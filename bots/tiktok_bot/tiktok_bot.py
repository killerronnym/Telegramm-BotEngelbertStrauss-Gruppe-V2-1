import asyncio
import time
import requests
import json
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')
from dataclasses import dataclass
from typing import Dict, Tuple, Optional, List
from telegram.ext import Application

# --- AUTO-PFAD SETUP ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, '..', '..'))

def log_print(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    safe_msg = str(msg).encode('utf-8', 'replace').decode('utf-8')
    log_line = f"[{timestamp}] TikTok Bot: {safe_msg}"
    
    # Print to stdout
    try:
        print(log_line, flush=True)
    except UnicodeEncodeError:
        print(f"[{timestamp}] TikTok Bot: [Message contains unsupported characters]", flush=True)
        
    # Write to log file for the dashboard
    log_file_path = os.path.join(PROJECT_ROOT, "logs", "tiktok_bot.log")
    try:
        os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
        with open(log_file_path, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")
    except Exception as e:
        print(f"Failed to write to log file: {e}")

try:
    from TikTokLive import TikTokLiveClient
    from TikTokLive.events import ConnectEvent, DisconnectEvent, JoinEvent, SocialEvent
    log_print("✅ TikTokLive Basis geladen.")
except Exception as e:
    log_print(f"❌ FEHLER BEIM LADEN: {e}")
    # Do not exit here, allow ID-Finder bot to start
    # sys.exit(1) # Removed sys.exit(1)
    TikTokLiveClient = None # Mark as unavailable
    ConnectEvent, DisconnectEvent, JoinEvent, SocialEvent = None, None, None, None


# =========================
# CONFIG LOAD
# =========================
# Load config using the shared_bot_utils now capable of hitting MySQL
sys.path.append(PROJECT_ROOT)
from shared_bot_utils import get_bot_config, is_bot_active

def load_config():
    log_print("Lade ID-Finder Config...")
    id_finder_config = get_bot_config("id_finder")
    log_print("Lade TikTok Config...")
    tiktok_config = get_bot_config("tiktok")
    log_print(f"Config geladen. Aktiv: {tiktok_config.get('is_active')}")
    
    # Kompatibilität für alte und neue Config-Struktur
    targets = tiktok_config.get("target_unique_ids", [])
    if not targets and tiktok_config.get("target_unique_id"):
        targets = [tiktok_config.get("target_unique_id")]
    
    return {
        "TELEGRAM_BOT_TOKEN": tiktok_config.get("bot_token") or get_bot_token(),
        "TELEGRAM_CHAT_ID": tiktok_config.get("telegram_chat_id"),
        "TELEGRAM_TOPIC_ID": tiktok_config.get("telegram_topic_id"),
        "TARGETS": [t.lower() for t in targets],
        "WATCH_HOSTS": tiktok_config.get("watch_hosts", []),
        "RETRY_OFFLINE_SECONDS": tiktok_config.get("retry_offline_seconds", 60),
        "ALERT_COOLDOWN_SECONDS": tiktok_config.get("alert_cooldown_seconds", 1800),
        "IS_ACTIVE": tiktok_config.get("is_active", False),
        "MESSAGE_TEMPLATE_SELF": tiktok_config.get("message_template_self", "🔴 {target} ist jetzt LIVE!\\n\\n🔗 {url}"),
        "MESSAGE_TEMPLATE_PRESENCE": tiktok_config.get("message_template_presence", "👀 {target} wurde in einem TikTok-Live gesehen!\\n\\n🎥 Host: @{host}\\n📌 Event: {event}\\n🔗 {url}")
    }

def safe_load_config():
    try:
        return load_config()
    except Exception as e:
        log_print(f"❌ Kritischer Fehler in load_config: {e}")
        return {}

def tg_send(token: str, chat_id: str, topic_id: str, text: str) -> None:
    if not token or not chat_id: return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": False}
    if topic_id:
        try: payload["message_thread_id"] = int(topic_id)
        except: pass
    try:
        requests.post(url, json=payload, timeout=20).raise_for_status()
        log_print("🚀 Telegram Nachricht gesendet!")
    except Exception as e: log_print(f"❌ Telegram Fehler: {e}")

@dataclass
class AlertState:
    # key: (host, target) -> last_sent_ts
    last_sent: Dict[Tuple[str, str], float]
    # key: target -> last_host_notified
    last_host: Dict[str, str]

    def can_send(self, host: str, target: str, cooldown: int) -> bool:
        h, t = host.lower(), target.lower()
        if self.last_host.get(t) != h: return True
        return (time.time() - self.last_sent.get((h, t), 0.0)) >= cooldown

    def mark_sent(self, host: str, target: str):
        h, t = host.lower(), target.lower()
        self.last_host[t] = h
        self.last_sent[(h, t)] = time.time()

def live_url(host: str) -> str: return f"https://www.tiktok.com/@{host}/live"

async def watch_one_host(host_unique_id: str, targets: List[str], alert_state: AlertState, sem: asyncio.Semaphore) -> None:
    host_unique_id = host_unique_id.lower()
    
    # Check if TikTokLiveClient is available
    if TikTokLiveClient is None:
        log_print(f"TikTokLiveClient nicht verfügbar, kann @{host_unique_id} nicht überwachen.")
        return

    while True:
        if not is_bot_active('tiktok'):
            log_print("TikTok Bot ist im Dashboard DEAKTIVIERT. Warte...")
            await asyncio.sleep(60)
            continue
            
        config = load_config()
        if not config.get("IS_ACTIVE"):
            log_print(f"TikTok Bot ist in Config DEAKTIVIERT. Überspringe Überwachung für @{host_unique_id}.")
            await asyncio.sleep(config.get("RETRY_OFFLINE_SECONDS", 60))
            continue

        try:
            async with sem:
                log_print(f"Verbinde mit @{host_unique_id}...")
                client = TikTokLiveClient(unique_id=host_unique_id)

                def check_and_alert(event, event_type: str):
                    try:
                        raw_data = str(event).lower()
                        # Wir prüfen JEDES Ziel in den Event-Daten
                        for t in config["TARGETS"]:
                            if t in raw_data:
                                if alert_state.can_send(host_unique_id, t, config["ALERT_COOLDOWN_SECONDS"]):
                                    log_print(f"[{host_unique_id}] 🎯 {t} ERKANNT ({event_type})!")
                                    # Ist es sein eigenes Live?
                                    is_self = (host_unique_id == t)
                                    template = config["MESSAGE_TEMPLATE_SELF"] if is_self else config["MESSAGE_TEMPLATE_PRESENCE"]
                                    
                                    try:
                                        msg = template.format(target=t, host=host_unique_id, event=event_type, url=live_url(host_unique_id))
                                    except:
                                        msg = f"Meldung: {t} @ {host_unique_id} ({event_type})"\
                                    
                                    tg_send(config["TELEGRAM_BOT_TOKEN"], config["TELEGRAM_CHAT_ID"], config["TELEGRAM_TOPIC_ID"], msg)
                                    alert_state.mark_sent(host_unique_id, t)
                    except Exception as e:
                        log_print(f"Error in check_and_alert: {e}")


                @client.on(ConnectEvent)
                async def on_connect(event: ConnectEvent):
                    log_print(f"[{host_unique_id}] ✅ Verbunden.")
                    check_and_alert(event, "Stream-Start")

                @client.on(SocialEvent)
                async def on_social(event: SocialEvent):
                    check_and_alert(event, "Aktivität")

                # TODO: These events might not exist in newer TikTokLive versions or need proper handling
                # @client.on("LinkMicMethodEvent")
                # async def on_method(event): check_and_alert(event, "In Box")

                # @client.on("LinkLayerEvent")
                # async def on_layer(event): check_and_alert(event, "Layout")

                try:
                    await client.start()
                except Exception as e:
                    log_print(f"Fehler beim Starten des TikTokLive-Clients für @{host_unique_id}: {e}")
                finally:
                    try: await client.disconnect()
                    except: pass
        except Exception as e:
            log_print(f"Unerwarteter Fehler in watch_one_host für @{host_unique_id}: {e}")
        
        await asyncio.sleep(config.get("RETRY_OFFLINE_SECONDS", 60))

async def start_tiktok_monitor(app_instance: Application = None):
    log_print("=== TIKTOK MONITOR MULTI-TARGET AKTIV ===")
    config = safe_load_config()
    if not config:
        log_print("❌ Abbruch: Konfiguration konnte nicht geladen werden.")
        return
        
    log_print(f"Accounts in Config: {config.get('TARGETS', [])}")
    alert_state = AlertState(last_host={}, last_sent={})
    sem = asyncio.Semaphore(config.get("MAX_CONCURRENT_LIVES", 3))
    
    tasks = []
    # Alle Hosts scannen
    log_print(f"Erstelle Tasks für {len(config.get('WATCH_HOSTS', []))} Hosts...")
    for h in config.get("WATCH_HOSTS", []):
        tasks.append(asyncio.create_task(watch_one_host(h, config["TARGETS"], alert_state, sem)))
    
    # Zusätzlich jeden Ziel-Account selbst scannen (falls einer davon selbst live geht)
    log_print(f"Erstelle Tasks für {len(config.get('TARGETS', []))} Ziele...")
    for t in config.get("TARGETS", []):
        if t not in config.get("WATCH_HOSTS", []):
            tasks.append(asyncio.create_task(watch_one_host(t, [t], alert_state, sem)))
    
    log_print(f"✅ Monitoring-Setup abgeschlossen. {len(tasks)} Kanäle werden überwacht.")
    if tasks:
        await asyncio.gather(*tasks)
    else:
        log_print("Keine TikTok Hosts oder Ziele konfiguriert. TikTok Monitor wird nicht gestartet.")
        # Keep the monitor alive, but sleeping if there are no hosts to watch
        while True:
            await asyncio.sleep(60)

def setup_jobs(job_queue):
    """Wird vom main_bot aufgerufen, um den Hintergrund-Task zu starten."""
    job_queue.run_once(lambda context: asyncio.create_task(start_tiktok_monitor()), 5)

if __name__ == "__main__":
    print("Bitte starte den Bot über main_bot.py")
