import asyncio
import time
import requests
import json
import os
import sys
from dataclasses import dataclass
from typing import Dict, Tuple, Optional, List
from telegram.ext import Application

# --- AUTO-PFAD SETUP ---
def setup_environment():
    current = os.path.dirname(os.path.abspath(__file__))
    project_root = None
    for _ in range(5):
        if os.path.exists(os.path.join(current, 'venv')):
            project_root = current
            break
        parent = os.path.dirname(current)
        if parent == current: break
        current = parent
    if project_root:
        venv_pkgs = os.path.join(project_root, 'venv', 'lib', 'python3.11', 'site-packages')
        if os.path.exists(venv_pkgs) and venv_pkgs not in sys.path:
            sys.path.insert(0, venv_pkgs)
        return project_root
    return None

PROJECT_ROOT = setup_environment()

def log_print(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    # Encode/decode to safely handle emojis in Windows console
    safe_msg = str(msg).encode('utf-8', 'replace').decode('utf-8')
    try:
        print(f"[{timestamp}] TikTok Bot: {safe_msg}", flush=True)
    except UnicodeEncodeError:
        print(f"[{timestamp}] TikTok Bot: [Message contains unsupported characters]", flush=True)

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
from shared_bot_utils import get_bot_config

def load_config():
    id_finder_config = get_bot_config("id_finder")
    tiktok_config = get_bot_config("tiktok")
    
    # Kompatibilität für alte und neue Config-Struktur
    targets = tiktok_config.get("target_unique_ids", [])
    if not targets and tiktok_config.get("target_unique_id"):
        targets = [tiktok_config.get("target_unique_id")]
    
    return {
        "TELEGRAM_BOT_TOKEN": id_finder_config.get("bot_token"),
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
        config = load_config()
        if not config.get("IS_ACTIVE"):
            log_print(f"TikTok Bot ist DEAKTIVIERT. Überspringe Überwachung für @{host_unique_id}.")
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
    config = load_config()
    alert_state = AlertState(last_host={}, last_sent={})
    sem = asyncio.Semaphore(config.get("MAX_CONCURRENT_LIVES", 3))
    
    tasks = []
    # Alle Hosts scannen
    for h in config["WATCH_HOSTS"]:
        tasks.append(asyncio.create_task(watch_one_host(h, config["TARGETS"], alert_state, sem)))
    
    # Zusätzlich jeden Ziel-Account selbst scannen (falls einer davon selbst live geht)
    for t in config["TARGETS"]:
        if t not in config["WATCH_HOSTS"]:
            tasks.append(asyncio.create_task(watch_one_host(t, [t], alert_state, sem)))
    
    log_print(f"Beobachte {len(tasks)} Kanäle auf {len(config['TARGETS'])} Zielpersonen.")
    if tasks:
        await asyncio.gather(*tasks)
    else:
        log_print("Keine TikTok Hosts oder Ziele konfiguriert. TikTok Monitor wird nicht gestartet.")
        # Keep the monitor alive, but sleeping if there are no hosts to watch
        while True:
            await asyncio.sleep(60)

if __name__ == "__main__":
    try:
        asyncio.run(start_tiktok_monitor())
    except KeyboardInterrupt:
        pass
