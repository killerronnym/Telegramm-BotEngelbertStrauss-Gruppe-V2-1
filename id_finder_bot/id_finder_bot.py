import logging
import os
import json
import re
import html
import threading
from datetime import datetime, timedelta
from collections import defaultdict, deque
from typing import Optional, Tuple, List, Dict, Any

try:
    from zoneinfo import ZoneInfo
except Exception:
    try:
        from backports.zoneinfo import ZoneInfo
    except Exception:
        ZoneInfo = None

from telegram import Update, ChatPermissions, MessageEntity
from telegram.error import TelegramError, Forbidden
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# Optional (Reactions Updates) – je nach python-telegram-bot Version verfügbar
try:
    from telegram.ext import MessageReactionHandler  # type: ignore
except Exception:
    MessageReactionHandler = None  # fallback

try:
    from telegram.ext import MessageReactionCountHandler  # type: ignore
except Exception:
    MessageReactionCountHandler = None  # fallback

# ✅ Minecraft Bridge (separate Datei minecraft_bridge.py)
try:
    from minecraft_bridge import register_minecraft  # type: ignore
except Exception:
    register_minecraft = None  # fallback


# --- Logging Setup ---------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

# --- Configuration & Paths -------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # .../id_finder_bot
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# ✅ IMMER aus id_finder_bot/id_finder_config.json lesen/schreiben
CONFIG_FILE = os.path.join(BASE_DIR, "id_finder_config.json")
COMMAND_LOG_FILE = os.path.join(BASE_DIR, "id_finder_command.log")

MODERATION_DATA_FILE = os.path.join(DATA_DIR, "moderation_data.json")
ADMINS_FILE = os.path.join(PROJECT_ROOT, "dashboard", "admins.json")

USERNAME_CACHE_FILE = os.path.join(DATA_DIR, "username_cache.json")
USER_REGISTRY_FILE = os.path.join(DATA_DIR, "user_registry.json")

# ✅ Message Logs (pro User)
USER_MESSAGE_DIR = os.path.join(DATA_DIR, "user_messages")
os.makedirs(USER_MESSAGE_DIR, exist_ok=True)

# ✅ NEU: Global Activity Log (für Dashboard Analytics)
ACTIVITY_LOG_FILE = os.path.join(DATA_DIR, "activity_log.jsonl")

# ✅ Optional: Reactions Events (falls PTB das liefert)
REACTIONS_LOG_FILE = os.path.join(DATA_DIR, "reactions_log.jsonl")

# ✅ NEU: Index, um message_id -> from_user_id aufzulösen (für ReactionCount Updates)
MESSAGE_INDEX_FILE = os.path.join(DATA_DIR, "message_index.jsonl")

# Lock für File Writes
_FILE_LOCK = threading.Lock()

TZ = ZoneInfo("Europe/Berlin")

# In-Memory Cache: (chat_id, message_id) -> from_user_id
_MSG_INDEX_CACHE: Dict[Tuple[int, int], int] = {}
_MSG_INDEX_CACHE_MAX = 20000


# ---------------------------
# JSON Helpers
# ---------------------------
def load_json_file(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading {path}: {e}")
        return default


def save_json_file(path: str, data):
    try:
        dir_ = os.path.dirname(path)
        if dir_:
            os.makedirs(dir_, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving {path}: {e}")



def load_config() -> Dict[str, Any]:
    return load_json_file(CONFIG_FILE, {})


def save_config(config: dict):
    save_json_file(CONFIG_FILE, config)


def load_moderation_data() -> Dict[str, Any]:
    return load_json_file(MODERATION_DATA_FILE, {})


def save_moderation_data(data: Dict[str, Any]):
    save_json_file(MODERATION_DATA_FILE, data)


def load_admins() -> Dict[str, Any]:
    return load_json_file(ADMINS_FILE, {})


def load_username_cache() -> Dict[str, int]:
    return load_json_file(USERNAME_CACHE_FILE, {})


def save_username_cache(cache: Dict[str, int]):
    save_json_file(USERNAME_CACHE_FILE, cache)


def load_user_registry() -> Dict[str, Any]:
    return load_json_file(USER_REGISTRY_FILE, {"users": {}})


def save_user_registry(reg: Dict[str, Any]):
    save_json_file(USER_REGISTRY_FILE, reg)


def now_iso() -> str:
    # ✅ Dashboard-freundlich: timezone aware ISO (Berlin)
    return datetime.now(TZ).isoformat(timespec="seconds")


def escape(s: str) -> str:
    return html.escape(s or "", quote=False)


def _cfg_bool(cfg: Dict[str, Any], key: str, default: bool) -> bool:
    v = cfg.get(key, default)
    return bool(v) if isinstance(v, bool) else str(v).strip().lower() in ("1", "true", "yes", "on")


def _cfg_int(cfg: Dict[str, Any], key: str, default: int) -> int:
    try:
        return int(cfg.get(key, default))
    except Exception:
        return default


def log_command(user_id, user_name, command, target_id=None, details=None):
    timestamp = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    log_entry = (
        f"[{timestamp}] User: {user_name} ({user_id}) | "
        f"Cmd: {command} | Target: {target_id} | Details: {details}\n"
    )
    try:
        with open(COMMAND_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception as e:
        logger.error(f"Error writing to command log: {e}")


# ---------------------------
# Cleanup Helpers
# ---------------------------
async def cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.delete_message(
            chat_id=context.job.chat_id,
            message_id=context.job.data["message_id"],
        )
    except TelegramError:
        pass


async def send_and_schedule_delete(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    *,
    chat_id: Optional[int] = None,
    thread_id: Optional[int] = None,
    parse_mode: Optional[str] = None,
    disable_web_page_preview: bool = True,
):
    config = load_config()
    cleanup_seconds = int(config.get("bot_message_cleanup_seconds", 0) or 0)
    delete_commands = bool(config.get("delete_commands", False))

    try:
        real_chat_id = chat_id if chat_id is not None else (update.effective_chat.id if update.effective_chat else None)
        real_thread_id = thread_id if thread_id is not None else (
            update.effective_message.message_thread_id if update.effective_message else None
        )

        if update.message and not delete_commands and real_chat_id == update.effective_chat.id:
            sent_message = await update.message.reply_text(
                text,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview,
            )
        else:
            sent_message = await context.bot.send_message(
                chat_id=real_chat_id,
                text=text,
                message_thread_id=real_thread_id,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview,
            )

        if cleanup_seconds > 0 and context.job_queue:
            context.job_queue.run_once(
                cleanup_job,
                when=cleanup_seconds,
                data={"message_id": sent_message.message_id},
                chat_id=real_chat_id,
                name=f"cleanup_{sent_message.message_id}",
            )

    except TelegramError as e:
        logger.error(f"Failed to send or schedule cleanup: {e}")


async def dm_user(context: ContextTypes.DEFAULT_TYPE, user_id: int, text: str, parse_mode: Optional[str] = "HTML") -> bool:
    try:
        await context.bot.send_message(chat_id=user_id, text=text, parse_mode=parse_mode, disable_web_page_preview=True)
        return True
    except Forbidden:
        return False
    except TelegramError:
        return False


# ---------------------------
# Admin Log Target
# ---------------------------
def get_admin_log_target(config: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    admin_group_id = config.get("admin_group_id")
    admin_topic_id = config.get("admin_log_topic_id")
    try:
        admin_group_id = int(admin_group_id) if admin_group_id else None
    except (ValueError, TypeError):
        admin_group_id = None
    try:
        admin_topic_id = int(admin_topic_id) if admin_topic_id else None
    except (ValueError, TypeError):
        admin_topic_id = None
    return admin_group_id, admin_topic_id


async def admin_log(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    config = load_config()
    admin_group_id, admin_topic_id = get_admin_log_target(config)
    if not admin_group_id:
        return
    try:
        await context.bot.send_message(
            chat_id=admin_group_id,
            message_thread_id=admin_topic_id,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except TelegramError:
        pass


# ---------------------------
# Permissions
# ---------------------------
def check_permission(permission_key: str):
    def decorator(func):
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            if not update.effective_user:
                return

            user_id = str(update.effective_user.id)
            admins = load_admins()

            if user_id not in admins or not admins[user_id].get("permissions", {}).get(permission_key, False):
                log_command(user_id, update.effective_user.full_name, f"PERMISSION_DENIED: {func.__name__}")
                await send_and_schedule_delete(update, context, f"❌ Keine Berechtigung ({permission_key}).")
                return

            return await func(update, context, *args, **kwargs)

        return wrapper
    return decorator


# ---------------------------
# User Registry (persistent)
# ---------------------------
def register_user_seen(user, chat_id: Optional[int] = None):
    """
    Persistently store user info for web dashboard & safer resolving.
    """
    if not user:
        return

    reg = load_user_registry()
    users = reg.setdefault("users", {})

    uid = str(user.id)
    entry = users.get(uid, {})
    entry.setdefault("first_seen", now_iso())
    entry["last_seen"] = now_iso()
    entry["full_name"] = user.full_name or entry.get("full_name", "")
    entry["is_bot"] = bool(getattr(user, "is_bot", False))

    username = getattr(user, "username", None)
    if username:
        entry["username"] = str(username).lstrip("@")
    else:
        entry.setdefault("username", "")

    chat_ids = entry.get("chat_ids", [])
    if chat_id is not None:
        try:
            cid = int(chat_id)
            if cid not in chat_ids:
                chat_ids.append(cid)
        except Exception:
            pass
    entry["chat_ids"] = chat_ids

    users[uid] = entry
    save_user_registry(reg)

    # keep the fast cache in sync too
    if username:
        uname = str(username).lstrip("@").lower()
        cache = load_username_cache()
        cache[uname] = int(user.id)
        save_username_cache(cache)


# ---------------------------
# File Helpers (JSONL)
# ---------------------------
def _rotate_file_if_needed(path: str, max_bytes: int = 10 * 1024 * 1024, backups: int = 3):
    """
    Wenn Datei zu groß wird, rotiere:
      file.(backups) -> löschen
      file.(n) -> file.(n+1)
      file -> file.1
    """
    try:
        if not os.path.exists(path):
            return
        if os.path.getsize(path) <= max_bytes:
            return

        # delete oldest
        oldest = f"{path}.{backups}"
        if os.path.exists(oldest):
            try:
                os.remove(oldest)
            except Exception:
                pass

        # shift downwards
        for i in range(backups - 1, 0, -1):
            src = f"{path}.{i}"
            dst = f"{path}.{i+1}"
            if os.path.exists(src):
                try:
                    os.replace(src, dst)
                except Exception:
                    pass

        # move main to .1
        try:
            os.replace(path, f"{path}.1")
        except Exception:
            pass
    except Exception:
        pass


def _append_jsonl(path: str, obj: Dict[str, Any], *, max_bytes: int, backups: int):
    line = json.dumps(obj, ensure_ascii=False)
    with _FILE_LOCK:
        _rotate_file_if_needed(path, max_bytes=max_bytes, backups=backups)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def _tail_lines(path: str, max_lines: int = 4000) -> List[str]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            block = 4096
            data = b""
            lines: List[bytes] = []
            while size > 0 and len(lines) <= (max_lines + 50):
                step = block if size >= block else size
                size -= step
                f.seek(size)
                data = f.read(step) + data
                lines = data.splitlines()
                if len(lines) >= (max_lines + 5):
                    break
            tail = lines[-max_lines:] if max_lines > 0 else lines
            return [x.decode("utf-8", errors="replace") for x in tail]
    except Exception:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.readlines()[-max_lines:]
        except Exception:
            return []


# ---------------------------
# Message Index (message_id -> sender)
# ---------------------------
def _msg_key(chat_id: int, message_id: int) -> Tuple[int, int]:
    return (int(chat_id), int(message_id))


def _cache_msg_index(chat_id: int, message_id: int, from_user_id: int):
    key = _msg_key(chat_id, message_id)
    _MSG_INDEX_CACHE[key] = int(from_user_id)

    # simple eviction
    if len(_MSG_INDEX_CACHE) > _MSG_INDEX_CACHE_MAX:
        for _ in range(len(_MSG_INDEX_CACHE) - _MSG_INDEX_CACHE_MAX):
            try:
                _MSG_INDEX_CACHE.pop(next(iter(_MSG_INDEX_CACHE)))
            except Exception:
                break


def _append_message_index(chat, msg, user):
    try:
        if not chat or not msg or not user:
            return
        rec = {
            "ts": now_iso(),
            "chat_id": chat.id,
            "message_id": msg.message_id,
            "from_user_id": user.id,
        }
        cfg = load_config()
        max_bytes = _cfg_int(cfg, "message_index_max_bytes", 20 * 1024 * 1024)
        backups = _cfg_int(cfg, "message_index_backups", 5)
        _append_jsonl(MESSAGE_INDEX_FILE, rec, max_bytes=max_bytes, backups=backups)
        _cache_msg_index(chat.id, msg.message_id, user.id)
    except Exception:
        pass


def _lookup_sender_id(chat_id: int, message_id: int) -> Optional[int]:
    key = _msg_key(chat_id, message_id)
    if key in _MSG_INDEX_CACHE:
        return _MSG_INDEX_CACHE[key]

    # fallback: scan tail of index file
    lines = _tail_lines(MESSAGE_INDEX_FILE, max_lines=6000)
    for line in reversed(lines):
        line = (line or "").strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if int(obj.get("chat_id", -1)) == int(chat_id) and int(obj.get("message_id", -1)) == int(message_id):
            uid = obj.get("from_user_id")
            if isinstance(uid, int):
                _cache_msg_index(chat_id, message_id, uid)
                return uid
            try:
                uid_i = int(uid)
                _cache_msg_index(chat_id, message_id, uid_i)
                return uid_i
            except Exception:
                return None
    return None


def _user_log_paths(uid: str, max_backups: int = 5) -> List[str]:
    base = os.path.join(USER_MESSAGE_DIR, f"{uid}.jsonl")
    paths = []
    if os.path.exists(base):
        paths.append(base)
    for i in range(1, max_backups + 1):
        p = f"{base}.{i}"
        if os.path.exists(p):
            paths.append(p)
    return paths


def _patch_message_reactions_in_user_log(
    from_user_id: int,
    chat_id: int,
    message_id: int,
    reactions_total: int,
    reactions_detail: Optional[List[Dict[str, Any]]] = None,
):
    """
    Patcht die ursprüngliche Message im JSONL (in-place), damit Dashboard die Reactions korrekt anzeigen kann,
    OHNE dass Reaction-Events als "Messages" gezählt werden.
    """
    uid = str(from_user_id)
    paths = _user_log_paths(uid, max_backups=6)
    if not paths:
        return

    cfg = load_config()
    max_patch_bytes = _cfg_int(cfg, "reaction_patch_max_bytes", 25 * 1024 * 1024)

    for path in paths:
        try:
            if not os.path.exists(path):
                continue
            if os.path.getsize(path) > max_patch_bytes:
                continue

            with _FILE_LOCK:
                with open(path, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                changed = False
                for i in range(len(lines) - 1, -1, -1):
                    line = (lines[i] or "").strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue

                    # nur echte Messages patchen, keine Reaction-Events
                    ev = str(obj.get("event") or obj.get("kind") or "").lower().strip()
                    if ev in ("reaction", "reaction_update", "message_reaction", "reaction_count", "message_reaction_count"):
                        continue

                    if int(obj.get("chat_id", -1)) != int(chat_id):
                        continue
                    if int(obj.get("message_id", -1)) != int(message_id):
                        continue
                    if int(obj.get("from_user_id", -1)) != int(from_user_id):
                        continue

                    prev = obj.get("reactions")
                    try:
                        prev_i = int(prev) if prev is not None else 0
                    except Exception:
                        prev_i = 0

                    # nur patchen, wenn sich was ändert (oder größer wird)
                    if int(reactions_total) == prev_i:
                        return

                    obj["reactions"] = int(reactions_total)
                    obj["reactions_total"] = int(reactions_total)
                    obj["reaction_count"] = int(reactions_total)
                    obj["reactions_updated_at"] = now_iso()
                    if reactions_detail is not None:
                        obj["reactions_detail"] = reactions_detail

                    lines[i] = json.dumps(obj, ensure_ascii=False) + "\n"
                    changed = True
                    break

                if changed:
                    with open(path, "w", encoding="utf-8") as f:
                        f.writelines(lines)
                return

        except Exception:
            continue


# ---------------------------
# Message / Media Helpers
# ---------------------------
def _detect_msg_type(msg) -> str:
    try:
        if msg.photo:
            return "photo"
        if msg.video:
            return "video"
        if msg.document:
            return "document"
        if msg.animation:
            return "animation"
        if msg.sticker:
            return "sticker"
        if msg.voice:
            return "voice"
        if msg.audio:
            return "audio"
        if msg.text:
            return "text"
        if msg.caption:
            return "caption"
    except Exception:
        pass
    return "other"


def _message_media_payload(msg) -> Dict[str, Any]:
    """
    Extrahiert Medien-Metadaten (keine Downloads!).
    """
    media: Dict[str, Any] = {"kind": None}

    try:
        if msg.photo:
            p = msg.photo[-1]
            media = {
                "kind": "photo",
                "file_id": getattr(p, "file_id", None),
                "file_unique_id": getattr(p, "file_unique_id", None),
                "width": getattr(p, "width", None),
                "height": getattr(p, "height", None),
                "file_size": getattr(p, "file_size", None),
            }
            return media

        if msg.video:
            v = msg.video
            media = {
                "kind": "video",
                "file_id": getattr(v, "file_id", None),
                "file_unique_id": getattr(v, "file_unique_id", None),
                "width": getattr(v, "width", None),
                "height": getattr(v, "height", None),
                "duration": getattr(v, "duration", None),
                "mime_type": getattr(v, "mime_type", None),
                "file_size": getattr(v, "file_size", None),
            }
            return media

        if msg.document:
            d = msg.document
            media = {
                "kind": "document",
                "file_id": getattr(d, "file_id", None),
                "file_unique_id": getattr(d, "file_unique_id", None),
                "file_name": getattr(d, "file_name", None),
                "mime_type": getattr(d, "mime_type", None),
                "file_size": getattr(d, "file_size", None),
            }
            return media

        if msg.animation:
            a = msg.animation
            media = {
                "kind": "animation",
                "file_id": getattr(a, "file_id", None),
                "file_unique_id": getattr(a, "file_unique_id", None),
                "file_name": getattr(a, "file_name", None),
                "mime_type": getattr(a, "mime_type", None),
                "file_size": getattr(a, "file_size", None),
                "duration": getattr(a, "duration", None),
                "width": getattr(a, "width", None),
                "height": getattr(a, "height", None),
            }
            return media

        if msg.sticker:
            s = msg.sticker
            media = {
                "kind": "sticker",
                "file_id": getattr(s, "file_id", None),
                "file_unique_id": getattr(s, "file_unique_id", None),
                "emoji": getattr(s, "emoji", None),
                "set_name": getattr(s, "set_name", None),
                "is_animated": getattr(s, "is_animated", None),
                "is_video": getattr(s, "is_video", None),
            }
            return media

        if msg.voice:
            v = msg.voice
            media = {
                "kind": "voice",
                "file_id": getattr(v, "file_id", None),
                "file_unique_id": getattr(v, "file_unique_id", None),
                "duration": getattr(v, "duration", None),
                "mime_type": getattr(v, "mime_type", None),
                "file_size": getattr(v, "file_size", None),
            }
            return media

        if msg.audio:
            a = msg.audio
            media = {
                "kind": "audio",
                "file_id": getattr(a, "file_id", None),
                "file_unique_id": getattr(a, "file_unique_id", None),
                "duration": getattr(a, "duration", None),
                "title": getattr(a, "title", None),
                "performer": getattr(a, "performer", None),
                "file_name": getattr(a, "file_name", None),
                "mime_type": getattr(a, "mime_type", None),
                "file_size": getattr(a, "file_size", None),
            }
            return media
    except Exception:
        pass

    return media


def _count_reactions_from_message(msg) -> int:
    """
    Falls die Message bereits Reaction-Infos enthält (je nach API/Version).
    Meistens sind Reactions nicht direkt in message enthalten – aber falls doch, zählen wir sie.
    """
    try:
        r = getattr(msg, "reactions", None)
        if not r:
            return 0

        counts = []
        if hasattr(r, "reactions") and isinstance(r.reactions, list):
            for x in r.reactions:
                c = getattr(x, "total_count", None)
                if isinstance(c, int):
                    counts.append(c)
        if hasattr(r, "total_count") and isinstance(r.total_count, int):
            return int(r.total_count)
        return int(sum(counts)) if counts else 0
    except Exception:
        return 0


# ---------------------------
# ✅ Message Logging + Global Activity (Dashboard)
# ---------------------------
async def log_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Loggt Nachrichten/Medien pro User in data/user_messages/<uid>.jsonl
    UND zusätzlich global in data/activity_log.jsonl (für Analytics Dashboard).
    """
    try:
        cfg = load_config()

        # Pro-User Logging
        if not _cfg_bool(cfg, "message_logging_enabled", True):
            return

        only_groups = _cfg_bool(cfg, "message_logging_groups_only", True)

        msg = update.effective_message
        chat = update.effective_chat
        user = update.effective_user

        if not msg or not chat or not user:
            return

        if only_groups and chat.type not in ("group", "supergroup"):
            return

        if bool(getattr(user, "is_bot", False)) and _cfg_bool(cfg, "message_logging_ignore_bots", True):
            return

        # Commands optional ignorieren (für Text-Logs)
        is_command = bool((msg.text or "").strip().startswith("/"))
        if is_command and _cfg_bool(cfg, "message_logging_ignore_commands", True):
            return

        register_user_seen(user, chat.id)
        _append_message_index(chat, msg, user)

        media = _message_media_payload(msg)
        msg_type = _detect_msg_type(msg)

        text = msg.text or msg.caption or ""
        reaction_count = _count_reactions_from_message(msg)

        rec_user: Dict[str, Any] = {
            "ts": now_iso(),
            "chat_id": chat.id,
            "chat_type": chat.type,
            "chat_title": getattr(chat, "title", None),
            "thread_id": getattr(msg, "message_thread_id", None),
            "message_id": msg.message_id,
            "from_user_id": user.id,
            "username": (getattr(user, "username", None) or ""),
            "full_name": (getattr(user, "full_name", None) or ""),
            "text": text,
            "has_media": bool(media.get("kind")),
            "media": media,
            "msg_type": msg_type,
            "reactions": int(reaction_count),
            "reactions_total": int(reaction_count),
            "reaction_count": int(reaction_count),
            "edited": bool(getattr(update, "edited_message", None)),
        }

        if msg.reply_to_message and msg.reply_to_message.from_user:
            ru = msg.reply_to_message.from_user
            rec_user["reply_to"] = {
                "message_id": msg.reply_to_message.message_id,
                "from_user_id": ru.id,
                "username": getattr(ru, "username", None),
                "full_name": getattr(ru, "full_name", None),
            }

        uid = str(user.id)
        user_path = os.path.join(USER_MESSAGE_DIR, f"{uid}.jsonl")
        max_bytes_user = _cfg_int(cfg, "message_logging_max_bytes_per_user", 10 * 1024 * 1024)  # 10MB
        backups_user = _cfg_int(cfg, "message_logging_backups", 3)
        _append_jsonl(user_path, rec_user, max_bytes=max_bytes_user, backups=backups_user)

        # Global Activity (optional)
        if _cfg_bool(cfg, "activity_logging_enabled", True):
            count_commands = _cfg_bool(cfg, "activity_logging_include_commands", True)
            if is_command and not count_commands:
                return

            rec_activity: Dict[str, Any] = {
                "ts": rec_user["ts"],
                "chat_id": chat.id,
                "chat_type": chat.type,
                "chat_title": getattr(chat, "title", None),
                "thread_id": getattr(msg, "message_thread_id", None),
                "message_id": msg.message_id,
                "user_id": user.id,
                "username": (getattr(user, "username", None) or ""),
                "full_name": (getattr(user, "full_name", None) or ""),
                "msg_type": msg_type,
                "has_media": bool(media.get("kind")),
                "media_kind": media.get("kind"),
                "reactions": int(reaction_count),
                "is_command": is_command,
            }

            max_bytes_global = _cfg_int(cfg, "activity_logging_max_bytes", 50 * 1024 * 1024)  # 50MB
            backups_global = _cfg_int(cfg, "activity_logging_backups", 5)
            _append_jsonl(ACTIVITY_LOG_FILE, rec_activity, max_bytes=max_bytes_global, backups=backups_global)

    except Exception as e:
        logger.error(f"log_user_message failed: {e}")


# ---------------------------
# ✅ Reactions Serialization
# ---------------------------
def _serialize_reaction_list(reaction_obj) -> List[str]:
    """
    Versucht aus old/new reaction (PTB Objects) eine Liste von Strings zu machen.
    """
    out: List[str] = []
    try:
        if reaction_obj is None:
            return []
        if isinstance(reaction_obj, list):
            for r in reaction_obj:
                # PTB: ReactionTypeEmoji / ReactionTypeCustomEmoji / etc.
                emoji = getattr(r, "emoji", None)
                if emoji:
                    out.append(str(emoji))
                else:
                    # fallback
                    out.append(str(r))
            return out
        # fallback single
        out.append(str(reaction_obj))
    except Exception:
        pass
    return out


def _serialize_reaction_counts(reactions_obj) -> Tuple[int, List[Dict[str, Any]]]:
    """
    Für MessageReactionCount Updates:
    Gibt (total, details) zurück, wobei details eine Liste ist: [{"emoji": "🔥", "count": 3}, ...]
    """
    total = 0
    details: List[Dict[str, Any]] = []
    try:
        if reactions_obj is None:
            return 0, []

        # PTB: reactions_obj kann eine Liste von ReactionCount sein oder ein wrapper
        lst = None
        if isinstance(reactions_obj, list):
            lst = reactions_obj
        elif hasattr(reactions_obj, "reactions") and isinstance(reactions_obj.reactions, list):
            lst = reactions_obj.reactions

        if lst is None:
            # fallback: nichts parsebares
            return 0, [{"raw": str(reactions_obj)}]

        for item in lst:
            try:
                cnt = getattr(item, "total_count", None)
                if cnt is None:
                    cnt = getattr(item, "count", None)
                cnt_i = int(cnt) if cnt is not None else 0

                rtype = getattr(item, "type", None)
                emoji = getattr(rtype, "emoji", None) if rtype is not None else None
                if not emoji:
                    emoji = getattr(item, "emoji", None)

                details.append({"emoji": str(emoji) if emoji else None, "count": cnt_i})
                total += cnt_i
            except Exception:
                continue

        return int(total), details
    except Exception:
        return 0, []


# ---------------------------
# ✅ Reaction Updates loggen + Message-ReactionCounts nachtragen
# ---------------------------
async def log_reaction_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Loggt wer reagiert hat (old/new). Gut für "likes_given".
    """
    try:
        cfg = load_config()
        if not _cfg_bool(cfg, "activity_logging_enabled", True):
            return

        mr = getattr(update, "message_reaction", None)
        if not mr:
            return

        chat = getattr(mr, "chat", None)
        user = getattr(mr, "user", None)
        if not chat or not user:
            return

        register_user_seen(user, chat.id)

        old_list = _serialize_reaction_list(getattr(mr, "old_reaction", None))
        new_list = _serialize_reaction_list(getattr(mr, "new_reaction", None))

        # delta = Anzahl neu hinzugefügter Reactions (best-effort)
        delta = max(0, len(new_list) - len(old_list))

        payload = {
            "ts": now_iso(),
            "event": "reaction",
            "kind": "message_reaction",
            "chat_id": getattr(chat, "id", None),
            "chat_type": getattr(chat, "type", None),
            "chat_title": getattr(chat, "title", None),
            "message_id": getattr(mr, "message_id", None),
            "reactor_user_id": getattr(user, "id", None),
            "reactor_username": getattr(user, "username", None),
            "reactor_full_name": getattr(user, "full_name", None),
            "old_reaction": old_list,
            "new_reaction": new_list,
            "reaction_delta": int(delta),
        }

        max_bytes = _cfg_int(cfg, "reactions_logging_max_bytes", 20 * 1024 * 1024)
        backups = _cfg_int(cfg, "reactions_logging_backups", 3)
        _append_jsonl(REACTIONS_LOG_FILE, payload, max_bytes=max_bytes, backups=backups)

    except Exception as e:
        logger.error(f"log_reaction_update failed: {e}")


async def log_reaction_count_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Loggt ReactionCounts pro Message und patcht die ursprüngliche Message im User-Log,
    damit das Dashboard "Likes" wirklich anzeigen kann (alle Emojis).
    """
    try:
        cfg = load_config()
        if not _cfg_bool(cfg, "activity_logging_enabled", True):
            return

        mrc = getattr(update, "message_reaction_count", None)
        if not mrc:
            return

        chat = getattr(mrc, "chat", None)
        if not chat:
            return

        chat_id = getattr(chat, "id", None)
        message_id = getattr(mrc, "message_id", None)
        if chat_id is None or message_id is None:
            return

        total, details = _serialize_reaction_counts(getattr(mrc, "reactions", None))

        payload = {
            "ts": now_iso(),
            "event": "reaction_count",
            "kind": "message_reaction_count",
            "chat_id": int(chat_id),
            "chat_type": getattr(chat, "type", None),
            "chat_title": getattr(chat, "title", None),
            "message_id": int(message_id),
            "reactions_total": int(total),
            "reactions_detail": details,
        }

        max_bytes = _cfg_int(cfg, "reactions_logging_max_bytes", 20 * 1024 * 1024)
        backups = _cfg_int(cfg, "reactions_logging_backups", 3)
        _append_jsonl(REACTIONS_LOG_FILE, payload, max_bytes=max_bytes, backups=backups)

        # ✅ Sender ermitteln und Message im User-Log patchen
        sender_id = _lookup_sender_id(int(chat_id), int(message_id))
        if sender_id is None:
            return

        _patch_message_reactions_in_user_log(
            from_user_id=int(sender_id),
            chat_id=int(chat_id),
            message_id=int(message_id),
            reactions_total=int(total),
            reactions_detail=details,
        )

    except Exception as e:
        logger.error(f"log_reaction_count_update failed: {e}")


# ---------------------------
# ✅ Global Activity Tracker (für Analytics)
# ---------------------------
async def track_user_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Schreibt IMMER (auch bei Commands) die User-Daten in die Registry,
    damit Analytics/Dashboard zuverlässig Daten hat.
    """
    try:
        if update.effective_user:
            register_user_seen(update.effective_user, update.effective_chat.id if update.effective_chat else None)

        # Wenn jemand auf jemanden antwortet, speichern wir den Ziel-User auch direkt
        if update.effective_message and update.effective_message.reply_to_message and update.effective_message.reply_to_message.from_user:
            register_user_seen(
                update.effective_message.reply_to_message.from_user,
                update.effective_chat.id if update.effective_chat else None
            )

        # Reaction-Update: reactor auch registrieren
        mr = getattr(update, "message_reaction", None)
        if mr:
            u = getattr(mr, "user", None)
            c = getattr(mr, "chat", None)
            if u and c:
                register_user_seen(u, c.id)

    except Exception as e:
        logger.error(f"track_user_activity failed: {e}")


# ---------------------------
# Moderation Data helpers
# ---------------------------
def ensure_user_block(data: dict, user_id: int):
    uid = str(user_id)
    if uid not in data:
        data[uid] = {"warns": 0, "history": []}
    return data[uid]


def parse_duration(token: Optional[str]) -> Optional[timedelta]:
    if not token:
        return None
    m = re.match(r"^(\d+)([mhd])$", token.strip().lower())
    if not m:
        return None
    amount, unit = int(m.group(1)), m.group(2)
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "h":
        return timedelta(hours=amount)
    if unit == "d":
        return timedelta(days=amount)
    return None


# ---------------------------
# Target Resolution
# ---------------------------
def extract_text_mention_user(update: Update):
    msg = update.message
    if not msg or not msg.entities:
        return None
    for ent in msg.entities:
        if ent.type == MessageEntity.TEXT_MENTION and ent.user:
            return ent.user
    return None


def extract_tg_userid(token: str) -> Optional[int]:
    if not token:
        return None
    m = re.search(r"tg://user\?id=(\d+)", token)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def resolve_username_to_id(username: str) -> Optional[int]:
    username = (username or "").lstrip("@").lower()
    if not username:
        return None

    cache = load_username_cache()
    uid = cache.get(username)
    if uid:
        try:
            return int(uid)
        except Exception:
            pass

    reg = load_user_registry()
    users = reg.get("users", {}) or {}
    for uid_str, entry in users.items():
        if str(entry.get("username", "")).lower() == username:
            try:
                return int(uid_str)
            except Exception:
                return None
    return None


async def verify_user_in_chat(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, expected_username: Optional[str] = None) -> bool:
    try:
        m = await context.bot.get_chat_member(chat_id, user_id)
        if not m or not m.user:
            return False
        if expected_username:
            u = getattr(m.user, "username", None)
            if u and str(u).lstrip("@").lower() != expected_username.lstrip("@").lower():
                return False
        return True
    except TelegramError:
        return False


def looks_like_target_token(token: str) -> bool:
    if not token:
        return False
    t = token.strip()
    if t.startswith("@"):
        return True
    if re.match(r"^\d+$", t):
        return True
    if "tg://user?id=" in t:
        return True
    return False


async def get_target_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Tuple[Optional[int], List[str], str]:
    args = list(getattr(context, "args", []) or [])
    chat_id = update.effective_chat.id if update.effective_chat else None

    if args and looks_like_target_token(args[0]):
        first = args[0]

        if re.match(r"^\d+$", first.strip()):
            try:
                uid = int(first.strip())
                if chat_id and not await verify_user_in_chat(context, chat_id, uid):
                    return None, args[1:], "none"
                return uid, args[1:], "id"
            except ValueError:
                return None, args[1:], "none"

        tg_uid = extract_tg_userid(first)
        if tg_uid:
            if chat_id and not await verify_user_in_chat(context, chat_id, tg_uid):
                return None, args[1:], "none"
            return tg_uid, args[1:], "tg"

        if first.startswith("@"):
            expected = first.lstrip("@").lower()
            uid = resolve_username_to_id(first)
            if not uid:
                return None, args[1:], "username"
            if chat_id and not await verify_user_in_chat(context, chat_id, uid, expected_username=expected):
                return None, args[1:], "username"
            return uid, args[1:], "username"

    if update.message and update.message.reply_to_message and update.message.reply_to_message.from_user:
        target = update.message.reply_to_message.from_user
        register_user_seen(target, chat_id)
        return target.id, args, "reply"

    u = extract_text_mention_user(update)
    if u:
        register_user_seen(u, chat_id)
        if args and args[0].startswith("@"):
            args = args[1:]
        return u.id, args, "mention"

    return None, args, "none"


# ---------------------------
# Command Deletion (late)
# ---------------------------
async def handle_slash_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config = load_config()
    if config.get("delete_commands", False) and update.message:
        try:
            await update.message.delete()
        except TelegramError:
            pass


# ---------------------------
# In-Memory Flood Tracking
# ---------------------------
FLOOD_TRACKER = defaultdict(lambda: defaultdict(deque))


def is_admin_or_allowed(update: Update) -> bool:
    if not update.effective_chat or update.effective_chat.type not in ("group", "supergroup"):
        return True
    if not update.effective_user or update.effective_user.is_bot:
        return True
    admins = load_admins()
    uid = str(update.effective_user.id)
    return uid in admins


def extract_domains(text: str) -> List[str]:
    if not text:
        return []
    domains = []
    for m in re.finditer(r"https?://([^/\s]+)", text, flags=re.IGNORECASE):
        domains.append(m.group(1).lower())
    for m in re.finditer(r"\b([a-z0-9-]+\.[a-z]{2,})(/[^\s]*)?\b", text, flags=re.IGNORECASE):
        domains.append(m.group(1).lower())
    return list(dict.fromkeys(domains))


def contains_link(update: Update) -> bool:
    msg = update.message
    if not msg:
        return False
    if msg.entities:
        for ent in msg.entities:
            if ent.type in (MessageEntity.URL, MessageEntity.TEXT_LINK):
                return True
    text = msg.text or msg.caption or ""
    return bool(re.search(r"https?://|t\.me/|www\.", text, flags=re.IGNORECASE))


# ---------------------------
# Commands: Info
# ---------------------------
@check_permission("can_see_ids")
async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    user, chat = update.message.from_user, update.effective_chat
    topic_id = update.message.message_thread_id

    register_user_seen(user, chat.id if chat else None)

    response = f"👤 Deine ID: <code>{user.id}</code>\n💬 Chat ID: <code>{chat.id}</code>"
    if topic_id:
        response += f"\n🧵 Topic ID: <code>{topic_id}</code>"

    if update.message.reply_to_message:
        original_user = update.message.reply_to_message.from_user
        register_user_seen(original_user, chat.id if chat else None)
        response += f"\n\n👇 <b>Ziel-User</b> 👇\n👤 User ID: <code>{original_user.id}</code>"

    await send_and_schedule_delete(update, context, response, parse_mode="HTML")
    log_command(user.id, user.full_name, "/id")


@check_permission("can_see_ids")
async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await send_and_schedule_delete(update, context, f"💬 Chat ID: <code>{chat_id}</code>", parse_mode="HTML")
    log_command(update.effective_user.id, update.effective_user.full_name, "/chatid")


@check_permission("can_see_ids")
async def get_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_id, _args, kind = await get_target_user(update, context)
    if target_id:
        await send_and_schedule_delete(update, context, f"👤 User ID: <code>{target_id}</code>", parse_mode="HTML")
        log_command(update.effective_user.id, update.effective_user.full_name, "/userid", target_id)
    else:
        msg = (
            "❌ User nicht gefunden.\n"
            "Nutze: <b>/userid @username</b> oder <b>/userid 123456789</b>.\n"
            "Hinweis: @username geht nur zuverlässig, wenn der User bereits in der Registry ist (z.B. beigetreten/geschrieben)."
        )
        await send_and_schedule_delete(update, context, msg, parse_mode="HTML")


@check_permission("can_see_ids")
async def get_topic_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    topic_id = update.message.message_thread_id
    if topic_id:
        await send_and_schedule_delete(update, context, f"🧵 Topic ID: <code>{topic_id}</code>", parse_mode="HTML")
        log_command(update.effective_user.id, update.effective_user.full_name, "/topicid")
    else:
        await send_and_schedule_delete(update, context, "Dies ist kein Thema (Topic).")


@check_permission("can_see_ids")
async def whois(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /whois @user oder /whois 123
    Zeigt, was in data/user_registry.json über den User gespeichert ist.
    """
    if not context.args:
        await send_and_schedule_delete(update, context, "Usage: /whois @username  oder  /whois 123456")
        return

    token = context.args[0].strip()
    reg = load_user_registry()
    users = reg.get("users", {}) or {}

    uid: Optional[int] = None
    if token.startswith("@"):
        uid = resolve_username_to_id(token)
    elif re.match(r"^\d+$", token):
        uid = int(token)
    else:
        await send_and_schedule_delete(update, context, "Bitte @username oder User-ID angeben.")
        return

    if not uid:
        await send_and_schedule_delete(update, context, "❌ Nicht gefunden in Registry/Cache. Bitte User-ID nutzen.")
        return

    entry = users.get(str(uid))
    if not entry:
        await send_and_schedule_delete(update, context, "❌ User-ID bekannt, aber keine Registry-Daten. (User noch nie gesehen)")
        return

    txt = (
        f"👤 <b>User</b>: {escape(entry.get('full_name',''))}\n"
        f"🆔 <code>{uid}</code>\n"
        f"@{escape(entry.get('username',''))}\n"
        f"⏱️ first_seen: <code>{escape(entry.get('first_seen',''))}</code>\n"
        f"⏱️ last_seen: <code>{escape(entry.get('last_seen',''))}</code>\n"
        f"💬 chats: <code>{escape(str(entry.get('chat_ids', [])))}</code>"
    )
    await send_and_schedule_delete(update, context, txt, parse_mode="HTML")


# ---------------------------
# Admin setup
# ---------------------------
@check_permission("can_configure")
async def set_admin_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = load_config()
    cfg["admin_group_id"] = str(update.effective_chat.id)
    save_config(cfg)
    await send_and_schedule_delete(update, context, f"✅ Admin-Gruppe gesetzt: <code>{update.effective_chat.id}</code>", parse_mode="HTML")
    await admin_log(update, context, f"🛠️ Admin-Gruppe wurde gesetzt von <b>{escape(update.effective_user.full_name)}</b> (<code>{update.effective_user.id}</code>).")
    log_command(update.effective_user.id, update.effective_user.full_name, "/setadmingroup", details=str(update.effective_chat.id))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🤖 <b>Moderations-Befehle</b>\n"
        "Targets: am besten per <b>User-ID</b> oder <b>@username</b> (wenn bekannt).\n"
        "Reply geht weiterhin – aber <b>Args haben jetzt Priorität</b>.\n\n"
        "• <code>/warn @user Grund</code> oder <code>/warn 123456 Grund</code>\n"
        "• <code>/warnings @user</code>\n"
        "• <code>/unwarn @user</code>\n"
        "• <code>/clearwarnings @user</code>\n"
        "• <code>/mute @user 30m Grund</code>\n"
        "• <code>/unmute @user</code>\n"
        "• <code>/ban @user Grund</code>\n"
        "• <code>/unban 123456</code>\n"
        "• <code>/kick @user Grund</code>\n\n"
        "Tools:\n"
        "• <code>/del</code> (per Reply)\n"
        "• <code>/purge</code> (per Reply auf Start-Nachricht)\n"
        "• <code>/pin</code> / <code>/unpin</code> (per Reply)\n"
        "• <code>/lock links|media|stickers</code>\n"
        "• <code>/unlock links|media|stickers</code>\n"
        "• <code>/locks</code>\n\n"
        "Registry:\n"
        "• <code>/whois @user</code> / <code>/whois 123</code>\n\n"
        "Admin:\n"
        "• <code>/setadmingroup</code>\n"
        "• <code>/id</code> / <code>/chatid</code> / <code>/userid</code> / <code>/topicid</code>\n"
    )
    await send_and_schedule_delete(update, context, text, parse_mode="HTML")


# ---------------------------
# Moderation Actions
# ---------------------------
async def short_ack(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = "✅ Erledigt."):
    await send_and_schedule_delete(update, context, text)


@check_permission("can_warn")
async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_id, args, kind = await get_target_user(update, context)
    if not target_id:
        await send_and_schedule_delete(
            update,
            context,
            "❌ User nicht gefunden.\n"
            "👉 Bitte nutze <b>/warn 123456 Grund</b> (User-ID), wenn @username nicht auflösbar ist.\n"
            "Hinweis: @username funktioniert nur zuverlässig, wenn der User bereits in der Registry ist (beigetreten/geschrieben).",
            parse_mode="HTML",
        )
        return

    reason = " ".join(args).strip() or "Kein Grund angegeben"

    data = load_moderation_data()
    block = ensure_user_block(data, target_id)
    block["warns"] = int(block.get("warns", 0)) + 1
    block.setdefault("history", []).append(
        {"type": "warn", "reason": reason, "date": now_iso(), "by": update.effective_user.id}
    )
    save_moderation_data(data)

    cfg = load_config()
    warn_limit = int(cfg.get("warn_limit", 3) or 3)

    chat_title = update.effective_chat.title if update.effective_chat else "der Gruppe"

    dm_text = (
        f"⚠️ <b>Verwarnung</b>\n"
        f"Gruppe: <b>{escape(chat_title)}</b>\n"
        f"Grund: {escape(reason)}\n"
        f"Warnungen: <b>{block['warns']}/{warn_limit}</b>\n"
        f"\nWenn du Fragen hast, melde dich bei den Admins."
    )
    dm_ok = await dm_user(context, target_id, dm_text)

    await admin_log(
        update,
        context,
        f"⚠️ <b>WARN</b> durch <b>{escape(update.effective_user.full_name)}</b> (<code>{update.effective_user.id}</code>)\n"
        f"Target: <code>{target_id}</code>\n"
        f"Grund: {escape(reason)}\n"
        f"Warns: <b>{block['warns']}/{warn_limit}</b>\n"
        f"DM: {'✅' if dm_ok else '❌ (User hat Bot evtl. nicht gestartet)'}\n"
        f"Resolve: <code>{escape(kind)}</code>"
    )

    log_command(update.effective_user.id, update.effective_user.full_name, "/warn", target_id, reason)
    await short_ack(update, context, "✅ Verwarnung gespeichert.")


@check_permission("can_warn")
async def get_warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_id, _args, _kind = await get_target_user(update, context)
    if not target_id:
        await send_and_schedule_delete(update, context, "❌ User nicht gefunden. Nutze /warnings @username oder /warnings 123456.")
        return

    data = load_moderation_data()
    block = ensure_user_block(data, target_id)
    warnings_count = int(block.get("warns", 0))
    history = block.get("history", []) or []

    lines = [f"⚠️ <b>Warnungen</b> für <code>{target_id}</code>: <b>{warnings_count}</b>"]
    if history:
        lines.append("\n<b>Letzte Einträge:</b>")
        for entry in history[-10:]:
            et = escape(str(entry.get("type", "")))
            rs = escape(str(entry.get("reason", "")))
            dt = escape(str(entry.get("date", "")))
            lines.append(f"• <b>{et}</b> – {rs} <i>({dt})</i>")
    else:
        lines.append("Keine Einträge vorhanden.")

    await send_and_schedule_delete(update, context, "\n".join(lines), parse_mode="HTML")
    log_command(update.effective_user.id, update.effective_user.full_name, "/warnings", target_id)


@check_permission("can_warn")
async def unwarn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_id, _args, _kind = await get_target_user(update, context)
    if not target_id:
        await send_and_schedule_delete(update, context, "❌ User nicht gefunden.")
        return

    data = load_moderation_data()
    block = ensure_user_block(data, target_id)

    if int(block.get("warns", 0)) > 0:
        block["warns"] = int(block.get("warns", 0)) - 1
        block.setdefault("history", []).append(
            {"type": "unwarn", "reason": "Manuell entfernt", "date": now_iso(), "by": update.effective_user.id}
        )
        save_moderation_data(data)
        await short_ack(update, context, "✅ Verwarnung entfernt.")
    else:
        await short_ack(update, context, "ℹ️ User hat keine Verwarnungen.")

    await admin_log(update, context, f"✅ <b>UNWARN</b> durch <b>{escape(update.effective_user.full_name)}</b> → <code>{target_id}</code>")
    log_command(update.effective_user.id, update.effective_user.full_name, "/unwarn", target_id)


@check_permission("can_warn")
async def clear_warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_id, _args, _kind = await get_target_user(update, context)
    if not target_id:
        await send_and_schedule_delete(update, context, "❌ User nicht gefunden.")
        return

    data = load_moderation_data()
    block = ensure_user_block(data, target_id)
    old_warns = int(block.get("warns", 0))

    block["warns"] = 0
    block["history"] = []
    save_moderation_data(data)

    await short_ack(update, context, f"🗑️ Warnungen gelöscht ({old_warns}).")
    await admin_log(update, context, f"🗑️ <b>CLEARWARNINGS</b> durch <b>{escape(update.effective_user.full_name)}</b> → <code>{target_id}</code> (alt: {old_warns})")
    log_command(update.effective_user.id, update.effective_user.full_name, "/clearwarnings", target_id, f"old={old_warns}")


# ---------------------------
# Kick/Ban/Mute
# ---------------------------
@check_permission("can_kick")
async def kick_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_id, args, _kind = await get_target_user(update, context)
    if not target_id:
        await send_and_schedule_delete(update, context, "❌ User nicht gefunden.")
        return

    reason = " ".join(args).strip() or "Kein Grund angegeben"
    chat_title = update.effective_chat.title if update.effective_chat else "der Gruppe"
    await dm_user(context, target_id, f"👢 <b>Du wurdest gekickt</b>\nGruppe: <b>{escape(chat_title)}</b>\nGrund: {escape(reason)}")

    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target_id)
        await context.bot.unban_chat_member(update.effective_chat.id, target_id)
        await short_ack(update, context, "✅ Kick ausgeführt.")
        await admin_log(update, context, f"👢 <b>KICK</b> durch <b>{escape(update.effective_user.full_name)}</b> → <code>{target_id}</code>\nGrund: {escape(reason)}")
        log_command(update.effective_user.id, update.effective_user.full_name, "/kick", target_id, reason)
    except TelegramError as e:
        await send_and_schedule_delete(update, context, f"Fehler beim Kicken: {e}")


@check_permission("can_ban")
async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_id, args, _kind = await get_target_user(update, context)
    if not target_id:
        await send_and_schedule_delete(update, context, "❌ User nicht gefunden.")
        return

    reason = " ".join(args).strip() or "Kein Grund angegeben"
    chat_title = update.effective_chat.title if update.effective_chat else "der Gruppe"
    await dm_user(context, target_id, f"⛔ <b>Du wurdest gebannt</b>\nGruppe: <b>{escape(chat_title)}</b>\nGrund: {escape(reason)}")

    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target_id)
        await short_ack(update, context, "✅ Ban ausgeführt.")
        await admin_log(update, context, f"⛔ <b>BAN</b> durch <b>{escape(update.effective_user.full_name)}</b> → <code>{target_id}</code>\nGrund: {escape(reason)}")
        log_command(update.effective_user.id, update.effective_user.full_name, "/ban", target_id, reason)
    except TelegramError as e:
        await send_and_schedule_delete(update, context, f"Fehler beim Bannen: {e}")


@check_permission("can_ban")
async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_id, _args, _kind = await get_target_user(update, context)
    if not target_id:
        await send_and_schedule_delete(update, context, "❌ User nicht gefunden.")
        return

    try:
        await context.bot.unban_chat_member(update.effective_chat.id, target_id)
        await short_ack(update, context, "✅ Unban ausgeführt.")
        await admin_log(update, context, f"✅ <b>UNBAN</b> durch <b>{escape(update.effective_user.full_name)}</b> → <code>{target_id}</code>")
        log_command(update.effective_user.id, update.effective_user.full_name, "/unban", target_id)
    except TelegramError as e:
        await send_and_schedule_delete(update, context, f"Fehler beim Entbannen: {e}")


@check_permission("can_mute")
async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_id, args, _kind = await get_target_user(update, context)
    if not target_id:
        await send_and_schedule_delete(update, context, "❌ User nicht gefunden.")
        return

    duration_str = args[0] if args else None
    duration = parse_duration(duration_str)
    if not duration:
        await send_and_schedule_delete(update, context, "Bitte gib eine gültige Dauer an (z.B. 30m, 1h, 7d).")
        return

    reason = " ".join(args[1:]).strip() or "Kein Grund angegeben"
    until_date = datetime.now(TZ) + duration
    chat_title = update.effective_chat.title if update.effective_chat else "der Gruppe"

    await dm_user(
        context,
        target_id,
        f"🔇 <b>Stummgeschaltet</b>\nGruppe: <b>{escape(chat_title)}</b>\nDauer: <b>{escape(duration_str)}</b>\nGrund: {escape(reason)}"
    )

    try:
        permissions = ChatPermissions(can_send_messages=False)
        await context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=target_id,
            permissions=permissions,
            until_date=until_date,
        )
        await short_ack(update, context, "✅ Mute ausgeführt.")
        await admin_log(update, context, f"🔇 <b>MUTE</b> durch <b>{escape(update.effective_user.full_name)}</b> → <code>{target_id}</code>\nDauer: <b>{escape(duration_str)}</b>\nGrund: {escape(reason)}")
        log_command(update.effective_user.id, update.effective_user.full_name, "/mute", target_id, f"{duration_str} - {reason}")
    except TelegramError as e:
        await send_and_schedule_delete(update, context, f"Fehler beim Stummschalten: {e}")


@check_permission("can_mute")
async def unmute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_id, _args, _kind = await get_target_user(update, context)
    if not target_id:
        await send_and_schedule_delete(update, context, "❌ User nicht gefunden.")
        return

    try:
        permissions = ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
            can_invite_users=True,
        )
        await context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=target_id,
            permissions=permissions,
            until_date=None,
        )
        await short_ack(update, context, "✅ Unmute ausgeführt.")
        await admin_log(update, context, f"🔊 <b>UNMUTE</b> durch <b>{escape(update.effective_user.full_name)}</b> → <code>{target_id}</code>")
        log_command(update.effective_user.id, update.effective_user.full_name, "/unmute", target_id)
    except TelegramError as e:
        await send_and_schedule_delete(update, context, f"Fehler beim Entstummen: {e}")


# ---------------------------
# Message Tools
# ---------------------------
@check_permission("can_delete_messages")
async def delete_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.reply_to_message:
        await send_and_schedule_delete(update, context, "Bitte antworte auf eine Nachricht, die gelöscht werden soll.")
        return

    try:
        await update.message.reply_to_message.delete()
        await short_ack(update, context, "🗑️ Gelöscht.")
        log_command(update.effective_user.id, update.effective_user.full_name, "/del", details=f"Deleted message {update.message.reply_to_message.message_id}")
    except TelegramError as e:
        await send_and_schedule_delete(update, context, f"Fehler beim Löschen: {e}")


@check_permission("can_delete_messages")
async def purge_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.reply_to_message:
        await send_and_schedule_delete(update, context, "Bitte antworte auf die erste Nachricht im Bereich, der gelöscht werden soll.")
        return

    try:
        start_id = update.message.reply_to_message.message_id
        end_id = update.message.message_id - 1
        if end_id < start_id:
            await send_and_schedule_delete(update, context, "Nichts zu purgen.")
            return

        ids = list(range(start_id, end_id + 1))

        can_bulk = hasattr(context.bot, "delete_messages")
        for i in range(0, len(ids), 100):
            chunk = ids[i:i + 100]
            if can_bulk:
                try:
                    await context.bot.delete_messages(chat_id=update.effective_chat.id, message_ids=chunk)
                    continue
                except Exception:
                    pass
            for mid in chunk:
                try:
                    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=mid)
                except Exception:
                    pass

        await short_ack(update, context, f"🧹 Purge fertig ({len(ids)} msgs).")
        await admin_log(update, context, f"🧹 <b>PURGE</b> durch <b>{escape(update.effective_user.full_name)}</b> ({start_id}..{end_id})")
        log_command(update.effective_user.id, update.effective_user.full_name, "/purge", details=f"Purged {start_id}..{end_id}")

    except TelegramError as e:
        await send_and_schedule_delete(update, context, f"Fehler beim Purgen: {e}")


@check_permission("can_pin_messages")
async def pin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.reply_to_message:
        await send_and_schedule_delete(update, context, "Bitte antworte auf eine Nachricht, die angepinnt werden soll.")
        return

    try:
        await context.bot.pin_chat_message(
            chat_id=update.effective_chat.id,
            message_id=update.message.reply_to_message.message_id,
            disable_notification=True,
        )
        await short_ack(update, context, "📌 Angepinnt.")
        log_command(update.effective_user.id, update.effective_user.full_name, "/pin", details=f"Pinned {update.message.reply_to_message.message_id}")
    except TelegramError as e:
        await send_and_schedule_delete(update, context, f"Fehler beim Anpinnen: {e}")


@check_permission("can_pin_messages")
async def unpin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.reply_to_message:
        await send_and_schedule_delete(update, context, "Bitte antworte auf eine Nachricht, die gelöst werden soll.")
        return

    try:
        await context.bot.unpin_chat_message(
            chat_id=update.effective_chat.id,
            message_id=update.message.reply_to_message.message_id,
        )
        await short_ack(update, context, "✅ Unpin.")
        log_command(update.effective_user.id, update.effective_user.full_name, "/unpin", details=f"Unpinned {update.message.reply_to_message.message_id}")
    except TelegramError as e:
        await send_and_schedule_delete(update, context, f"Fehler beim Unpin: {e}")


# ---------------------------
# Locks + AutoMod
# ---------------------------
@check_permission("can_configure")
async def lock_feature(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = load_config()
    locks = cfg.get("locks", {}) or {}

    if not context.args:
        await send_and_schedule_delete(update, context, "Usage: /lock links|media|stickers")
        return

    key = context.args[0].strip().lower()
    if key not in ("links", "media", "stickers"):
        await send_and_schedule_delete(update, context, "Nur: links, media, stickers")
        return

    locks[key] = True
    cfg["locks"] = locks
    save_config(cfg)

    await short_ack(update, context, f"🔒 {key} gesperrt.")
    await admin_log(update, context, f"🔒 <b>LOCK</b> {escape(key)} durch <b>{escape(update.effective_user.full_name)}</b>")
    log_command(update.effective_user.id, update.effective_user.full_name, "/lock", details=key)


@check_permission("can_configure")
async def unlock_feature(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = load_config()
    locks = cfg.get("locks", {}) or {}

    if not context.args:
        await send_and_schedule_delete(update, context, "Usage: /unlock links|media|stickers")
        return

    key = context.args[0].strip().lower()
    if key not in ("links", "media", "stickers"):
        await send_and_schedule_delete(update, context, "Nur: links, media, stickers")
        return

    locks[key] = False
    cfg["locks"] = locks
    save_config(cfg)

    await short_ack(update, context, f"🔓 {key} entsperrt.")
    await admin_log(update, context, f"🔓 <b>UNLOCK</b> {escape(key)} durch <b>{escape(update.effective_user.full_name)}</b>")
    log_command(update.effective_user.id, update.effective_user.full_name, "/unlock", details=key)


async def locks_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = load_config()
    locks = cfg.get("locks", {}) or {}
    text = (
        "🔧 <b>Locks</b>\n"
        f"Links: <b>{'ON' if locks.get('links') else 'OFF'}</b>\n"
        f"Media: <b>{'ON' if locks.get('media') else 'OFF'}</b>\n"
        f"Stickers: <b>{'ON' if locks.get('stickers') else 'OFF'}</b>\n"
    )
    await send_and_schedule_delete(update, context, text, parse_mode="HTML")


async def handle_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Speichert User sofort beim Beitritt -> du hast die IDs, auch wenn sie noch nicht schreiben.
    """
    if not update.message or not update.message.new_chat_members:
        return
    chat_id = update.effective_chat.id if update.effective_chat else None
    for u in update.message.new_chat_members:
        register_user_seen(u, chat_id)


async def automod_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if not update.effective_chat or update.effective_chat.type not in ("group", "supergroup"):
        return
    if not update.effective_user or update.effective_user.is_bot:
        return

    register_user_seen(update.effective_user, update.effective_chat.id)

    if is_admin_or_allowed(update):
        return

    cfg = load_config()
    locks = cfg.get("locks", {}) or {}

    if locks.get("stickers") and update.message.sticker:
        try:
            await update.message.delete()
        except TelegramError:
            pass
        return

    if locks.get("media"):
        if any([update.message.photo, update.message.video, update.message.document, update.message.animation, update.message.audio, update.message.voice]):
            try:
                await update.message.delete()
            except TelegramError:
                pass
            return

    if locks.get("links") and contains_link(update):
        whitelist = cfg.get("link_whitelist", []) or []
        text = update.message.text or update.message.caption or ""
        domains = extract_domains(text)
        allowed = any(any(w.lower() in d for w in whitelist) for d in domains) if whitelist else False
        if not allowed:
            try:
                await update.message.delete()
            except TelegramError:
                pass
            return

    if bool(cfg.get("antispam_enabled", False)):
        flood_limit = int(cfg.get("flood_limit", 5) or 5)
        window_seconds = int(cfg.get("flood_window_seconds", 10) or 10)

        now_ts = datetime.now(TZ).timestamp()
        dq = FLOOD_TRACKER[update.effective_chat.id][update.effective_user.id]
        dq.append(now_ts)
        while dq and (now_ts - dq[0]) > window_seconds:
            dq.popleft()

        if len(dq) >= flood_limit:
            try:
                await update.message.delete()
            except TelegramError:
                pass

            mute_td = timedelta(minutes=5)
            until = datetime.now(TZ) + mute_td
            try:
                permissions = ChatPermissions(can_send_messages=False)
                await context.bot.restrict_chat_member(
                    chat_id=update.effective_chat.id,
                    user_id=update.effective_user.id,
                    permissions=permissions,
                    until_date=until,
                )
            except TelegramError:
                pass

            chat_title = update.effective_chat.title or "der Gruppe"
            await dm_user(context, update.effective_user.id, f"🔇 <b>Auto-Mute</b>\nGruppe: <b>{escape(chat_title)}</b>\nDauer: <b>5m</b>\nGrund: Flood/Spam")
            await admin_log(update, context, f"🚨 <b>FLOOD</b> Auto-mute <code>{update.effective_user.id}</code> (5m)")

            dq.clear()


# ---------------------------
# Bot Start
# ---------------------------
if __name__ == "__main__":
    config = load_config()
    token = config.get("bot_token")

    if not token:
        logger.info("Bot token not found, bot is disabled.")
        raise SystemExit(0)

    app = ApplicationBuilder().token(token).build()

    # ✅ Minecraft (separat) registrieren: /player + Status-Job
    if register_minecraft is not None:
        try:
            register_minecraft(app)
            logger.info("Minecraft bridge registered (commands + status job).")
        except Exception as e:
            logger.error(f"Failed to register Minecraft bridge: {e}")
    else:
        logger.warning("minecraft_bridge.py not found or failed to import – Minecraft features disabled.")

    # ✅ Track ALLES (auch Commands) ganz früh (Registry)
    app.add_handler(MessageHandler(filters.ALL, track_user_activity), group=-50)

    # ✅ Reaction Updates: wer reagiert (likes_given)
    if MessageReactionHandler is not None:
        try:
            app.add_handler(MessageReactionHandler(log_reaction_update), group=-45)
        except Exception:
            pass

    # ✅ Reaction Count Updates: Counts pro Message (likes received)
    if MessageReactionCountHandler is not None:
        try:
            app.add_handler(MessageReactionCountHandler(log_reaction_count_update), group=-44)
        except Exception:
            pass

    # ✅ Message-Logging früh, damit auch gelöschte Messages (Automod) erfasst werden
    app.add_handler(MessageHandler(filters.ALL, log_user_message), group=-40)

    # IMPORTANT: delete commands AFTER handlers, not before
    app.add_handler(MessageHandler(filters.COMMAND, handle_slash_commands), group=99)

    # Track joins (Registry)
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_members), group=0)

    # Help
    app.add_handler(CommandHandler("help", help_command))

    # ID Tools
    app.add_handler(CommandHandler("id", get_id))
    app.add_handler(CommandHandler("chatid", get_chat_id))
    app.add_handler(CommandHandler("userid", get_user_id))
    app.add_handler(CommandHandler("topicid", get_topic_id))
    app.add_handler(CommandHandler("whois", whois))

    # Admin setup
    app.add_handler(CommandHandler("setadmingroup", set_admin_group))
    app.add_handler(CommandHandler("locks", locks_status))

    # Warn
    app.add_handler(CommandHandler("warn", warn_user))
    app.add_handler(CommandHandler("warnings", get_warnings))
    app.add_handler(CommandHandler("unwarn", unwarn_user))
    app.add_handler(CommandHandler("clearwarnings", clear_warnings))

    # Kick/Ban/Mute
    app.add_handler(CommandHandler("kick", kick_user))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))
    app.add_handler(CommandHandler("mute", mute_user))
    app.add_handler(CommandHandler("unmute", unmute_user))

    # Message Tools
    app.add_handler(CommandHandler("del", delete_message))
    app.add_handler(CommandHandler("purge", purge_messages))
    app.add_handler(CommandHandler("pin", pin_message))
    app.add_handler(CommandHandler("unpin", unpin_message))

    # Locks
    app.add_handler(CommandHandler("lock", lock_feature))
    app.add_handler(CommandHandler("unlock", unlock_feature))

    # Auto-Mod Listener (low priority)
    app.add_handler(MessageHandler(~filters.COMMAND, automod_handler), group=1)

    logger.info("Bot is running...")
    # allowed_updates sicherheitshalber explizit (Reaction Updates kommen sonst ggf. nicht an)
    app.run_polling(allowed_updates=Update.ALL_TYPES)
