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
import html

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

async def check_pending_events(context: ContextTypes.DEFAULT_TYPE):
    """Poll DB for events that haven't been posted yet."""
    try:
        with flask_app.app_context():
            # CRITICAL: Completely remove session to force a brand new DB transaction
            db.session.remove()
            
            # Fetch all events to avoid ORM parameter caching issues
            all_events = GroupEvent.query.all()
            logger.info(f"[EVENT DEBUG] Found {len(all_events)} total events in DB via ORM.")
            
            pending = []
            for e in all_events:
                logger.info(f"[EVENT DEBUG] Inspecting ID={e.id}, title={e.title}, chat={e.chat_id}, msg={e.message_id}")
                if not e.message_id and e.chat_id:
                    pending.append(e)
            
            if not pending:
                logger.info("[EVENT DEBUG] No pending events found.")
                return

            for event in pending:
                logger.info(f"Processing pending event: {event.title} (ID: {event.id}) for chat {event.chat_id}")
                
                try:
                    # Format message
                    text = f"📅 <b>{html.escape(event.title)}</b>\n\n{html.escape(event.description or '')}\n\n✅ 0 | 🤔 0 | ❌ 0"
                    markup = get_event_markup(event.id, {})
                    
                    posted_msg = None
                    topic_id_int = int(event.topic_id) if event.topic_id and str(event.topic_id).isdigit() else None
                    
                    if event.image_path:
                        # Full path for Docker/Local consistency
                        img_path = os.path.join(PROJECT_ROOT, 'web_dashboard', 'app', event.image_path.lstrip('/'))
                        if os.path.exists(img_path):
                            with open(img_path, 'rb') as f:
                                posted_msg = await context.bot.send_photo(
                                    chat_id=event.chat_id,
                                    message_thread_id=topic_id_int,
                                    photo=f,
                                    caption=text,
                                    parse_mode=ParseMode.HTML,
                                    reply_markup=markup
                                )
                        else:
                            logger.error(f"Image not found at {img_path}, sending text only.")
                    
                    if not posted_msg:
                        posted_msg = await context.bot.send_message(
                            chat_id=event.chat_id,
                            message_thread_id=topic_id_int,
                            text=text,
                            parse_mode=ParseMode.HTML,
                            reply_markup=markup
                        )
                    
                    # Store message ID
                    event.message_id = posted_msg.message_id
                    db.session.commit()
                    logger.info(f"✅ Event '{event.title}' successfully posted. MsgID: {posted_msg.message_id}")

                    # Pin if requested
                    if event.should_pin:
                        try:
                            await context.bot.pin_chat_message(chat_id=event.chat_id, message_id=posted_msg.message_id)
                        except Exception as e:
                            logger.warning(f"Could not pin message {posted_msg.message_id}: {e}")

                except Exception as e:
                    logger.error(f"Failed to post event {event.id}: {e}")
                    # We don't commit here so it retries or we can see the error
    except Exception as e:
        logger.error(f"Error in check_pending_events job: {e}")

def setup_jobs(job_queue):
    """Register the polling job."""
    job_queue.run_repeating(check_pending_events, interval=10, first=5)
    logger.info("✅ Event polling job registered (10s interval).")

def get_handlers():
    return [
        CallbackQueryHandler(rsvp_handler, pattern="^event_rsvp_")
    ]

if __name__ == "__main__":
    logger.error("Dieses Modul läuft nur via main_bot.py")
