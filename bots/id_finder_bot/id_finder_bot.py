import logging
import os
import json
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional

# --- Paths ---
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BOT_DIR))
# Import models from web_dashboard.app.models
sys.path.append(PROJECT_ROOT)

from web_dashboard.app.models import db, BotSettings, IDFinderAdmin, IDFinderUser, IDFinderMessage, TopicMapping, Broadcast, AutoCleanupTask
from flask import Flask

# Import the tiktok monitor function
from bots.id_finder_bot.minecraft_bridge import register_minecraft

# Import shared utils for DB URL resolution
from shared_bot_utils import get_db_url

# --- Database Helper ---
def get_db_session():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = get_db_url()
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app

flask_app = get_db_session()

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
    from telegram import Update, ForumTopic
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
                    if b.media_path:
                        full_media_path = os.path.join(PROJECT_ROOT, 'web_dashboard', 'app', 'static', b.media_path)
                        if os.path.exists(full_media_path):
                            with open(full_media_path, 'rb') as f:
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
                        else:
                            logger.error(f"Mediendatei nicht gefunden: {full_media_path}")
                            b.status = 'failed'
                            continue
                    else:
                        msg = await context.bot.send_message(
                            chat_id=chat_id, text=b.text,
                            message_thread_id=thread_id, disable_notification=b.silent_send,
                            parse_mode=ParseMode.HTML
                        )
                    
                    if b.pin_message and msg:
                        await context.bot.pin_chat_message(chat_id=chat_id, message_id=msg.message_id)

                    b.status = 'sent'
                    logger.info(f"Broadcast {b.id} erfolgreich gesendet.")
                except Exception as e:
                    logger.error(f"Fehler beim Senden von Broadcast {b.id}: {e}")
                    b.status = 'failed'
                
            db.session.commit()
    except Exception as e:
        logger.error(f"Fehler in der Broadcast Engine: {e}")

# --- Activity Tracking ---
async def track_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg, user, chat = update.effective_message, update.effective_user, update.effective_chat
    if not all([msg, user, chat]): return
    
    config = get_config_from_db()
    if not config or not config.get("message_logging_enabled", True): return
    if config.get("message_logging_groups_only", False) and chat.type not in ["group", "supergroup"]:
        return

    now = datetime.utcnow()
    
    try:
        with flask_app.app_context():
            # Update User Registry
            db_user = IDFinderUser.query.filter_by(telegram_id=user.id).first()
            if not db_user:
                db_user = IDFinderUser(
                    telegram_id=user.id, username=user.username,
                    first_name=user.first_name, last_name=user.last_name,
                    language_code=user.language_code, is_bot=user.is_bot,
                    first_contact=now
                )
                db.session.add(db_user)
            else:
                db_user.username = user.username
                db_user.first_name = user.first_name
                db_user.last_name = user.last_name
                db_user.last_contact = now
            
            # Discover Topics
            if chat.type in ["group", "supergroup"] and msg.message_thread_id:
                thread_id = msg.message_thread_id
                mapping = TopicMapping.query.filter_by(topic_id=thread_id).first()
                if not mapping:
                    topic_name = f"Topic {thread_id}"
                    try:
                        forum_topic = await context.bot.get_forum_topic(chat_id=chat.id, message_thread_id=thread_id)
                        topic_name = forum_topic.name
                    except: pass
                    db.session.add(TopicMapping(topic_id=thread_id, topic_name=topic_name))

            # Log Message
            is_command = msg.text.startswith("/") if msg.text else False
            if is_command and config.get("message_logging_ignore_commands", True):
                db.session.commit()
                return

            content_type = "text"
            file_id = None
            if msg.photo: 
                content_type = "photo"
                file_id = msg.photo[-1].file_id
            elif msg.video: 
                content_type = "video"
                file_id = msg.video.file_id
            elif msg.sticker:
                content_type = "sticker"
                file_id = msg.sticker.file_id
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

            db_msg = IDFinderMessage(
                telegram_user_id=user.id, message_id=msg.message_id,
                chat_id=chat.id, message_thread_id=msg.message_thread_id,
                chat_type=chat.type, text=msg.text or msg.caption or "",
                content_type=content_type, file_id=file_id,
                is_command=is_command, timestamp=now
            )
            logger.info(f"Logging message from {user.id}: type={content_type}, file_id={file_id}")
            db.session.add(db_msg)
            db.session.commit()
    except Exception as e:
        logger.error(f"Fehler beim Loggen: {e}")

# --- Commands ---
async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"👤 *Benutzer-ID:* `{update.effective_user.id}`\n"
        f"💬 *Chat-ID:* `{update.effective_chat.id}`\n"
        f"🏷️ *Topic-ID:* `{update.effective_message.message_thread_id or 'Kein Topic'}`",
        parse_mode=ParseMode.MARKDOWN
    )

# --- Bot Lifecycle Callbacks ---
async def post_init(app: Application) -> None:
    logger.info("ID-Finder Bot initialisiert.")

async def post_shutdown(app: Application) -> None:
    logger.info("ID-Finder Bot wurde beendet und heruntergefahren.")

def main():
    config = get_config_from_db()
    if not config or not config.get("bot_token"):
        logger.critical("Bot Token nicht in Datenbank gefunden! Bitte im Dashboard unter 'ID-Finder Bot' einstellen.")
        sys.exit(1)
        
    app = ApplicationBuilder().token(config["bot_token"])
    app = app.post_init(post_init).post_shutdown(post_shutdown).build()
    
    # Handlers
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, track_activity))
    app.add_handler(CommandHandler("id", get_id))

    # Minecraft Bridge
    register_minecraft(app)

    # Jobs (Warteschlangen prüfen)
    app.job_queue.run_repeating(check_and_send_broadcasts, interval=30)
    app.job_queue.run_repeating(process_cleanup_tasks, interval=10) # Alle 10 Sek nach abgelaufenen Meldungen suchen

    logger.info("ID-Finder Bot startet (mit Broadcast, Auto-Cleanup & TikTok Monitor)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()