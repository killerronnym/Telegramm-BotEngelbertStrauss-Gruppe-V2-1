import os
import json
import asyncio
import logging
import re
import time
import socket
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple, List

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes, Application

# Try importing mcstatus, handle potential missing dependency
try:
    from mcstatus import JavaServer
except ImportError:
    JavaServer = None

from shared_bot_utils import get_bot_config, get_db_url
from sqlalchemy import create_engine, text

log = logging.getLogger(__name__)

# --- Database Helper for saving ---
def update_minecraft_config(cfg: Dict[str, Any]) -> bool:
    try:
        engine = create_engine(get_db_url())
        with engine.connect() as conn:
            conn.execute(
                text("UPDATE bot_settings SET config_json = :cfg WHERE bot_name = 'minecraft'"),
                {"cfg": json.dumps(cfg)}
            )
            conn.commit()
        return True
    except Exception as e:
        log.error(f"Fehler beim Speichern der Minecraft-Config: {e}")
        return False

# ✅ Globaler Lock gegen doppelte Nachrichten / Parallelität
_status_lock = asyncio.Lock()


# --- Paths -------------------------------------------------------------------
def _project_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(here)


def _find_config_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(here)
    # Search in multiple locations for robustness
    candidates = [
        os.path.join(project_root, "data", "minecraft_status_config.json"),
        os.path.join(here, "minecraft_status_config.json"),
        os.path.join(project_root, "minecraft_status_config.json"),
        os.path.join(project_root, "MinecraftServerStatus", "minecraft_status_config.json"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    # Fallback to standard location
    return os.path.join(project_root, "data", "minecraft_status_config.json")


CONFIG_PATH = _find_config_path()
DATA_DIR = os.path.join(_project_root(), "data")
# ✅ Robustheits-Fix: Sicherstellen, dass das Datenverzeichnis existiert
os.makedirs(DATA_DIR, exist_ok=True)

STATUS_CACHE_PATH = os.path.join(DATA_DIR, "minecraft_status_cache.json")


# --- Config ------------------------------------------------------------------
DEFAULT_CFG: Dict[str, Any] = {
    # Anzeige-Name
    "name": "Minecraft Server",

    # Wichtig: NICHT mehr standardmäßig 127.0.0.1 erzwingen!
    # mc_host/mc_port werden vom Dashboard gespeichert und sollen PRIORITÄT haben.
    "mc_host": "",
    "mc_port": 25565,

    # Backward compatibility (falls alte Config noch host/port nutzt)
    "host": "",
    "port": None,

    "timeout_seconds": 5,

    "display_host": "",
    "display_port": None,

    "chat_id": "",
    "topic_id": None,

    "update_seconds": 30,
    "delete_player_seconds": 8,

    "status_message_id": None,
    "status_message_created_at": None,  # Timestamp der Statusmessage (für Rotation < 48h)
}


def _load_cfg() -> Dict[str, Any]:
    cfg = dict(DEFAULT_CFG)
    try:
        db_cfg = get_bot_config("minecraft")
        if db_cfg:
            cfg.update(db_cfg)
        return cfg
    except Exception as e:
        log.error("Could not load config from DB: %s", e)
        return dict(DEFAULT_CFG)


def _atomic_write_json(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
    except Exception as e:
        log.error(f"Failed to atomic write {path}: {e}")
        if os.path.exists(tmp_path):
            try: os.remove(tmp_path)
            except: pass


def _save_cfg(cfg: Dict[str, Any]) -> None:
    update_minecraft_config(cfg)


# --- Helpers ------------------------------------------------------------------
def _cfg_host_port(cfg: Dict[str, Any]) -> Tuple[str, int]:
    host = str(cfg.get("mc_host") or cfg.get("host") or "").strip()
    # If no host is configured, we can't do anything
    if not host: 
        return "", 25565
        
    port_raw = cfg.get("mc_port")
    if port_raw in (None, "", "null"):
        port_raw = cfg.get("port")
    if port_raw in (None, "", "null"):
        port_raw = 25565
    try:
        port = int(port_raw)
    except Exception:
        port = 25565
    return host, port


def _cfg_display_host_port(cfg: Dict[str, Any], host: str, port: int) -> Tuple[str, int]:
    display_host = str(cfg.get("display_host") or host).strip()
    try:
        display_port = int(cfg.get("display_port") or port)
    except Exception:
        display_port = port
    return display_host, display_port


async def _fetch_status(host: str, port: int, timeout_seconds: int) -> Tuple[Any, int]:
    if not JavaServer:
        raise ImportError("mcstatus library not installed")

    timeout_seconds = max(1, min(int(timeout_seconds or 5), 15))
    
    def _blocking():
        t0 = time.monotonic()
        # Lookup can also take time (DNS), so we include it in the measurement/timeout logic implicitly via wrapper
        server = JavaServer.lookup(f"{host}:{port}")
        st = server.status()
        duration = time.monotonic() - t0
        ping_ms = int(duration * 1000)
        return st, ping_ms

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_blocking),
            timeout=timeout_seconds
        )
    except asyncio.TimeoutError:
        raise TimeoutError(f"Connection timed out after {timeout_seconds}s")
    except socket.gaierror:
        raise OSError("DNS resolution failed")
    except ConnectionRefusedError:
        raise OSError("Connection refused")
    except Exception as e:
        # Re-raise as is or wrap if needed
        raise e


def _sanitize_text(s: str) -> str:
    if not s:
        return ""
    # Remove Minecraft color codes (§x)
    s = re.sub(r"§.", "", str(s))
    # Remove HTML-like tags just in case
    s = re.sub(r"<[^>]+>", "", s)
    # Keep only printable chars and newlines, limit length
    cleaned = "".join(ch for ch in s if ch == "\n" or (ord(ch) >= 32 and ord(ch) != 127)).replace("\r", "\n").strip()
    return cleaned[:1000] # Limit length to prevent log spam or UI issues


def _motd_plain(status) -> str:
    try:
        if hasattr(status, "motd"):
            if callable(getattr(status.motd, "to_plain", None)):
                return status.motd.to_plain()
            return str(status.motd)
        return ""
    except Exception:
        return ""


def _status_to_cache(
    ok: bool,
    host: str,
    port: int,
    display_host: str,
    display_port: int,
    name: str,
    status=None,
    ping_ms: Optional[int] = None,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    base: Dict[str, Any] = {
        "last_update": now,
        "server_online": bool(ok),
        "ping_ms": ping_ms,
        "name": name,
        "host": host,
        "port": port,
        "display_host": display_host,
        "display_port": display_port,
        "version": None,
        "software": None,
        "motd": None,
        "players": None,
        "player_count": None,
        "max_players": None,
        "online_names": [],
        "error": error,
    }
    
    if not ok or status is None:
        return base

    try:
        # Safely extract data
        ver = str(getattr(getattr(status, "version", None), "name", "") or "") or None
        
        players_obj = getattr(status, "players", None)
        online = int(getattr(players_obj, "online", 0))
        maxp = int(getattr(players_obj, "max", 0))
        sample = getattr(players_obj, "sample", []) or []
        
        names: List[str] = []
        if sample:
            for p in sample[:40]: # Limit to 40
                p_name = getattr(p, "name", None)
                if p_name:
                    names.append(_sanitize_text(p_name))
        
        motd = _sanitize_text(_motd_plain(status)).replace("\n", " ").strip() or None
        
        base.update({
            "version": ver,
            "motd": motd,
            "players": f"{online}/{maxp}",
            "player_count": online,
            "max_players": maxp,
            "online_names": names,
        })
    except Exception as e:
        log.error(f"Error parsing status object: {e}")
        base["error"] = "Error parsing server response"
        
    return base


def _write_status_cache(cache: Dict[str, Any]) -> None:
    try:
        _atomic_write_json(STATUS_CACHE_PATH, cache)
    except Exception as e:
        log.error("Could not write status cache %s: %s", STATUS_CACHE_PATH, e)


def _fmt_status_text(status, display_host: str, display_port: int, name: str) -> str:
    try:
        motd = _sanitize_text(_motd_plain(status)).replace("\n", " ").strip()
        ver = str(getattr(getattr(status, "version", None), "name", "") or "")
        
        players_obj = getattr(status, "players", None)
        online = int(getattr(players_obj, "online", 0))
        maxp = int(getattr(players_obj, "max", 0))
        sample = getattr(players_obj, "sample", []) or []
        
        players = []
        if sample:
            for p in sample[:20]: # Limit to 20 for telegram message
                p_name = getattr(p, "name", None)
                if p_name:
                    players.append(f"• {_sanitize_text(p_name)}")
                    
        lines = [
            "🟢 Online",
            f"⛏️ {name}",
            f"🌐 {display_host}:{display_port}",
        ]
        if ver: lines.append(f"🧩 Version: {ver}")
        if motd: lines.append(f"💬 MOTD: {motd}")
        lines.append(f"👥 Spieler: {online}/{maxp}")
        if players:
            lines.append("")
            lines.append("👥 Player:")
            lines.extend(players)
            
        return "\n".join(lines)
    except Exception as e:
        log.error(f"Error formatting status text: {e}")
        return f"🟢 Online\n⛏️ {name}\n🌐 {display_host}:{display_port}\n(Fehler beim Verarbeiten der Details)"


# --- Telegram Status Job ------------------------------------------------------
async def _send_or_edit_status(context: ContextTypes.DEFAULT_TYPE):
    if not context.job: return # Safety check

    async with _status_lock:
        cfg = _load_cfg()
        host, port = _cfg_host_port(cfg)
        name = str(cfg.get("name") or "Minecraft Server").strip()
        timeout_seconds = int(cfg.get("timeout_seconds") or 5)
        display_host, display_port = _cfg_display_host_port(cfg, host, port)
        chat_id = str(cfg.get("chat_id", "")).strip()
        topic_id = cfg.get("topic_id")

        if not host:
            # Silent return if no host configured (yet)
            return

        if not chat_id:
            # Log only once or nicely if chat_id missing
            return

        try:
            chat_id_int = int(chat_id)
        except Exception:
            log.warning("Minecraft bridge: chat_id not int: %r", chat_id)
            return

        thread_id: Optional[int] = None
        if topic_id not in (None, "", "null"):
            try:
                thread_id = int(str(topic_id).strip())
            except Exception:
                thread_id = None

        # --- Fetch status + cache schreiben ---
        text: str
        status = None
        ping_ms = None
        error_msg = None
        
        try:
            status, ping_ms = await _fetch_status(host, port, timeout_seconds)
            text = _fmt_status_text(status, display_host, display_port, name)
            
            cache = _status_to_cache(
                ok=True,
                host=host, port=port,
                display_host=display_host, display_port=display_port,
                name=name, status=status, ping_ms=ping_ms
            )
            _write_status_cache(cache)
            
        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            log.info(f"Minecraft Server {host}:{port} offline/unreachable: {error_msg}")
            
            text = (
                f"🔴 Offline\n"
                f"⛏️ {name}\n"
                f"🌐 {display_host}:{display_port}\n\n"
                f"Der Server ist gerade nicht erreichbar."
            )
            cache = _status_to_cache(
                ok=False,
                host=host, port=port,
                display_host=display_host, display_port=display_port,
                name=name, status=None, ping_ms=None,
                error=error_msg
            )
            _write_status_cache(cache)

        # --- msg_id normalisieren ---
        msg_id_raw = cfg.get("status_message_id")
        msg_id: Optional[int] = None
        if msg_id_raw not in (None, "", "null", 0):
            try:
                msg_id = int(msg_id_raw)
            except Exception:
                msg_id = None

        created_at_raw = cfg.get("status_message_created_at")

        # Robustheits-Fix: Falls msg_id existiert aber created_at fehlt -> jetzt setzen
        if msg_id and not created_at_raw:
            cfg["status_message_created_at"] = datetime.now().isoformat(timespec="seconds")
            _save_cfg(cfg)
            created_at_raw = cfg["status_message_created_at"]

        # --- Rotation prüfen ---
        must_rotate = False
        if msg_id and created_at_raw:
            try:
                ca_dt = datetime.fromisoformat(str(created_at_raw))
                # Rotate after 23 hours to stay fresh in chat
                if (datetime.now() - ca_dt).total_seconds() > 23 * 3600:
                    must_rotate = True
            except Exception:
                must_rotate = True

        # 1) Proaktive Rotation: delete -> cfg clear -> dann neu
        if msg_id and must_rotate:
            try:
                await context.bot.delete_message(chat_id=chat_id_int, message_id=msg_id)
                log.info("Minecraft bridge: rotated status message (deleted old %s).", msg_id)
            except Exception as e_del:
                log.warning("Minecraft bridge: could not delete old status message %s for rotation: %s", msg_id, e_del)

            msg_id = None
            cfg["status_message_id"] = None
            cfg["status_message_created_at"] = None
            _save_cfg(cfg)

        # 2) Edit versuchen
        if msg_id:
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id_int,
                    message_id=msg_id,
                    text=text,
                    disable_web_page_preview=True,
                )
                return
            except Exception as e_edit:
                msg_lower = str(e_edit).lower()
                if "message is not modified" in msg_lower:
                    return # No changes, all good

                log.info("Minecraft bridge: edit failed for %s (%s). Attempting delete and new post.", msg_id, e_edit)
                try:
                    await context.bot.delete_message(chat_id=chat_id_int, message_id=msg_id)
                except Exception:
                    pass # Ignore if already deleted

                msg_id = None
                cfg["status_message_id"] = None
                cfg["status_message_created_at"] = None
                _save_cfg(cfg)

        # 3) Neu senden (erst NACH delete/cfg-clear)
        try:
            sent = await context.bot.send_message(
                chat_id=chat_id_int,
                message_thread_id=thread_id,
                text=text,
                disable_web_page_preview=True,
                disable_notification=True,
            )
            cfg["status_message_id"] = sent.message_id
            cfg["status_message_created_at"] = datetime.now().isoformat(timespec="seconds")
            _save_cfg(cfg)
            log.info("Minecraft bridge: sent new status message %s", sent.message_id)
        except Exception as e_send:
            log.error("Minecraft bridge: failed to send new status message: %s", e_send)


async def _job_callback(context: ContextTypes.DEFAULT_TYPE):
    await _send_or_edit_status(context)


# --- /player Command ----------------------------------------------------------
async def cmd_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = _load_cfg()
    host, port = _cfg_host_port(cfg)
    name = str(cfg.get("name") or "Minecraft Server").strip()
    timeout_seconds = int(cfg.get("timeout_seconds") or 5)
    display_host, display_port = _cfg_display_host_port(cfg, host, port)
    delete_after = int(cfg.get("delete_player_seconds") or 8)
    
    if not update.message: return
    
    m = None
    try:
        status, _ping_ms = await _fetch_status(host, port, timeout_seconds)
        online = int(status.players.online)
        maxp = int(status.players.max)
        
        names = []
        if status.players.sample:
            names = [_sanitize_text(p.name) for p in status.players.sample if getattr(p, "name", None)]
            names = names[:40] # Limit
            
        txt = f"⛏️ {name}\n🌐 {display_host}:{display_port}\n👥 Spieler online: {online}/{maxp}"
        if names: txt += "\n" + "\n".join(f"• {n}" for n in names)
        
        m = await update.message.reply_text(txt)
    except ImportError:
        m = await update.message.reply_text("🔴 Fehler: 'mcstatus' Bibliothek fehlt.")
    except Exception as e:
        m = await update.message.reply_text(f"🔴 Server nicht erreichbar ({type(e).__name__})")
        
    if m and delete_after > 0 and context.job_queue:
        async def _del(c: ContextTypes.DEFAULT_TYPE):
            try: await c.bot.delete_message(chat_id=m.chat_id, message_id=m.message_id)
            except Exception: pass
        context.job_queue.run_once(_del, when=delete_after)


# --- Registration -------------------------------------------------------------
def register_minecraft(app: Application) -> None:
    if not JavaServer:
        log.error("❌ 'mcstatus' library not found. Minecraft bridge disabled.")
        return

    cfg = _load_cfg()
    every = max(10, min(int(cfg.get("update_seconds") or 30), 3600))
    
    app.add_handler(CommandHandler("player", cmd_player))
    
    if app.job_queue:
        # Run first update slightly delayed to allow bot startup to finish
        app.job_queue.run_once(_job_callback, when=10)
        app.job_queue.run_repeating(_job_callback, interval=every, first=20)
        log.info("Minecraft bridge job scheduled every %ss.", every)
    else:
        log.warning("Minecraft bridge: job_queue not available – status auto-update disabled.")


# --- CLI / Debug --------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    if not JavaServer:
        print("❌ 'mcstatus' library not installed. Please run: pip install mcstatus")
        exit(1)
        
    cfg = _load_cfg()
    host, port = _cfg_host_port(cfg)
    display_host, display_port = _cfg_display_host_port(cfg, host, port)
    name = cfg.get("name", "Minecraft Server")
    
    async def _main():
        print(f"🔍 Teste Minecraft-Status für {host}:{port}...")
        try:
            status, ping_ms = await _fetch_status(host, port, cfg.get("timeout_seconds", 5))
            text = _fmt_status_text(status, display_host, display_port, name)
            print("\n✅ ONLINE")
            print(f"Ping: {ping_ms} ms")
            print("-" * 20)
            print(text)
        except Exception as e:
            print("\n🔴 OFFLINE / FEHLER")
            print(f"{type(e).__name__}: {e}")
            
    asyncio.run(_main())
