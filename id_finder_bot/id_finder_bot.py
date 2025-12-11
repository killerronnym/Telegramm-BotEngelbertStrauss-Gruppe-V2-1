import logging
import os
import json
import re
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict, deque

from telegram import Update, ChatPermissions
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    JobQueue
)
from telegram.error import TelegramError

# --- Logging Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Configuration & Paths ---
CONFIG_FILE = 'id_finder_config.json'
COMMAND_LOG_FILE = 'id_finder_command.log'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

MODERATION_DATA_FILE = os.path.join(DATA_DIR, "moderation_data.json")
ADMINS_FILE = os.path.join(os.path.dirname(BASE_DIR), 'dashboard', 'admins.json')


# ---------------------------
# Load/Save Helpers
# ---------------------------

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return {}

def save_config(config: dict):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving config: {e}")

def load_moderation_data():
    if not os.path.exists(MODERATION_DATA_FILE):
        return {}
    try:
        with open(MODERATION_DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading moderation data: {e}")
        return {}

def save_moderation_data(data):
    try:
        with open(MODERATION_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving moderation data: {e}")

def load_admins():
    if not os.path.exists(ADMINS_FILE):
        return {}
    try:
        with open(ADMINS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading admin data: {e}")
        return {}

def log_command(user_id, user_name, command, target_id=None, details=None):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] User: {user_name} ({user_id}) | Cmd: {command} | Target: {target_id} | Details: {details}\n"
    try:
        with open(COMMAND_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_entry)
    except Exception as e:
        logger.error(f"Error writing to command log: {e}")


# ---------------------------
# NEW: Cleanup Helpers
# ---------------------------

async def cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    """Deletes the message specified in the job context."""
    try:
        await context.bot.delete_message(
            chat_id=context.job.chat_id,
            message_id=context.job.data['message_id']
        )
    except TelegramError as e:
        # Ignore if message is already deleted
        if "message to delete not found" not in e.message.lower():
            logger.warning(f"Could not delete message {context.job.data['message_id']}: {e}")

async def send_and_schedule_delete(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, **kwargs):
    """Sends a message and schedules its deletion if configured."""
    config = load_config()
    cleanup_seconds = config.get('bot_message_cleanup_seconds', 0)

    try:
        sent_message = await update.message.reply_text(text, **kwargs)

        if cleanup_seconds > 0 and context.job_queue:
            context.job_queue.run_once(
                cleanup_job,
                when=cleanup_seconds,
                data={'message_id': sent_message.message_id},
                chat_id=update.effective_chat.id,
                name=f"cleanup_{sent_message.message_id}"
            )
    except TelegramError as e:
        logger.error(f"Failed to send or schedule cleanup for message: {e}")


# ---------------------------
# Utility
# ---------------------------

def get_reply_parameters(config, update: Update):
    log_topic_id = config.get('log_topic_id')
    main_group_id = config.get('main_group_id')

    try:
        log_topic_id = int(log_topic_id) if log_topic_id else None
        main_group_id = int(main_group_id) if main_group_id else None
    except (ValueError, TypeError):
        log_topic_id = None
        main_group_id = None

    if log_topic_id and main_group_id:
        return {"chat_id": main_group_id, "message_thread_id": log_topic_id}
    else:
        return {
            "chat_id": update.effective_chat.id,
            "message_thread_id": update.effective_message.message_thread_id if update.effective_message else None
        }

async def get_target_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user = None
    args = list(context.args)

    if update.message and update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
    elif args:
        try:
            user_id = int(args[0])
            try:
                chat_id = update.effective_chat.id
                member = await context.bot.get_chat_member(chat_id, user_id)
                target_user = member.user
                args = args[1:]
            except Exception:
                pass
        except ValueError:
            pass

    return target_user, args

def parse_duration(token: str) -> timedelta | None:
    if not token: return None
    m = re.match(r'^(\d+)([mhd])$', token.strip().lower())
    if not m: return None
    amount, unit = int(m.group(1)), m.group(2)
    if unit == 'm': return timedelta(minutes=amount)
    if unit == 'h': return timedelta(hours=amount)
    if unit == 'd': return timedelta(days=amount)
    return None

def ensure_user_block(data: dict, user_id: int):
    uid = str(user_id)
    if uid not in data:
        data[uid] = {"warns": 0, "history": []}
    return data[uid]

# ---------------------------
# Permission Decorator & Global Handler
# ---------------------------

async def handle_slash_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Global handler to delete any message that is a slash command if enabled."""
    config = load_config()
    if config.get('delete_commands', False) and update.message:
        try:
            await update.message.delete()
        except TelegramError as e:
            if "message to delete not found" not in e.message.lower():
                 logger.warning(f"Could not delete command message {update.message.message_id}: {e}")


def check_permission(permission_key: str):
    def decorator(func):
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            if not update.effective_user or not update.message: return

            user_id = str(update.effective_user.id)
            admins = load_admins()

            if user_id not in admins or not admins[user_id].get("permissions", {}).get(permission_key, False):
                log_command(user_id, update.effective_user.full_name, f"PERMISSION_DENIED: {func.__name__}")
                await send_and_schedule_delete(update, context, "Du hast keine Berechtigung für diesen Befehl.")
                return

            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator

# ---------------------------
# In-Memory Flood Tracking
# ---------------------------
FLOOD_TRACKER = defaultdict(lambda: defaultdict(deque))

# ---------------------------
# Commands: All handlers updated to use send_and_schedule_delete
# ---------------------------

@check_permission("can_see_ids")
async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, chat, topic_id = update.message.from_user, update.effective_chat, update.message.message_thread_id
    response = f"👤 Deine ID: `{user.id}`\n💬 Chat ID: `{chat.id}`"
    if topic_id: response += f"\n🧵 Topic ID: `{topic_id}`"
    if update.message.reply_to_message:
        original_user = update.message.reply_to_message.from_user
        response += f"\n\n👇 **Ziel-User** 👇\n👤 User ID: `{original_user.id}`"
    await send_and_schedule_delete(update, context, response, parse_mode='Markdown')
    log_command(user.id, user.full_name, "/id")

# ... (The same modification applies to ALL other command handlers)

@check_permission("can_warn")
async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user, args = await get_target_user(update, context)
    if not target_user:
        await send_and_schedule_delete(update, context, "Bitte antworte auf eine Nachricht oder gib eine User-ID an.")
        return

    reason = " ".join(args) or "Kein Grund angegeben"
    data = load_moderation_data()
    block = ensure_user_block(data, target_user.id)
    block["warns"] = block.get("warns", 0) + 1
    block.setdefault("history", []).append({"type": "warn", "reason": reason, "date": datetime.now().isoformat(), "by": update.effective_user.id})
    save_moderation_data(data)

    log_command(update.effective_user.id, update.effective_user.full_name, "/warn", target_user.id, reason)
    
    msg_text = f"⚠️ Benutzer {target_user.full_name} (`{target_user.id}`) wurde verwarnt.\nGrund: {reason}\nAnzahl: {block['warns']}"
    await send_and_schedule_delete(update, context, msg_text, parse_mode='Markdown')

@check_permission("can_kick")
async def kick_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user, args = await get_target_user(update, context)
    if not target_user:
        await send_and_schedule_delete(update, context, "Zielnutzer nicht gefunden.")
        return

    reason = " ".join(args) or "Kein Grund angegeben"
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target_user.id)
        await context.bot.unban_chat_member(update.effective_chat.id, target_user.id)
        log_command(update.effective_user.id, update.effective_user.full_name, "/kick", target_user.id, reason)
        msg_text = f"👢 Benutzer {target_user.full_name} (`{target_user.id}`) wurde gekickt.\nGrund: {reason}"
        
        # Senden in Log-Kanal oder Chat
        config = load_config()
        reply_params = get_reply_parameters(config, update)
        # Hier senden wir direkt, da es eine Log-Nachricht sein kann, die bleiben soll.
        # Wenn es auch gelöscht werden soll, müsste man das hier anpassen.
        await context.bot.send_message(text=msg_text, parse_mode='Markdown', **reply_params)

    except TelegramError as e:
        await send_and_schedule_delete(update, context, f"Fehler beim Kicken: {e}")

# ... other commands adapted similarly ...

async def automod_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # This handler remains largely the same, but its replies should also be scheduled for deletion
    if not update.message or update.effective_chat.type not in ("group", "supergroup"): return
    
    user = update.effective_user
    if not user or user.is_bot: return
    
    # ... (existing automod logic)
    # Example for a reply:
    # await send_and_schedule_delete(update, context, "Your message was deleted due to...")


# ---------------------------
# Bot Start
# ---------------------------

if __name__ == "__main__":
    config = load_config()
    token = config.get("bot_token")

    if not token:
        logger.info("Bot token not found, bot is disabled.")
    else:
        # NEW: Initialize JobQueue
        job_queue = JobQueue()
        app = ApplicationBuilder().token(token).job_queue(job_queue).build()

        # NEW: Global handler for slash commands (high priority)
        app.add_handler(MessageHandler(filters.COMMAND, handle_slash_commands), group=-1)

        # Register all your command handlers here
        # ID Tools
        app.add_handler(CommandHandler("id", get_id))
        app.add_handler(CommandHandler("chatid", get_chat_id)) # Assuming this exists
        app.add_handler(CommandHandler("userid", get_user_id)) # Assuming this exists
        app.add_handler(CommandHandler("topicid", get_topic_id)) # Assuming this exists

        # Warn
        app.add_handler(CommandHandler("warn", warn_user))
        app.add_handler(CommandHandler("warnings", get_warnings)) # Assuming this exists
        app.add_handler(CommandHandler("unwarn", unwarn_user)) # Assuming this exists
        app.add_handler(CommandHandler("clearwarnings", clear_warnings)) # Assuming this exists

        # Kick/Ban/Mute
        app.add_handler(CommandHandler("kick", kick_user))
        app.add_handler(CommandHandler("ban", ban_user)) # Assuming this exists
        app.add_handler(CommandHandler("unban", unban_user)) # Assuming this exists
        app.add_handler(CommandHandler("mute", mute_user)) # Assuming this exists
        app.add_handler(CommandHandler("unmute", unmute_user)) # Assuming this exists
        
        # Message Tools
        app.add_handler(CommandHandler("del", delete_message)) # Assuming this exists
        app.add_handler(CommandHandler("purge", purge_messages)) # Assuming this exists
        app.add_handler(CommandHandler("pin", pin_message)) # Assuming this exists
        app.add_handler(CommandHandler("unpin", unpin_message)) # Assuming this exists
        app.add_handler(CommandHandler("lock", lock_feature)) # Assuming this exists
        app.add_handler(CommandHandler("unlock", unlock_feature)) # Assuming this exists

        # ... and so on for all other commands from the original file
        
        # Auto-Mod Listener (low priority)
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, automod_handler), group=1)

        logger.info("Bot is running...")
        app.run_polling()
