import os
import json
import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple, List

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from mcstatus import JavaServer

log = logging.getLogger(__name__)


# --- Paths -------------------------------------------------------------------
def _project_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(here)


def _find_config_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(here)
    candidates = [
        os.path.join(project_root, "data", "minecraft_status_config.json"),
        os.path.join(here, "minecraft_status_config.json"),
        os.path.join(project_root, "minecraft_status_config.json"),
        os.path.join(project_root, "MinecraftServerStatus", "minecraft_status_config.json"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return candidates[0]


CONFIG_PATH = _find_config_path()
DATA_DIR = os.path.join(_project_root(), "data")
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
    "status_message_created_at": None,  # ✅ NEU: Timestamp der Statusmessage (für Rotation < 48h)
}


def _load_cfg() -> Dict[str, Any]:
    cfg = dict(DEFAULT_CFG)
    if not os.path.exists(CONFIG_PATH):
        return cfg
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            cfg.update(raw)
        return cfg
    except Exception as e:
        log.error("Could not read %s: %s", CONFIG_PATH, e)
        return dict(DEFAULT_CFG)


def _atomic_write_json(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)


def _save_cfg(cfg: Dict[str, Any]) -> None:
    try:
        _atomic_write_json(CONFIG_PATH, cfg)
    except Exception as e:
        log.error("Could not write %s: %s", CONFIG_PATH, e)


# --- Helpers ------------------------------------------------------------------
def _cfg_host_port(cfg: Dict[str, Any]) -> Tuple[str, int]:
    # ✅ PRIORITÄT: mc_host/mc_port (Dashboard) → danach host/port (Legacy)
    host = str(cfg.get("mc_host") or cfg.get("host") or "127.0.0.1").strip()

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


async def _fetch_status(host: str, port: int, timeout_seconds: int):
    timeout_seconds = max(1, min(int(timeout_seconds or 5), 10))

    def _blocking():
        t0 = time.monotonic()
        server = JavaServer.lookup(f"{host}:{port}")
        st = server.status()
        ping_ms = int((time.monotonic() - t0) * 1000)
        return st, ping_ms

    return await asyncio.wait_for(
        asyncio.to_thread(_blocking),
        timeout=timeout_seconds + 1
    )


def _sanitize_text(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"§.", "", s)
    s = re.sub(r"<[^>]+>", "", s)
    return "".join(ch for ch in s if ch == "\n" or ord(ch) >= 32).replace("\r", "\n").strip()


def _motd_plain(status) -> str:
    try:
        return str(getattr(status.motd, "to_plain", lambda: status.motd)())
    except Exception:
        return str(getattr(status, "motd", ""))


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

    ver = str(getattr(getattr(status, "version", None), "name", "") or "") or None
    online = int(getattr(getattr(status, "players", None), "online", 0))
    maxp = int(getattr(getattr(status, "players", None), "max", 0))

    sample = getattr(getattr(status, "players", None), "sample", []) or []
    names: List[str] = [
        _sanitize_text(p.name)
        for p in sample[:40]
        if getattr(p, "name", None)
    ]

    motd = _sanitize_text(_motd_plain(status)).replace("\n", " ").strip() or None

    base.update({
        "version": ver,
        "motd": motd,
        "players": f"{online}/{maxp}",
        "player_count": online,
        "max_players": maxp,
        "online_names": names,
    })
    return base


def _write_status_cache(cache: Dict[str, Any]) -> None:
    try:
        _atomic_write_json(STATUS_CACHE_PATH, cache)
    except Exception as e:
        log.error("Could not write status cache %s: %s", STATUS_CACHE_PATH, e)


def _fmt_status_text(status, display_host: str, display_port: int, name: str) -> str:
    motd = _sanitize_text(_motd_plain(status)).replace("\n", " ").strip()

    ver = str(getattr(getattr(status, "version", None), "name", "") or "")
    online = int(getattr(getattr(status, "players", None), "online", 0))
    maxp = int(getattr(getattr(status, "players", None), "max", 0))

    sample = getattr(getattr(status, "players", None), "sample", []) or []
    players = [f"• {_sanitize_text(p.name)}" for p in sample[:20] if getattr(p, "name", None)]

    lines = [
        "🟢 Online",  # ✅ oben nur das
        f"⛏️ {name}",
        f"🌐 {display_host}:{display_port}",
    ]
    if ver:
        lines.append(f"🧩 Version: {ver}")
    if motd:
        lines.append(f"💬 MOTD: {motd}")

    lines.append(f"👥 Spieler: {online}/{maxp}")

    if players:
        lines.append("")
        lines.append("👥 Player:")
        lines.extend(players)

    return "\n".join(lines)


# --- Telegram Status Job ------------------------------------------------------
async def _send_or_edit_status(context: ContextTypes.DEFAULT_TYPE):
    cfg = _load_cfg()
    host, port = _cfg_host_port(cfg)
    name = str(cfg.get("name") or "Minecraft Server").strip()
    timeout_seconds = int(cfg.get("timeout_seconds") or 5)

    display_host, display_port = _cfg_display_host_port(cfg, host, port)

    chat_id = str(cfg.get("chat_id", "")).strip()
    topic_id = cfg.get("topic_id")

    if not host or not chat_id:
        log.warning("Minecraft bridge: config missing host/chat_id in %s", CONFIG_PATH)
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

    # --- Fetch status + cache schreiben (für Web-Dashboard) ---
    text: str
    msg_id = cfg.get("status_message_id")

    try:
        status, ping_ms = await _fetch_status(host, port, timeout_seconds)
        text = _fmt_status_text(status, display_host, display_port, name)

        cache = _status_to_cache(
            ok=True,
            host=host,
            port=port,
            display_host=display_host,
            display_port=display_port,
            name=name,
            status=status,
            ping_ms=ping_ms,
        )
        _write_status_cache(cache)

    except Exception as e:
        # ✅ Offline-Text ohne technische Fehlermeldung
        text = (
            f"🔴 Offline\n"
            f"⛏️ {name}\n"
            f"🌐 {display_host}:{display_port}\n\n"
            "Der Server ist gerade nicht erreichbar – bitte später nochmal schauen 😊"
        )

        cache = _status_to_cache(
            ok=False,
            host=host,
            port=port,
            display_host=display_host,
            display_port=display_port,
            name=name,
            status=None,
            ping_ms=None,
            error=f"{type(e).__name__}: {e}",
        )
        _write_status_cache(cache)

    # --- Rotation: damit Löschen sicher innerhalb 48h klappt ---
    created_at_raw = cfg.get("status_message_created_at")
    created_at_ts: Optional[float] = None
    if created_at_raw:
        try:
            created_at_ts = datetime.fromisoformat(str(created_at_raw)).timestamp()
        except Exception:
            created_at_ts = None

    ROTATE_AFTER_SECONDS = 24 * 60 * 60  # 24h (sicher unter 48h)
    now_ts = time.time()
    must_rotate = bool(msg_id and created_at_ts and (now_ts - created_at_ts) > ROTATE_AFTER_SECONDS)

    try:
        # ✅ Proaktiv rotieren, bevor Telegram Delete-Limit (48h) greift
        if msg_id and must_rotate:
            try:
                await context.bot.delete_message(chat_id=chat_id_int, message_id=int(msg_id))
                log.info("Minecraft bridge: rotated status message (deleted old %s).", msg_id)
            except Exception as e_del:
                log.warning("Minecraft bridge: could not delete old status message %s: %s", msg_id, e_del)

            cfg["status_message_id"] = None
            cfg["status_message_created_at"] = None
            _save_cfg(cfg)
            msg_id = None

        # ✅ Normalfall: editieren
        if msg_id:
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id_int,
                    message_id=int(msg_id),
                    text=text,
                    disable_web_page_preview=True,
                )
                return

            except Exception as e_edit:
                msg_lower = str(e_edit).lower()

                if "message is not modified" in msg_lower:
                    return

                # ✅ Edit geht nicht mehr -> löschen versuchen -> neu senden
                try:
                    await context.bot.delete_message(chat_id=chat_id_int, message_id=int(msg_id))
                    log.info("Minecraft bridge: deleted old status message %s after edit failure.", msg_id)
                except Exception as e_del:
                    log.warning("Minecraft bridge: could not delete old status message %s: %s", msg_id, e_del)

                cfg["status_message_id"] = None
                cfg["status_message_created_at"] = None
                _save_cfg(cfg)
                msg_id = None

        # ✅ Neue Statusmessage senden
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

    except Exception as e:
        log.error("Minecraft bridge: send/edit failed: %s", e)


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

    if not update.message:
        return

    try:
        status, _ping_ms = await _fetch_status(host, port, timeout_seconds)
        online = int(status.players.online)
        maxp = int(status.players.max)

        names = [
            _sanitize_text(p.name)
            for p in (status.players.sample or [])[:40]
            if getattr(p, "name", None)
        ]

        txt = f"⛏️ {name}\n🌐 {display_host}:{display_port}\n👥 Spieler online: {online}/{maxp}"
        if names:
            txt += "\n" + "\n".join(f"• {n}" for n in names)

        m = await update.message.reply_text(txt)

    except Exception as e:
        m = await update.message.reply_text(f"🔴 Server nicht erreichbar ({type(e).__name__})")

    if delete_after > 0 and context.job_queue:
        async def _del(c: ContextTypes.DEFAULT_TYPE):
            try:
                await c.bot.delete_message(chat_id=m.chat_id, message_id=m.message_id)
            except Exception:
                pass

        context.job_queue.run_once(_del, when=delete_after)


# --- Registration -------------------------------------------------------------
def register_minecraft(app) -> None:
    cfg = _load_cfg()
    every = max(10, min(int(cfg.get("update_seconds") or 30), 3600))

    app.add_handler(CommandHandler("player", cmd_player))

    if app.job_queue:
        app.job_queue.run_once(_job_callback, when=15)
        app.job_queue.run_repeating(_job_callback, interval=every, first=every)
        log.info("Minecraft bridge job scheduled every %ss (config: %s).", every, CONFIG_PATH)
        log.info("Minecraft status cache path: %s", STATUS_CACHE_PATH)
    else:
        log.warning("Minecraft bridge: job_queue not available – status auto-update disabled.")


# --- CLI / Debug --------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    cfg = _load_cfg()
    host, port = _cfg_host_port(cfg)
    display_host, display_port = _cfg_display_host_port(cfg, host, port)
    name = cfg.get("name", "Minecraft Server")

    async def _main():
        print("🔍 Teste Minecraft-Status…")
        print(f"Host: {host}:{port}")
        try:
            status, ping_ms = await _fetch_status(host, port, cfg.get("timeout_seconds", 5))
            text = _fmt_status_text(status, display_host, display_port, name)
            print("\n✅ ONLINE\n")
            print(f"Ping: {ping_ms} ms\n")
            print(text)
        except Exception as e:
            print("\n🔴 OFFLINE / FEHLER")
            print(type(e).__name__, str(e))

    asyncio.run(_main())
