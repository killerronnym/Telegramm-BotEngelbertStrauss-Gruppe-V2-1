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
    ZoneInfo = None

from telegram import Update, ChatPermissions, MessageEntity, ChatMemberUpdated
from telegram.error import TelegramError, Forbidden
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ChatMemberHandler,
    filters,
    ContextTypes,
)

# --- Configuration & Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)

AVATAR_DIR = os.path.join(DATA_DIR, "avatars")
os.makedirs(AVATAR_DIR, exist_ok=True)

GROUP_EVENTS_FILE = os.path.join(DATA_DIR, "group_events.jsonl")
USER_REGISTRY_FILE = os.path.join(DATA_DIR, "user_registry.json")
CONFIG_FILE = os.path.join(BASE_DIR, "id_finder_config.json")

_FILE_LOCK = threading.Lock()
TZ = ZoneInfo("Europe/Berlin")

# --- Logging ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Helpers ---
def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")

def save_json_file(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def load_json_file(path: str, default):
    if not os.path.exists(path): return default
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except: return default

def _append_jsonl(path: str, obj: Dict[str, Any]):
    line = json.dumps(obj, ensure_ascii=False)
    with _FILE_LOCK:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

# --- Avatar Downloader ---
async def download_user_avatar(user, context):
    uid = str(user.id)
    path = os.path.join(AVATAR_DIR, f"{uid}.jpg")
    # Nur einmal am Tag prüfen oder wenn Datei fehlt
    if os.path.exists(path): return f"/data/avatars/{uid}.jpg"
    
    try:
        photos = await context.bot.get_user_profile_photos(user.id, limit=1)
        if photos.total_count > 0:
            file = await context.bot.get_file(photos.photos[0][-1].file_id)
            await file.download_to_drive(path)
            return f"/data/avatars/{uid}.jpg"
    except Exception as e:
        logger.error(f"Avatar download failed for {uid}: {e}")
    return None

# --- User Registry ---
def register_user(user, chat_id=None):
    reg = load_json_file(USER_REGISTRY_FILE, {"users": {}})
    uid = str(user.id)
    entry = reg["users"].get(uid, {})
    entry.update({
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "last_seen": now_iso()
    })
    entry.setdefault("first_seen", now_iso())
    cids = entry.get("chat_ids", [])
    if chat_id and chat_id not in cids: cids.append(chat_id)
    entry["chat_ids"] = cids
    reg["users"][uid] = entry
    save_json_file(USER_REGISTRY_FILE, reg)

# --- Handlers ---
async def handle_chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.chat_member
    if not result: return
    
    user = result.from_user
    chat = result.chat
    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status
    
    event_type = None
    if old_status in ['left', 'kicked'] and new_status in ['member', 'creator', 'administrator']:
        event_type = "join"
    elif old_status in ['member', 'administrator', 'creator'] and new_status in ['left', 'kicked']:
        event_type = "leave"
        
    if event_type:
        register_user(user, chat.id)
        avatar_url = await download_user_avatar(user, context)
        
        event = {
            "ts": now_iso(),
            "type": event_type,
            "user_id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "chat_id": chat.id,
            "chat_title": chat.title,
            "avatar_url": avatar_url
        }
        _append_jsonl(GROUP_EVENTS_FILE, event)
        logger.info(f"Event: {event_type} - User: {user.full_name} ({user.id})")

async def track_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user:
        register_user(update.effective_user, update.effective_chat.id if update.effective_chat else None)

# --- Bot Initialization ---
if __name__ == "__main__":
    config = load_json_file(CONFIG_FILE, {})
    token = config.get("bot_token")
    if not token: raise SystemExit("No Token!")

    app = ApplicationBuilder().token(token).build()
    
    # Handlers
    app.add_handler(ChatMemberHandler(handle_chat_member_update, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.ALL, track_activity), group=-1)
    
    # ID Finder Commands
    async def get_id(u, c): await u.message.reply_text(f"User ID: {u.effective_user.id}\nChat ID: {u.effective_chat.id}")
    app.add_handler(CommandHandler("id", get_id))

    logger.info("Bot started...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
