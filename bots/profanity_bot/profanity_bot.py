import sys
import os
import json
import logging
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters
from shared_bot_utils import is_bot_active, get_shared_flask_app
from datetime import datetime

# Navigation to root
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from web_dashboard.app.models import ProfanityWord, IDFinderWarning, IDFinderUser, BotSettings, IDFinderMessage, TopicMapping, db

logger = logging.getLogger("ProfanityBot")
logger.setLevel(logging.INFO)

def is_bot_active_local() -> bool:
    try:
        from shared_bot_utils import is_bot_active
        return is_bot_active('profanity_filter')
    except Exception as e:
        logger.error(f"Error checking if profanity_filter is active: {e}")
        return False

def get_app():
    return get_shared_flask_app()

def fetch_profanity_words():
    """Liest alle Wörter von der Blacklist aus der Datenbank."""
    app = get_app()
    if not app:
        return []
    with app.app_context():
        try:
            return [w.word.lower() for w in ProfanityWord.query.all()]
        except Exception as e:
            logger.error(f"Fehler beim Laden der Profanity-Wörter aus der DB: {e}")
            return []

async def handle_profanity_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prüft Textnachrichten auf Beleidigungen."""
    # We only care about group messages (or wherever the bot has delete permissions)
    if not update.message or not update.message.text:
        return
        
    chat = update.message.chat
    if chat.type == 'private':
        return # Do not filter private messages to the bot
        
    message_text = update.message.text.lower()
    logger.info(f"⚡ Profanity Check Triggered on '{message_text[:20]}...'")
    
    active = is_bot_active_local()
    if not active:
        logger.info("-> Ignoriert: Modul ist im Dashboard ausgeschaltet.")
        return
    
    words = fetch_profanity_words()
    if not words:
        logger.info("-> Ignoriert: Blacklist ist leer oder DB Fehler.")
        return
        
    for word in words:
        # Check if the bad word is directly in the message
        # You could also use regex like r'\b' + re.escape(word) + r'\b' to only match full words,
        # but the request mentioned "Egal ob es vorne hinten, Mitte oder irgendwo drin steht", so substring:
        if word in message_text:
            try:
                # 1. Delete the message
                await update.message.delete()
                logger.info(f"Beleidigung gelöscht im Chat {chat.id} durch User {update.message.from_user.id}: '{word}'")
                
                # 2. Add an IDFinderWarning
                app = get_app()
                if app:
                    with app.app_context():
                        user_id = update.message.from_user.id
                        
                        # Get IDFinder Config to check limits
                        id_s = BotSettings.query.filter_by(bot_name='id_finder').first()
                        max_warns = 3
                        punishment = 'none'
                        mute_duration = 24
                        
                        if id_s and id_s.config_json:
                            id_cfg = json.loads(id_s.config_json)
                            max_warns = id_cfg.get('max_warnings', 3)
                            punishment = id_cfg.get('punishment_type', 'none')
                            mute_duration = id_cfg.get('mute_duration', 24)
                            
                        # Ensure user exists in IDFinderUser table
                        target_user = IDFinderUser.query.filter_by(telegram_id=user_id).first()
                        if not target_user:
                            target_user = IDFinderUser(
                                telegram_id=user_id,
                                username=update.message.from_user.username,
                                first_name=update.message.from_user.first_name,
                                avatar_file_id=None
                            )
                            db.session.add(target_user)
                            db.session.commit()
                            
                        warning = IDFinderWarning(
                            telegram_user_id=target_user.telegram_id,
                            reason=f"Automatischer Beleidigungsfilter: '{word}'",
                            admin_id=None, # System Auto-Mod
                            message_db_id=None,
                            timestamp=datetime.utcnow()
                        )
                        db.session.add(warning)
                        db.session.commit()
                        
                        warning_count = IDFinderWarning.query.filter_by(telegram_user_id=target_user.telegram_id).count()
                        
                        # Notify user in group (Optional, maybe DM is better, but group is standard for ID-Finder)
                        punishment_text = ""
                        if warning_count >= max_warns and punishment != 'none':
                            punishment_text = " 🚨 Maximale Verwarnungen erreicht! Konsequenzen folgen."
                            
                        notice = await context.bot.send_message(
                            chat_id=chat.id,
                            text=f"⚠️ {update.message.from_user.mention_html()}, deine Nachricht wurde gelöscht wegen beleidigenden Inhalten.\n\n"
                                 f"Verwarnung {warning_count} / {max_warns}{punishment_text}\n\n"
                                 f"<i>(Diese Nachricht wird in 60 Sekunden gelöscht)</i>",
                            parse_mode="HTML"
                        )
                        
                        import asyncio
                        async def delete_notice_later(bot, chat_id, message_id):
                            await asyncio.sleep(60)
                            try:
                                await bot.delete_message(chat_id=chat_id, message_id=message_id)
                            except Exception as e:
                                logger.error(f"Fehler beim Löschen der Profanity-Warnung: {e}")
                                
                        asyncio.create_task(delete_notice_later(context.bot, chat.id, notice.message_id))
                        
                        # 3. Log the deleted message into IDFinderMessage so Live Moderation shows it in red
                        # Run this slightly delayed to ensure ID-Finder has already logged the message
                        async def mark_message_deleted(msg_id, c_id, uid, t_id, c_type, m_text, b_word):
                            await asyncio.sleep(2)
                            app_ctx = get_app()
                            if app_ctx:
                                with app_ctx.app_context():
                                    try:
                                        db_msg = IDFinderMessage.query.filter_by(message_id=msg_id, chat_id=c_id).first()
                                        if db_msg:
                                            db_msg.is_deleted = True
                                            db_msg.deletion_reason = f"Beleidigungsfilter: {b_word}"
                                            db.session.commit()
                                            logger.info(f"Nachricht {msg_id} nachträglich als gelöscht (rot) markiert.")
                                        else:
                                            # Upsert if somehow ID Finder missed it
                                            db_msg = IDFinderMessage(
                                                telegram_user_id=uid,
                                                message_id=msg_id,
                                                chat_id=c_id,
                                                message_thread_id=t_id,
                                                chat_type=c_type,
                                                text=m_text,
                                                content_type='text',
                                                is_command=False,
                                                timestamp=datetime.utcnow(),
                                                is_deleted=True,
                                                deletion_reason=f"Beleidigungsfilter: {b_word}"
                                            )
                                            db.session.add(db_msg)
                                            db.session.commit()
                                    except Exception as inner_e:
                                        logger.error(f"Konnte gelöschte Nachricht nicht ins Live-Log schreiben: {inner_e}")
                                        
                        asyncio.create_task(
                            mark_message_deleted(
                                update.message.message_id, 
                                chat.id, 
                                target_user.telegram_id, 
                                update.message.message_thread_id, 
                                chat.type, 
                                message_text, 
                                word
                            )
                        )
                            
                        # Execute punishment if limit reached
                        if warning_count >= max_warns and punishment != 'none':
                            try:
                                if punishment == 'kick':
                                    await context.bot.ban_chat_member(chat_id=chat.id, user_id=user_id)
                                    await context.bot.unban_chat_member(chat_id=chat.id, user_id=user_id)
                                elif punishment == 'ban':
                                    await context.bot.ban_chat_member(chat_id=chat.id, user_id=user_id)
                                elif punishment == 'mute':
                                    from telegram.constants import ChatPermissions
                                    import time
                                    until = int(time.time()) + (mute_duration * 3600)
                                    await context.bot.restrict_chat_member(
                                        chat_id=chat.id, 
                                        user_id=user_id, 
                                        permissions=ChatPermissions(can_send_messages=False),
                                        until_date=until
                                    )
                                logger.info(f"Auto-Mod Strafe '{punishment}' ausgeführt an {user_id}")
                            except Exception as e:
                                logger.error(f"Fehler bei Auto-Mod Strafe: {e}")
                                await context.bot.send_message(chat_id=chat.id, text=f"⚠️ DEBUG System-Fehler: Konnte Strafe nicht ausführen. Grund: {str(e)}")
                                
                        # Return after the first word is found to avoid double penalization
                        return
                        
            except Exception as e:
                logger.error(f"Fehler beim Bearbeiten der Beleidigung '{word}': {e}")
                # Tell the chat exactly what went wrong!
                try:
                    await context.bot.send_message(
                        chat_id=chat.id, 
                        text=f"🤖 <b>SYSTEM-DEBUG-MELDUNG</b>\nIch habe das verbotene Wort <code>{word}</code> in der Nachricht von {update.message.from_user.first_name} gefunden, aber Telegram verbietet mir das Löschen der Nachricht!\n\n<b>Technischer Grund vom Server:</b> {str(e)}\n\n(Das passiert meistens, wenn der Sender ein Administrator ist oder dem Bot Rechte fehlen.)",
                        parse_mode="HTML"
                    )
                except:
                    pass

def get_handlers():
    """Gibt die Handler zurück, die main_bot.py registrieren soll."""
    # Group -1 = Vor allen anderen Befehlen laufen lassen, absolute Priorität als Filter
    h1 = MessageHandler(filters.TEXT, handle_profanity_check)
    return [(h1, -1)]

def get_fallback_handlers():
    return []

def setup_jobs(job_queue):
    pass
