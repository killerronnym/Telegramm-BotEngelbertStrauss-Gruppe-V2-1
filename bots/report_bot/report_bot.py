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
import html

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
        help_msg = (
            "⚠️ <b>Anleitung: So meldest du eine Nachricht</b>\n\n"
            "1. Gehe zu der Nachricht, die du melden möchtest.\n"
            "2. Nutze die <b>Antwort-Funktion</b> (Reply) auf diese Nachricht.\n"
            "3. Schreibe <code>/report [Grund]</code> (der Grund ist optional).\n\n"
            "Nur wenn du auf eine Nachricht antwortest, wissen die Admins, was gemeldet wurde! 💡"
        )
        await msg.reply_text(help_msg, parse_mode=ParseMode.HTML)
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
                rep_name = html.escape(user.first_name)
                target_user = reported_msg.from_user
                target_name = html.escape(target_user.first_name) if target_user else "Unbekannt"
                esc_reason = html.escape(reason)
                chat_title = html.escape(chat.title or "Privat")
                
                # Chat link construction (stripped -100 for public/supergroup links)
                chat_id_str = str(chat.id)
                if chat_id_str.startswith("-100"):
                    link_id = chat_id_str[4:]
                else:
                    link_id = chat_id_str

                report_text = (
                    f"🚨 <b>NEUE MELDUNG</b> 🚨\n\n"
                    f"👤 <b>Melder:</b> {rep_name} (ID: <code>{user.id}</code>)\n"
                    f"👤 <b>Gemeldeter Nutzer:</b> {target_name} (ID: <code>{target_user.id if target_user else 'N/A'}</code>)\n"
                    f"💬 <b>Grund:</b> {esc_reason}\n"
                    f"📍 <b>Wo:</b> {chat_title}\n\n"
                    f"🔗 <a href='https://t.me/c/{link_id}/{reported_msg.message_id}'>Zur Nachricht springen</a>"
                )
                
                try:
                    await context.bot.send_message(
                        chat_id=target_chat,
                        text=report_text,
                        message_thread_id=target_topic if target_topic else None,
                        parse_mode=ParseMode.HTML
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
