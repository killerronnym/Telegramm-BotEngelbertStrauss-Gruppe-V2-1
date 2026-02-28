import logging
import os
import json
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

# --- Paths ---
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BOT_DIR))
# Import models from web_dashboard.app.models
sys.path.append(PROJECT_ROOT)

from web_dashboard.app.models import db, BotSettings, IDFinderAdmin, IDFinderUser, IDFinderMessage, TopicMapping, Broadcast, AutoCleanupTask, IDFinderWarning
from flask import Flask

# Import shared utils for DB URL resolution and app context
from shared_bot_utils import get_db_url, get_bot_config, is_bot_active, get_shared_flask_app

flask_app = get_shared_flask_app()

# --- Logging ---
LOG_FILE = os.path.join(BOT_DIR, "id_finder_bot.log")
# Ensure logging uses UTF-8 even on Windows
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Force UTF-8 for stdout/stderr if possible
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

try:
    from telegram import Update, ForumTopic, ChatPermissions
    from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, Application
    from telegram.constants import ParseMode
except ImportError:
    logger.error("Erforderliche Bibliothek 'python-telegram-bot' nicht gefunden!")
    sys.exit(1)

from shared_bot_utils import get_bot_config

# --- Config Management ---
def get_config_from_db():
    try:
        return get_bot_config("id_finder")
    except Exception as e:
        logger.error(f"Fehler beim Laden der Konfiguration aus DB: {e}")
    return None

# --- Auto Cleanup Task ---
async def process_cleanup_tasks(context: ContextTypes.DEFAULT_TYPE):
    if not is_bot_active('id_finder'): return
    """
    Sucht nach abgelaufenen Bot-Meldungen und löscht diese aus dem Chat.
    """
    try:
        with flask_app.app_context():
            now = datetime.utcnow()
            tasks = AutoCleanupTask.query.filter(
                AutoCleanupTask.status == 'pending',
                AutoCleanupTask.cleanup_at <= now
            ).all()

            for task in tasks:
                try:
                    logger.info(f"Lösche alte Bot-Meldung: Chat {task.chat_id}, Msg {task.message_id}")
                    await context.bot.delete_message(chat_id=task.chat_id, message_id=task.message_id)
                except Exception as e:
                    logger.debug(f"Konnte Nachricht nicht löschen (evtl. schon weg): {e}")
                
                task.status = 'done'
            
            db.session.commit()
            
            # Optional: Erledigte Aufgaben ganz löschen
            AutoCleanupTask.query.filter_by(status='done').delete()
            db.session.commit()
            
    except Exception as e:
        logger.error(f"Fehler bei Auto-Cleanup: {e}")

# --- Broadcast Engine ---
async def check_and_send_broadcasts(context: ContextTypes.DEFAULT_TYPE):
    # Broadcast-Manager läuft immer, solange der Bot-Prozess aktiv ist.
    # (Auch wenn das ID-Finder Modul im Dashboard auf 'AUS' steht)
    """
    Prüft die Datenbank nach fälligen Broadcasts und versendet sie.
    """
    config = get_config_from_db()
    if not config: return
    
    main_group_id = config.get('main_group_id')
    if not main_group_id: return

    try:
        with flask_app.app_context():
            now = datetime.utcnow()
            pending_broadcasts = Broadcast.query.filter(
                Broadcast.status == 'pending',
                Broadcast.scheduled_at <= now
            ).all()

            for b in pending_broadcasts:
                logger.info(f"Sende fälligen Broadcast: {b.id}")
                try:
                    chat_id = main_group_id
                    thread_id = int(b.topic_id) if b.topic_id and str(b.topic_id).isdigit() else None
                    
                    msg = None
                    media_files = []
                    if b.media_files:
                        try:
                            media_files = json.loads(b.media_files)
                        except:
                            logger.error(f"Fehler beim Parsen der media_files für Broadcast {b.id}")

                    # 1. Fall: Album (Mehrere Bilder/Videos)
                    if media_files:
                        from telegram import InputMediaPhoto, InputMediaVideo
                        media_group = []
                        for i, rel_path in enumerate(media_files):
                            fpath = os.path.join(PROJECT_ROOT, 'web_dashboard', 'app', 'static', rel_path)
                            if os.path.exists(fpath):
                                cap = b.text if i == 0 else None # Caption nur beim ersten Bild
                                if rel_path.lower().endswith(('.mp4', '.mov', '.avi')):
                                    media_group.append(InputMediaVideo(open(fpath, 'rb'), caption=cap, parse_mode=ParseMode.HTML))
                                else:
                                    media_group.append(InputMediaPhoto(open(fpath, 'rb'), caption=cap, parse_mode=ParseMode.HTML))
                        
                        if media_group:
                            msgs = await context.bot.send_media_group(
                                chat_id=chat_id, media=media_group,
                                message_thread_id=thread_id, disable_notification=b.silent_send
                            )
                            msg = msgs[0] if msgs else None

                    # 2. Fall: Einzelne Datei (kompatibel zu altem System)
                    elif b.media_path:
                        full_media_path = os.path.join(PROJECT_ROOT, 'web_dashboard', 'app', 'static', b.media_path)
                        if os.path.exists(full_media_path):
                            with open(full_media_path, 'rb') as f:
                                try:
                                    if b.media_type == 'image':
                                        msg = await context.bot.send_photo(
                                            chat_id=chat_id, photo=f, caption=b.text,
                                            message_thread_id=thread_id, disable_notification=b.silent_send,
                                            parse_mode=ParseMode.HTML
                                        )
                                    elif b.media_type == 'video':
                                        msg = await context.bot.send_video(
                                            chat_id=chat_id, video=f, caption=b.text,
                                            message_thread_id=thread_id, disable_notification=b.silent_send,
                                            parse_mode=ParseMode.HTML
                                        )
                                except Exception as he:
                                    if "Can't parse entities" in str(he):
                                        logger.warning(f"HTML Parse Fehler bei Broadcast {b.id}, versende als Plaintext.")
                                        f.seek(0)
                                        if b.media_type == 'image':
                                            msg = await context.bot.send_photo(chat_id=chat_id, photo=f, caption=b.text, message_thread_id=thread_id)
                                        else:
                                            msg = await context.bot.send_video(chat_id=chat_id, video=f, caption=b.text, message_thread_id=thread_id)
                                    else: raise he
                        else:
                            logger.error(f"Mediendatei nicht gefunden: {full_media_path}")
                            b.status = 'failed'
                            continue

                    # 3. Fall: Reiner Text
                    else:
                        try:
                            msg = await context.bot.send_message(
                                chat_id=chat_id, text=b.text,
                                message_thread_id=thread_id, disable_notification=b.silent_send,
                                parse_mode=ParseMode.HTML
                            )
                        except Exception as he:
                            if "Can't parse entities" in str(he):
                                logger.warning(f"HTML Parse Fehler bei Text-Broadcast {b.id}, versende als Plaintext.")
                                msg = await context.bot.send_message(chat_id=chat_id, text=b.text, message_thread_id=thread_id)
                            else: raise he
                    
                    # Nachricht anpinnen falls gewünscht
                    if b.pin_message and msg:
                        try:
                            await context.bot.pin_chat_message(chat_id=chat_id, message_id=msg.message_id)
                        except Exception as pe:
                            logger.error(f"Konnte Nachricht {msg.message_id} nicht anpinnen: {pe}")

                    b.status = 'sent'
                    logger.info(f"Broadcast {b.id} erfolgreich gesendet.")
                except Exception as e:
                    logger.error(f"Fehler beim Senden von Broadcast {b.id}: {e}")
                    b.status = 'failed'
                
            db.session.commit()
    except Exception as e:
        logger.error(f"Fehler in der Broadcast Engine: {e}")

# --- Activity Tracking ---
def db_log_message_sync(user_dict, chat_dict, msg_dict, config):
    try:
        with flask_app.app_context():
            now = datetime.utcnow()
            # Update User Registry
            db_user = IDFinderUser.query.filter_by(telegram_id=user_dict['id']).first()
            if not db_user:
                db_user = IDFinderUser(
                    telegram_id=user_dict['id'], username=user_dict['username'],
                    first_name=user_dict['first_name'], last_name=user_dict['last_name'],
                    language_code=user_dict['language_code'], is_bot=user_dict['is_bot'],
                    first_contact=now
                )
                db.session.add(db_user)
            else:
                db_user.username = user_dict['username']
                db_user.first_name = user_dict['first_name']
                db_user.last_name = user_dict['last_name']
                db_user.last_contact = now
            
            # Discover Topics
            if chat_dict['type'] in ["group", "supergroup"] and msg_dict.get('thread_id'):
                thread_id = msg_dict['thread_id']
                mapping = TopicMapping.query.filter_by(topic_id=thread_id).first()
                if not mapping:
                    db.session.add(TopicMapping(topic_id=thread_id, topic_name=msg_dict.get('topic_name', f"Topic {thread_id}")))

            # Log Message
            if msg_dict['is_command'] and config.get("message_logging_ignore_commands", True):
                db.session.commit()
                return

            db_msg = IDFinderMessage.query.filter_by(message_id=msg_dict['id'], chat_id=chat_dict['id']).first()
            if not db_msg:
                db_msg = IDFinderMessage(
                    telegram_user_id=user_dict['id'], message_id=msg_dict['id'],
                    chat_id=chat_dict['id'], message_thread_id=msg_dict.get('thread_id'),
                    chat_type=chat_dict['type'], text=msg_dict['text'],
                    content_type=msg_dict['content_type'], file_id=msg_dict['file_id'],
                    is_command=msg_dict['is_command'], timestamp=now
                )
                db.session.add(db_msg)
                logger.info(f"✅ Message {msg_dict['id']} from {user_dict['id']} saved to DB.")
            else:
                # Update existing (might have been created by Profanity Filter)
                # Keep is_deleted and deletion_reason if already set
                db_msg.telegram_user_id = user_dict['id']
                db_msg.message_thread_id = msg_dict.get('thread_id')
                db_msg.chat_type = chat_dict['type']
                db_msg.text = msg_dict['text']
                db_msg.content_type = msg_dict['content_type']
                db_msg.file_id = msg_dict['file_id']
                db_msg.is_command = msg_dict['is_command']
                # DO NOT overwrite is_deleted or deletion_reason here if already true
                logger.info(f"✅ Message {msg_dict['id']} from {user_dict['id']} updated in DB.")
            
            db.session.commit()
    except Exception as e:
        logger.error(f"❌ Fehler beim synchronen Loggen: {e}")
        import traceback
        logger.error(traceback.format_exc())

async def track_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("--- [DIAG] track_activity triggered ---")
    if not is_bot_active('id_finder'):
        # logger.info("--- [DIAG] is_bot_active('id_finder') returned False ---")
        # For Master Bot, we might want to log regardless or check why it's inactive
        pass 
        
    msg, user, chat = update.effective_message, update.effective_user, update.effective_chat
    if not all([msg, user, chat]):
        logger.info(f"--- [DIAG] Missing components: msg={bool(msg)}, user={bool(user)}, chat={bool(chat)} ---")
        return
    
    config = get_bot_config("id_finder")
    logger.info(f"--- [DIAG] User: {user.id}, Chat: {chat.id} ({chat.type}), Msg: {msg.message_id} ---")
    
    if not config:
        logger.warning("--- [DIAG] No config found for id_finder! ---")
        return
        
    if not config.get("message_logging_enabled", True):
        logger.info("--- [DIAG] Message Logging disabled in config. ---")
        return
        
    logger.info(f"--- [DIAG] Processing message {msg.message_id} from {user.id} in {chat.id} ---")
        
    if config.get("message_logging_groups_only", False) and chat.type not in ["group", "supergroup"]:
        logger.info(f"--- [DIAG] Skipping private chat (groups_only=True). ---")
        return

    user_dict = {
        'id': user.id, 'username': user.username, 'first_name': user.first_name,
        'last_name': user.last_name, 'language_code': user.language_code, 'is_bot': user.is_bot
    }
    chat_dict = {'id': chat.id, 'type': chat.type}
    
    topic_name = f"Topic {msg.message_thread_id}"
    if chat.type in ["group", "supergroup"] and msg.message_thread_id:
        try:
            forum_topic = await context.bot.get_forum_topic(chat_id=chat.id, message_thread_id=msg.message_thread_id)
            topic_name = forum_topic.name
        except: pass

    content_type = "text"
    file_id = None
            
    if msg.photo: 
        content_type = "photo"
        file_id = msg.photo[-1].file_id
    elif msg.video: 
        content_type = "video"
        file_id = msg.video.file_id
    elif msg.sticker:
        content_type = "sticker_video" if msg.sticker.is_video else "sticker"
        file_id = msg.sticker.thumbnail.file_id if msg.sticker.is_animated and msg.sticker.thumbnail else msg.sticker.file_id
    elif msg.animation:
        content_type = "animation"
        file_id = msg.animation.file_id
    elif msg.document:
        content_type = "document"
        file_id = msg.document.file_id
    elif msg.voice:
        content_type = "voice"
        file_id = msg.voice.file_id
    elif msg.audio:
        content_type = "audio"
        file_id = msg.audio.file_id
    elif msg.video_note:
        content_type = "video_note"
        file_id = msg.video_note.file_id

    msg_dict = {
        'id': msg.message_id, 'thread_id': msg.message_thread_id, 'text': msg.text or msg.caption or "",
        'content_type': content_type, 'file_id': file_id,
        'is_command': (msg.text.startswith("/") if msg.text else False),
        'topic_name': topic_name
    }
    
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, db_log_message_sync, user_dict, chat_dict, msg_dict, config)

# --- Commands ---
async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_bot_active('id_finder'): return
    await update.message.reply_text(
        f"👤 *Benutzer-ID:* `{update.effective_user.id}`\n"
        f"💬 *Chat-ID:* `{update.effective_chat.id}`\n"
        f"🏷️ *Topic-ID:* `{update.effective_message.message_thread_id or 'Kein Topic'}`",
        parse_mode=ParseMode.MARKDOWN
    )

async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_bot_active('id_finder'): return
    user = update.effective_user
    chat = update.effective_chat
    msg = update.effective_message
    
    config = get_config_from_db()
    
    try:
        with flask_app.app_context():
            admin = IDFinderAdmin.query.filter_by(telegram_id=user.id).first()
            if not admin or not admin.permissions.get("can_warn", False) and not admin.permissions.get("is_superadmin", False):
                await msg.reply_text("❌ Du hast keine Berechtigung, Benutzer zu verwarnen.")
                return

            if not msg.reply_to_message:
                await msg.reply_text("⚠️ Bitte antworte auf eine Nachricht des Benutzers, den du verwarnen möchtest. (/warn <Grund>)")
                return

            target_user = msg.reply_to_message.from_user
            if target_user.is_bot:
                await msg.reply_text("❌ Du kannst keine Bots verwarnen.")
                return

            reason = "Kein Grund angegeben."
            if context.args:
                reason = " ".join(context.args)

            # Ensure user exists
            db_user = IDFinderUser.query.filter_by(telegram_id=target_user.id).first()
            if not db_user:
                db_user = IDFinderUser(
                    telegram_id=target_user.id, username=target_user.username,
                    first_name=target_user.first_name, last_name=target_user.last_name,
                    is_bot=target_user.is_bot
                )
                db.session.add(db_user)
                db.session.commit()

            # Add warning
            warning = IDFinderWarning(
                telegram_user_id=target_user.id,
                reason=reason,
                admin_id=user.id,
                message_db_id=None # We'd need the db_id of the replied message ideally, but leaving None is fine for now
            )
            db.session.add(warning)
            db.session.commit()
            
            warning_count = IDFinderWarning.query.filter_by(telegram_user_id=target_user.id).count()
            max_warns = config.get('max_warnings', 3)
            punishment = config.get('punishment_type', 'none')
            
            punishment_text = ""
            if warning_count >= max_warns and punishment != 'none':
                punishment_text = f"\n\n🚨 *Limit erreicht. Aktion: {punishment.upper()}*"
                try:
                    if punishment == 'mute':
                        mute_hours = config.get('mute_duration', 24)
                        until = datetime.utcnow() + timedelta(hours=mute_hours)
                        await context.bot.restrict_chat_member(chat_id=chat.id, user_id=target_user.id, permissions=ChatPermissions(can_send_messages=False), until_date=until)
                        punishment_text += f"\n(Stummgeschaltet für {mute_hours}h)"
                    elif punishment == 'kick':
                        await context.bot.ban_chat_member(chat_id=chat.id, user_id=target_user.id)
                        await context.bot.unban_chat_member(chat_id=chat.id, user_id=target_user.id)
                        punishment_text += "\n(Pausiert/Kick ausgeführt)"
                    elif punishment == 'ban':
                        await context.bot.ban_chat_member(chat_id=chat.id, user_id=target_user.id)
                        punishment_text += "\n(Permanent gesperrt)"
                except Exception as e:
                    logger.error(f"Fehler bei Auto-Punishment: {e}")
                    punishment_text += "\n_(Konnte nicht ausgeführt werden. Missing Admin Rights?)_"

            # Optional: Delete the /warn command itself
            if config and config.get("delete_commands", False):
                try:
                    await msg.delete()
                except: pass

            reply = await msg.reply_to_message.reply_text(
                f"⚠️ *Verwarnung an {target_user.first_name}*\n"
                f"Grund: {reason}\n"
                f"Verwarnung {warning_count} / {max_warns}{punishment_text}",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Optional: Automatic cleanup of bot message
            cleanup_secs = config.get("bot_message_cleanup_seconds", 0)
            if cleanup_secs > 0:
                cleanup_time = datetime.utcnow() + timedelta(seconds=cleanup_secs)
                task = AutoCleanupTask(chat_id=chat.id, message_id=reply.message_id, cleanup_at=cleanup_time, status='pending')
                db.session.add(task)
                db.session.commit()

    except Exception as e:
        logger.error(f"Fehler bei /warn: {e}")
        await msg.reply_text("❌ Interner Fehler beim Verwarnen.")

def get_handlers():
    return [
        CommandHandler("id", get_id),
        CommandHandler("warn", warn_user)
    ]

def get_track_handler():
    # Wir nehmen ALLE Nachrichten (auch Commands), die Filterung passiert in track_activity/db_log_message_sync
    return MessageHandler(filters.ALL, track_activity)

def setup_jobs(job_queue):
    job_queue.run_repeating(check_and_send_broadcasts, interval=30)
    job_queue.run_repeating(process_cleanup_tasks, interval=10)

if __name__ == "__main__":
    logger.error("Dieses Modul läuft nur via main_bot.py")