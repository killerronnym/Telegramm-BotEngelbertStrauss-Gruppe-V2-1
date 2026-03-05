import logging
import os
import json
import sys
from datetime import datetime

# Setup Project Root for imports
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BOT_DIR))
sys.path.append(PROJECT_ROOT)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
from telegram.constants import ParseMode

from web_dashboard.app.models import db, BotSettings, ReportedMessage
from shared_bot_utils import is_bot_active, get_bot_config, get_shared_flask_app

flask_app = get_shared_flask_app()
logger = logging.getLogger(__name__)

def get_report_config():
    return get_bot_config("report_bot") or {
        "is_active": False,
        "target_chat_id": None,
        "target_topic_id": None
    }

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /report command."""
    config = get_report_config()
    if not config.get("is_active"):
        return

    msg = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not msg.reply_to_message:
        await msg.reply_text("⚠️ Bitte antworte auf eine Nachricht, die du melden möchtest, mit `/report [Grund]`. ", parse_mode=ParseMode.MARKDOWN)
        return

    reported_msg = msg.reply_to_message
    reason = "Kein Grund angegeben."
    if context.args:
        reason = " ".join(context.args)

    try:
        with flask_app.app_context():
            # Save report to DB
            new_report = ReportedMessage(
                reporter_id=user.id,
                reported_user_id=reported_msg.from_user.id if reported_msg.from_user else None,
                reported_message_id=reported_msg.message_id,
                chat_id=chat.id,
                reason=reason
            )
            db.session.add(new_report)
            db.session.commit()
            
            # Post to Admin Channel/Topic if configured
            target_chat = config.get("target_chat_id")
            if target_chat:
                target_topic = config.get("target_topic_id")
                
                # Format notification
                report_text = (
                    f"🚨 **NEUE MELDUNG** 🚨\n\n"
                    f"👤 **Melder:** {user.mention_markdown_v2()}\n"
                    f"👤 **Gemeldeter Nutzer:** {reported_msg.from_user.mention_markdown_v2() if reported_msg.from_user else 'Unbekannt'}\n"
                    f"💬 **Grund:** {reason}\n"
                    f"📍 **Wo:** {chat.title or 'Privat'}\n\n"
                    f"🔗 [Zur Nachricht](https://t.me/c/{str(chat.id)[4:] if str(chat.id).startswith('-100') else chat.id}/{reported_msg.message_id})"
                )
                
                try:
                    await context.bot.send_message(
                        chat_id=target_chat,
                        text=report_text,
                        message_thread_id=target_topic if target_topic else None,
                        parse_mode=ParseMode.MARKDOWN_V2
                    )
                except Exception as e:
                    logger.error(f"Fehler beim Senden der Report-Benachrichtigung an {target_chat}: {e}")

            # Confirmation to user (and delete after 5s)
            confirmation = await msg.reply_text("✅ Danke für deine Meldung. Die Administratoren wurden informiert.")
            
            # Auto-delete call (optional, depends on cleanup_bot)
            try:
                await msg.delete() # Delete the /report command message
            except: pass

    except Exception as e:
        logger.error(f"Fehler in report_command: {e}")
        await msg.reply_text("❌ Ein Fehler ist aufgetreten. Bitte versuche es später erneut.")

def get_handlers():
    return [
        CommandHandler("report", report_command)
    ]

if __name__ == "__main__":
    logger.error("Dieses Modul läuft nur via main_bot.py")
