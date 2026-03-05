import logging
import os
import json
import sys
from datetime import datetime

# Setup Project Root for imports
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BOT_DIR))
sys.path.append(PROJECT_ROOT)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, filters
from telegram.constants import ParseMode

from web_dashboard.app.models import db, BotSettings, GroupEvent, EventRSVP
from shared_bot_utils import get_bot_config, get_shared_flask_app

flask_app = get_shared_flask_app()
logger = logging.getLogger(__name__)

def get_event_markup(event_id, rsvp_counts):
    keyboard = [
        [
            InlineKeyboardButton(f"✅ Bin dabei ({rsvp_counts.get('dabei', 0)})", callback_data=f"event_rsvp_{event_id}_dabei"),
            InlineKeyboardButton(f"🤔 Vielleicht ({rsvp_counts.get('vielleicht', 0)})", callback_data=f"event_rsvp_{event_id}_vielleicht")
        ],
        [
            InlineKeyboardButton(f"❌ Nicht dabei ({rsvp_counts.get('nicht_dabei', 0)})", callback_data=f"event_rsvp_{event_id}_nicht_dabei")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def rsvp_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user = query.from_user

    if not data.startswith("event_rsvp_"):
        return

    # event_rsvp_{id}_{status}
    parts = data.split("_")
    event_id = int(parts[2])
    status = parts[3]

    try:
        with flask_app.app_context():
            event = GroupEvent.query.get(event_id)
            if not event:
                await query.answer("Dieses Event existiert nicht mehr.", show_alert=True)
                return

            # Update or Create RSVP
            rsvp = EventRSVP.query.filter_by(event_id=event_id, telegram_user_id=user.id).first()
            if rsvp:
                if rsvp.status == status:
                    await query.answer("Du hast bereits diesen Status gewählt.")
                    return
                rsvp.status = status
            else:
                rsvp = EventRSVP(
                    event_id=event_id,
                    telegram_user_id=user.id,
                    username=user.username or user.first_name,
                    status=status
                )
                db.session.add(rsvp)
            
            db.session.commit()

            # Get updated counts
            counts = {
                'dabei': EventRSVP.query.filter_by(event_id=event_id, status='dabei').count(),
                'vielleicht': EventRSVP.query.filter_by(event_id=event_id, status='vielleicht').count(),
                'nicht_dabei': EventRSVP.query.filter_by(event_id=event_id, status='nicht_dabei').count()
            }

            # Update message
            try:
                await query.edit_message_reply_markup(reply_markup=get_event_markup(event_id, counts))
                await query.answer(f"Status geändert zu: {status.replace('_', ' ').capitalize()}")
            except Exception as e:
                logger.error(f"Error updating event message: {e}")
                await query.answer("Status gespeichert.")

    except Exception as e:
        logger.error(f"Error in rsvp_handler: {e}")
        await query.answer("Ein Fehler ist aufgetreten.", show_alert=True)

def get_handlers():
    return [
        CallbackQueryHandler(rsvp_handler, pattern="^event_rsvp_")
    ]

if __name__ == "__main__":
    logger.error("Dieses Modul läuft nur via main_bot.py")
