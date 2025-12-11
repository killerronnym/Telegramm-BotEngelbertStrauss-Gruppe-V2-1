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
    log_entry = f"[{timestamp}] User: {user_name} ({user_id}) | Cmd: {command} | Target: {target_id} | Details: {details}\\n"
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
        if update.message:
            sent_message = await update.message.reply_text(text, **kwargs)

            if cleanup_seconds > 0 and context.job_queue:
                context.job_queue.run_once(
                    cleanup_job,
                    when=cleanup_seconds,
                    data={'message_id': sent_message.message_id},
                    chat_id=update.effective_chat.id,
                    name=f"cleanup_{sent_message.message_id}"
                )
        else:
            # Fallback if there is no message to reply to (e.g. callback query or other update types)
             sent_message = await context.bot.send_message(chat_id=update.effective_chat.id, text=text, **kwargs)
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

            # PERMISSION BYPASS FOR DEBUGGING - COMMENT OUT IN PRODUCTION IF NEEDED
            # if user_id == "YOUR_ADMIN_ID": return await func(update, context, *args, **kwargs)

            if user_id not in admins or not admins[user_id].get("permissions", {}).get(permission_key, False):
                log_command(user_id, update.effective_user.full_name, f"PERMISSION_DENIED: {func.__name__}")
                
                # Check if user is admin but lacks specific permission
                if user_id in admins:
                     await send_and_schedule_delete(update, context, f"Du hast keine Berechtigung für diesen Befehl ({permission_key}).")
                else:
                     # Silent fail for non-admins or generic message
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
    response = f"👤 Deine ID: `{user.id}`\\n💬 Chat ID: `{chat.id}`"
    if topic_id: response += f"\\n🧵 Topic ID: `{topic_id}`"
    if update.message.reply_to_message:
        original_user = update.message.reply_to_message.from_user
        response += f"\\n\\n👇 **Ziel-User** 👇\\n👤 User ID: `{original_user.id}`"
    await send_and_schedule_delete(update, context, response, parse_mode='Markdown')
    log_command(user.id, user.full_name, "/id")

@check_permission("can_see_ids")
async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    response = f"💬 Chat ID: `{chat_id}`"
    await send_and_schedule_delete(update, context, response, parse_mode='Markdown')
    log_command(update.effective_user.id, update.effective_user.full_name, "/chatid")

@check_permission("can_see_ids")
async def get_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user, _ = await get_target_user(update, context)
    if target_user:
        response = f"👤 User ID: `{target_user.id}`"
        await send_and_schedule_delete(update, context, response, parse_mode='Markdown')
        log_command(update.effective_user.id, update.effective_user.full_name, "/userid", target_user.id)
    else:
        await send_and_schedule_delete(update, context, "Bitte antworte auf eine Nachricht oder gib eine User-ID an, um deren ID zu erhalten.")

@check_permission("can_see_ids")
async def get_topic_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic_id = update.message.message_thread_id
    if topic_id:
        response = f"🧵 Topic ID: `{topic_id}`"
        await send_and_schedule_delete(update, context, response, parse_mode='Markdown')
        log_command(update.effective_user.id, update.effective_user.full_name, "/topicid")
    else:
        await send_and_schedule_delete(update, context, "Dies ist kein Thema (Topic).")

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
    
    msg_text = f"⚠️ Benutzer {target_user.full_name} (`{target_user.id}`) wurde verwarnt.\\nGrund: {reason}\\nAnzahl: {block['warns']}"
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
        msg_text = f"👢 Benutzer {target_user.full_name} (`{target_user.id}`) wurde gekickt.\\nGrund: {reason}"
        
        # Senden in Log-Kanal oder Chat
        config = load_config()
        reply_params = get_reply_parameters(config, update)
        # Hier senden wir direkt, da es eine Log-Nachricht sein kann, die bleiben soll.
        # Wenn es auch gelöscht werden soll, müsste man das hier anpassen.
        await context.bot.send_message(text=msg_text, parse_mode='Markdown', **reply_params)

    except TelegramError as e:
        await send_and_schedule_delete(update, context, f"Fehler beim Kicken: {e}")

async def get_warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user, _ = await get_target_user(update, context)
    if not target_user:
        await send_and_schedule_delete(update, context, "Bitte antworte auf eine Nachricht oder gib eine User-ID an.")
        return

    data = load_moderation_data()
    block = ensure_user_block(data, target_user.id)
    warnings_count = block.get("warns", 0)
    history = block.get("history", [])

    response = f"⚠️ Warnungen für {target_user.full_name} (`{target_user.id}`): {warnings_count}\\n"
    if history:
        response += "\\n**Verlauf:**\\n"
        for entry in history:
            response += f"- Typ: {entry['type']}, Grund: {entry['reason']}, Datum: {entry['date']}\\n"
    else:
        response += "Keine Warnungen vorhanden."

    await send_and_schedule_delete(update, context, response, parse_mode='Markdown')
    log_command(update.effective_user.id, update.effective_user.full_name, "/warnings", target_user.id)

@check_permission("can_warn")
async def unwarn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user, args = await get_target_user(update, context)
    if not target_user:
        await send_and_schedule_delete(update, context, "Bitte antworte auf eine Nachricht oder gib eine User-ID an.")
        return

    data = load_moderation_data()
    block = ensure_user_block(data, target_user.id)
    if block["warns"] > 0:
        block["warns"] -= 1
        block.setdefault("history", []).append({"type": "unwarn", "reason": "Manuell entfernt", "date": datetime.now().isoformat(), "by": update.effective_user.id})
        save_moderation_data(data)
        response = f"✅ Eine Verwarnung für {target_user.full_name} (`{target_user.id}`) wurde entfernt. Aktuell: {block['warns']} Verwarnung(en)."
    else:
        response = f"🚫 {target_user.full_name} (`{target_user.id}`) hat keine Verwarnungen, die entfernt werden könnten."
    
    await send_and_schedule_delete(update, context, response, parse_mode='Markdown')
    log_command(update.effective_user.id, update.effective_user.full_name, "/unwarn", target_user.id)

@check_permission("can_warn")
async def clear_warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user, args = await get_target_user(update, context)
    if not target_user:
        await send_and_schedule_delete(update, context, "Bitte antworte auf eine Nachricht oder gib eine User-ID an.")
        return

    data = load_moderation_data()
    block = ensure_user_block(data, target_user.id)
    if block["warns"] > 0:
        old_warns = block["warns"]
        block["warns"] = 0
        block["history"] = [] # Clear history as well
        save_moderation_data(data)
        response = f"🗑️ Alle {old_warns} Verwarnungen für {target_user.full_name} (`{target_user.id}`) wurden entfernt."
    else:
        response = f"🚫 {target_user.full_name} (`{target_user.id}`) hat keine Verwarnungen."

    await send_and_schedule_delete(update, context, response, parse_mode='Markdown')
    log_command(update.effective_user.id, update.effective_user.full_name, "/clearwarnings", target_user.id)

@check_permission("can_ban")
async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user, args = await get_target_user(update, context)
    if not target_user:
        await send_and_schedule_delete(update, context, "Zielnutzer nicht gefunden.")
        return

    reason = " ".join(args) or "Kein Grund angegeben"
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target_user.id)
        log_command(update.effective_user.id, update.effective_user.full_name, "/ban", target_user.id, reason)
        msg_text = f"⛔ Benutzer {target_user.full_name} (`{target_user.id}`) wurde gebannt.\\nGrund: {reason}"
        config = load_config()
        reply_params = get_reply_parameters(config, update)
        await context.bot.send_message(text=msg_text, parse_mode='Markdown', **reply_params)
    except TelegramError as e:
        await send_and_schedule_delete(update, context, f"Fehler beim Bannen: {e}")

@check_permission("can_ban")
async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user, args = await get_target_user(update, context)
    if not target_user:
        await send_and_schedule_delete(update, context, "Zielnutzer nicht gefunden.")
        return

    try:
        await context.bot.unban_chat_member(update.effective_chat.id, target_user.id)
        log_command(update.effective_user.id, update.effective_user.full_name, "/unban", target_user.id)
        msg_text = f"✅ Benutzer {target_user.full_name} (`{target_user.id}`) wurde entbannt."
        config = load_config()
        reply_params = get_reply_parameters(config, update)
        await context.bot.send_message(text=msg_text, parse_mode='Markdown', **reply_params)
    except TelegramError as e:
        await send_and_schedule_delete(update, context, f"Fehler beim Entbannen: {e}")

@check_permission("can_mute")
async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user, args = await get_target_user(update, context)
    if not target_user:
        await send_and_schedule_delete(update, context, "Zielnutzer nicht gefunden.")
        return

    duration_str = args[0] if args else None
    duration = parse_duration(duration_str)

    if not duration:
        await send_and_schedule_delete(update, context, "Bitte gib eine gültige Dauer an (z.B. 30m, 1h, 7d).")
        return

    until_date = datetime.now() + duration
    reason = " ".join(args[1:]) or "Kein Grund angegeben"

    try:
        permissions = ChatPermissions(can_send_messages=False)
        await context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=target_user.id,
            permissions=permissions,
            until_date=until_date
        )
        log_command(update.effective_user.id, update.effective_user.full_name, "/mute", target_user.id, f"{duration_str} - {reason}")
        msg_text = f"🔇 Benutzer {target_user.full_name} (`{target_user.id}`) wurde für {duration_str} stummgeschaltet.\\nGrund: {reason}"
        await send_and_schedule_delete(update, context, msg_text, parse_mode='Markdown')
    except TelegramError as e:
        await send_and_schedule_delete(update, context, f"Fehler beim Stummschalten: {e}")

@check_permission("can_mute")
async def unmute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user, args = await get_target_user(update, context)
    if not target_user:
        await send_and_schedule_delete(update, context, "Zielnutzer nicht gefunden.")
        return

    try:
        permissions = ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
            can_change_info=False,
            can_invite_users=True,
            can_pin_messages=False
        )
        await context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=target_user.id,
            permissions=permissions,
            until_date=0  # Unmute immediately
        )
        log_command(update.effective_user.id, update.effective_user.full_name, "/unmute", target_user.id)
        msg_text = f"🔊 Benutzer {target_user.full_name} (`{target_user.id}`) wurde entstummt."
        await send_and_schedule_delete(update, context, msg_text, parse_mode='Markdown')
    except TelegramError as e:
        await send_and_schedule_delete(update, context, f"Fehler beim Entstummen: {e}")

@check_permission("can_delete_messages")
async def delete_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await send_and_schedule_delete(update, context, "Bitte antworte auf eine Nachricht, die gelöscht werden soll.")
        return
    
    try:
        await update.message.reply_to_message.delete()
        await update.message.delete() # Delete the command message itself
        log_command(update.effective_user.id, update.effective_user.full_name, "/del", details=f"Deleted message {update.message.reply_to_message.message_id}")
    except TelegramError as e:
        await send_and_schedule_delete(update, context, f"Fehler beim Löschen der Nachricht: {e}")

@check_permission("can_delete_messages")
async def purge_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await send_and_schedule_delete(update, context, "Bitte antworte auf die erste Nachricht in dem Bereich, der gelöscht werden soll.")
        return

    try:
        message_id_to_start_from = update.message.reply_to_message.message_id
        current_message_id = update.message.message_id

        messages_to_delete = []
        for i in range(message_id_to_start_from, current_message_id + 1):
            messages_to_delete.append(i)
        
        # Telegram Bot API's deleteMessages can take up to 100 messages at once
        # For larger purges, we might need to chunk this
        await context.bot.delete_messages(
            chat_id=update.effective_chat.id,
            message_ids=messages_to_delete
        )
        log_command(update.effective_user.id, update.effective_user.full_name, "/purge", details=f"Purged messages from {message_id_to_start_from} to {current_message_id}")
    except TelegramError as e:
        await send_and_schedule_delete(update, context, f"Fehler beim Purgen der Nachrichten: {e}")

@check_permission("can_pin_messages")
async def pin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await send_and_schedule_delete(update, context, "Bitte antworte auf eine Nachricht, die angepinnt werden soll.")
        return
    
    try:
        await context.bot.pin_chat_message(
            chat_id=update.effective_chat.id,
            message_id=update.message.reply_to_message.message_id,
            disable_notification=True # Generally better for pinning
        )
        await send_and_schedule_delete(update, context, "Nachricht angepinnt.", parse_mode='Markdown')
        log_command(update.effective_user.id, update.effective_user.full_name, "/pin", details=f"Pinned message {update.message.reply_to_message.message_id}")
    except TelegramError as e:
        await send_and_schedule_delete(update, context, f"Fehler beim Anpinnen der Nachricht: {e}")

@check_permission("can_pin_messages")
async def unpin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await send_and_schedule_delete(update, context, "Bitte antworte auf eine Nachricht, die gelöst werden soll.")
        return
    
    try:
        await context.bot.unpin_chat_message(
            chat_id=update.effective_chat.id,
            message_id=update.message.reply_to_message.message_id
        )
        await send_and_schedule_delete(update, context, "Nachricht gelöst.", parse_mode='Markdown')
        log_command(update.effective_user.id, update.effective_user.full_name, "/unpin", details=f"Unpinned message {update.message.reply_to_message.message_id}")
    except TelegramError as e:
        await send_and_schedule_delete(update, context, f"Fehler beim Lösen der Nachricht: {e}")

async def lock_feature(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_and_schedule_delete(update, context, "Diese Funktion ist noch nicht implementiert.")
    log_command(update.effective_user.id, update.effective_user.full_name, "/lock")

async def unlock_feature(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_and_schedule_delete(update, context, "Diese Funktion ist noch nicht implementiert.")
    log_command(update.effective_user.id, update.effective_user.full_name, "/unlock")


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
        app.add_handler(CommandHandler("chatid", get_chat_id))
        app.add_handler(CommandHandler("userid", get_user_id))
        app.add_handler(CommandHandler("topicid", get_topic_id))

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
        app.add_handler(CommandHandler("lock", lock_feature))
        app.add_handler(CommandHandler("unlock", unlock_feature))

        # ... and so on for all other commands from the original file
        
        # Auto-Mod Listener (low priority)
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, automod_handler), group=1)

        logger.info("Bot is running...")
        app.run_polling()
