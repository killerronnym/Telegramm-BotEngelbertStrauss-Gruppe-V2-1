import logging
import os
import json
import sys
import asyncio
from datetime import datetime
from typing import Dict, Any, List

# --- Paths ---
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BOT_DIR))
# Import models from web_dashboard.app.models
sys.path.append(PROJECT_ROOT)

from web_dashboard.app.models import db, BotSettings, IDFinderAdmin, IDFinderUser, IDFinderMessage, TopicMapping
from flask import Flask

# --- Database Helper ---
def get_db_session():
    app = Flask(__name__)
    db_path = os.path.join(PROJECT_ROOT, 'instance', 'app.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app

flask_app = get_db_session()

# --- Logging ---
LOG_FILE = os.path.join(BOT_DIR, "id_finder_bot.log")
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s",
    level=logging.INFO,
    handlers=[logging.FileHandler(LOG_FILE, encoding='utf-8'), logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

try:
    from telegram import Update, ForumTopic
    from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, Application
except ImportError:
    logger.error("Erforderliche Bibliothek 'python-telegram-bot' nicht gefunden!")
    sys.exit(1)

# --- Config Management ---
def get_config_from_db():
    try:
        with flask_app.app_context():
            settings = BotSettings.query.filter_by(bot_name='id_finder').first()
            if settings:
                return json.loads(settings.config_json)
    except Exception as e:
        logger.error(f"Fehler beim Laden der Konfiguration aus DB: {e}")
    return None

# --- Activity Tracking (DB Version) ---
async def track_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg, user, chat = update.effective_message, update.effective_user, update.effective_chat
    if not all([msg, user, chat]): return
    
    config = get_config_from_db()
    if not config or not config.get("message_logging_enabled", True): return
    if config.get("message_logging_groups_only", False) and chat.type not in ["group", "supergroup"]:
        return

    now = datetime.utcnow()
    
    try:
        # Get Avatar
        avatar_file_id = None
        try:
            photos = await context.bot.get_user_profile_photos(user.id, limit=1)
            if photos.total_count > 0:
                avatar_file_id = photos.photos[0][-1].file_id
        except Exception as e:
            logger.debug(f"Could not get avatar for user {user.id}: {e}")

        with flask_app.app_context():
            # Update User Registry
            db_user = IDFinderUser.query.filter_by(telegram_id=user.id).first()
            if not db_user:
                db_user = IDFinderUser(
                    telegram_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    language_code=user.language_code,
                    is_bot=user.is_bot,
                    avatar_file_id=avatar_file_id,
                    first_contact=now
                )
                db.session.add(db_user)
            else:
                db_user.username = user.username
                db_user.first_name = user.first_name
                db_user.last_name = user.last_name
                db_user.avatar_file_id = avatar_file_id or db_user.avatar_file_id
                db_user.last_contact = now
            
            # Update Topic Mapping if available
            if chat.type in ["group", "supergroup"]:
                 thread_id = msg.message_thread_id
                 if thread_id:
                    topic_name = f"Topic {thread_id}"
                    try:
                        forum_topic = await context.bot.get_forum_topic(chat_id=chat.id, message_thread_id=thread_id)
                        topic_name = forum_topic.name
                    except: pass
                    
                    mapping = TopicMapping.query.filter_by(topic_id=thread_id).first()
                    if mapping:
                        mapping.topic_name = topic_name
                    else:
                        mapping = TopicMapping(topic_id=thread_id, topic_name=topic_name)
                        db.session.add(mapping)

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
            elif msg.document: 
                content_type = "document"
                file_id = msg.document.file_id
            elif msg.sticker: 
                content_type = "sticker"
                file_id = msg.sticker.file_id
            elif msg.voice: 
                content_type = "voice"
                file_id = msg.voice.file_id
            elif msg.audio: 
                content_type = "audio"
                file_id = msg.audio.file_id
            elif msg.animation: 
                content_type = "animation"
                file_id = msg.animation.file_id

            db_msg = IDFinderMessage(
                telegram_user_id=user.id,
                message_id=msg.message_id,
                chat_id=chat.id,
                message_thread_id=msg.message_thread_id,
                chat_type=chat.type,
                text=msg.text or msg.caption or "",
                content_type=content_type,
                file_id=file_id,
                is_command=is_command,
                timestamp=now
            )
            db.session.add(db_msg)
            db.session.commit()
    except Exception as e:
        logger.error(f"Fehler beim Loggen der Aktivität: {e}")

# --- Admin Check ---
def is_admin(telegram_id: int):
    try:
        with flask_app.app_context():
            admin = IDFinderAdmin.query.filter_by(telegram_id=telegram_id).first()
            return admin is not None
    except: return False

# --- Commands ---
async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"👤 *Benutzer-ID:* `{update.effective_user.id}`\n"
        f"💬 *Chat-ID:* `{update.effective_chat.id}`\n"
        f"🏷️ *Topic-ID:* `{update.effective_message.message_thread_id or 'Kein Topic'}`",
        parse_mode="Markdown"
    )

async def shutdown(app: Application):
    logger.info("Bot wird heruntergefahren...")

def main():
    config = get_config_from_db()
    if not config or not config.get("bot_token"):
        logger.critical("Bot Token nicht in Datenbank gefunden!")
        sys.exit(1)
        
    app = ApplicationBuilder().token(config["bot_token"]).post_shutdown(shutdown).build()
    
    # Add handlers
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, track_activity))
    app.add_handler(CommandHandler("id", get_id))

    logger.info("ID-Finder Bot startet (DB-Modus)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
