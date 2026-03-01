import logging
from telegram import Update
from telegram.ext import CommandHandler, MessageHandler, ConversationHandler, filters, ContextTypes
from web_dashboard.app.models import Birthday, BotSettings, IDFinderUser
from web_dashboard.app import db
from shared_bot_utils import get_shared_flask_app
import json
import re
from datetime import datetime
import pytz

logger = logging.getLogger("BirthdayBot")
logger.setLevel(logging.INFO)

WAITING_FOR_DATE = 1

# Erlaubt Formate wie: "15 08", "15.08.", "15.08", "15.08.1990", "15 08 1990"
DATE_PATTERN = re.compile(r'^(\d{1,2})[\s\.]+(\d{1,2})(?:[\s\.]+(\d{4}))?\.?$')

def get_birthday_settings():
    flask_app = get_shared_flask_app()
    with flask_app.app_context():
        setting = BotSettings.query.filter_by(bot_name='birthday').first()
        if not setting:
            return {
                'registration_text': 'Dein Geburtstag ({day}.{month}.) wurde erfolgreich eingetragen!',
                'congratulation_text': 'Herzlichen Glückwunsch zum Geburtstag, {user}!',
                'prompt_text': '🎂 <b>Geburtstags-Bot</b>\n\nWann hast du Geburtstag?\nBitte schreibe es im Format <code>Tag.Monat</code> oder <code>Tag.Monat.Jahr</code>.\n<i>(Beispiel: 15.08. oder 15.08.1990 - das Jahr ist komplett freiwillig!)</i>\n\nWenn du abbrechen möchtest, tippe /cancel.',
                'error_format_text': 'Das war leider das falsche Format.\nBeispiele: `15.08.` oder `15 08 1990`\nVersuche es nochmal oder tippe /cancel.',
                'error_date_text': 'Das ist leider kein echtes Kalenderdatum. Bitte versuche es noch einmal:',
                'cancel_text': 'Geburtstags-Eintragung abgebrochen.',
                'announce_time': '00:01',
                'target_chat_id': '',
                'target_topic_id': ''
            }
        return json.loads(setting.config_json)
async def start_birthday_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from shared_bot_utils import is_bot_active
    if not is_bot_active('birthday'):
        logger.info("Birthday registration ignored: bot is inactive in settings.")
        return ConversationHandler.END

    logger.info(f"Starting birthday registration for user {update.effective_user.id} in chat {update.effective_chat.id} (Thread: {update.message.message_thread_id if update.message.is_topic_message else 'None'})")
    settings = get_birthday_settings()
    text = settings.get('prompt_text', '🎂 <b>Geburtstags-Bot</b>\n\nWann hast du Geburtstag?\nBitte schreibe es im Format <code>Tag.Monat</code> oder <code>Tag.Monat.Jahr</code>.\n<i>(Beispiel: 15.08. oder 15.08.1990 - das Jahr ist komplett freiwillig!)</i>\n\nWenn du abbrechen möchtest, tippe /cancel.')
    if update.message:
        kwargs = {'text': text, 'parse_mode': 'HTML'}
        if update.message.is_topic_message:
            kwargs['message_thread_id'] = update.message.message_thread_id
        logger.info(f"Sending prompt to user {update.effective_user.id} with kwargs: {kwargs}")
        await update.message.reply_text(**kwargs)
    return WAITING_FOR_DATE

async def handle_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    text_input = update.message.text.strip()
    
    match = DATE_PATTERN.match(text_input)
    
    settings = get_birthday_settings()
    if not match:
        msg = settings.get('error_format_text', "Das war leider das falsche Format.\nBeispiele: `15.08.` oder `15 08 1990`\nVersuche es nochmal oder tippe /cancel.")
        kwargs = {'text': msg, 'parse_mode': 'Markdown'}
        if update.message.is_topic_message:
            kwargs['message_thread_id'] = update.message.message_thread_id
        await update.message.reply_text(**kwargs)
        return WAITING_FOR_DATE
        
    day = int(match.group(1))
    month = int(match.group(2))
    year = int(match.group(3)) if match.group(3) else None
    
    if not (1 <= month <= 12) or not (1 <= day <= 31):
        msg = settings.get('error_date_text', "Das ist leider kein echtes Kalenderdatum. Bitte versuche es noch einmal:")
        kwargs = {'text': msg}
        if update.message.is_topic_message:
            kwargs['message_thread_id'] = update.message.message_thread_id
        await update.message.reply_text(**kwargs)
        return WAITING_FOR_DATE
        
    if year and (year < 1900 or year > datetime.now().year):
        await update.message.reply_text(f"Das Jahr {year} scheint nicht zu stimmen. Bitte versuche es noch einmal:")
        return WAITING_FOR_DATE
        
    flask_app = get_shared_flask_app()
    with flask_app.app_context():
        # User sicherstellen
        id_user = IDFinderUser.query.filter_by(telegram_id=user.id).first()
        if not id_user:
            id_user = IDFinderUser(telegram_id=user.id, first_name=user.first_name, username=user.username)
            db.session.add(id_user)
            try: db.session.flush()
            except: pass

        birthday = Birthday.query.filter_by(telegram_user_id=user.id).first()
        if birthday:
            birthday.day = day
            birthday.month = month
            birthday.year = year
            birthday.chat_id = chat_id
            birthday.username = user.username
            birthday.first_name = user.first_name
        else:
            birthday = Birthday(
                telegram_user_id=user.id,
                chat_id=chat_id,
                username=user.username,
                first_name=user.first_name,
                day=day,
                month=month,
                year=year
            )
            db.session.add(birthday)
        db.session.commit()
        
        settings = get_birthday_settings()
        reply_text = settings.get('registration_text', 'Dein Geburtstag ({day}.{month}.) wurde erfolgreich eingetragen!')
        
        reply_text = reply_text.replace('{day}', f"{day:02d}").replace('{month}', f"{month:02d}")
        if year:
            reply_text += f"\n(Jahrgang: {year} gespeichert)"
            
        await update.message.reply_text(reply_text, message_thread_id=update.message.message_thread_id if update.message.is_topic_message else None)
        
    return ConversationHandler.END

async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings = get_birthday_settings()
    msg = settings.get('cancel_text', "Geburtstags-Eintragung abgebrochen.")
    kwargs = {'text': msg}
    if update.message and update.message.is_topic_message:
        kwargs['message_thread_id'] = update.message.message_thread_id
    if update.message:
        await update.message.reply_text(**kwargs)
    return ConversationHandler.END

async def check_birthdays(context: ContextTypes.DEFAULT_TYPE):
    # Standard-Zeitzone (könnte man später konfigurierbar machen)
    tz = pytz.timezone('Europe/Berlin')
    now = datetime.now(tz)
    
    settings = get_birthday_settings()
    announce_time = settings.get('announce_time', '00:01')
    current_time_str = now.strftime('%H:%M')
    
    # Nur ein Log-Eintrag pro Minute (wenn wir getriggert werden)
    if now.second < 10: # Nur am Anfang der Minute loggen um Spam zu vermeiden
        logger.info(f"Checking birthdays... Local Time: {current_time_str}, Announce Time: {announce_time}")
    
    if current_time_str != announce_time:
        return
        
    logger.info(f"⏰ IT IS TIME! Sending congratulations for {now.day}.{now.month}. at {current_time_str}")
    
    # Ziel-Chat auslesen
    global_target_chat = settings.get('target_chat_id', '').strip()
    global_target_topic = settings.get('target_topic_id', '').strip()
        
    flask_app = get_shared_flask_app()
    with flask_app.app_context():
        # Wir suchen nach Geburtstagen für HEUTE in der Zeitzone
        birthdays = Birthday.query.filter_by(day=now.day, month=now.month).all()
        logger.info(f"Found {len(birthdays)} birthdays for today ({now.day}.{now.month}.)")
        for b in birthdays:
            # Prio1: Global, Prio2: Ort der Eintragung
            final_chat_id = global_target_chat if global_target_chat else b.chat_id
            
            if final_chat_id:
                try:
                    text = settings.get('congratulation_text', 'Herzlichen Glückwunsch zum Geburtstag, {user}!')
                    name = b.first_name if b.first_name else f"@{b.username}"
                    text = text.replace('{user}', name)
                    
                    if '{age}' in text:
                        if b.year:
                            age = today.year - b.year
                            text = text.replace('{age}', str(age))
                        else:
                            text = text.replace('{age}', '?')
                    
                    kwargs = {'chat_id': final_chat_id, 'text': text}
                    if global_target_topic and global_target_topic.isdigit():
                        kwargs['message_thread_id'] = int(global_target_topic)
                        
                    await context.bot.send_message(**kwargs)
                    logger.info(f"Geburtstagsgruß gesendet an {name} in Chat {final_chat_id}")
                except Exception as e:
                    logger.error(f"Fehler beim Senden des Geburtstagsgrußes für {b.telegram_user_id}: {e}")

def get_handlers():
    logger.info("Registering birthday bot handlers...")
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("geburtstag", start_birthday_registration),
            CommandHandler("gb", start_birthday_registration)
        ],
        states={
            WAITING_FOR_DATE: [
                MessageHandler(filters.TEXT & (~filters.COMMAND), handle_date_input)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_registration)],
        name="birthday_conv",
        persistent=True,
        allow_reentry=True
    )
    return [(conv_handler, 0)]

def get_fallback_handlers():
    return []

def setup_jobs(job_queue):
    job_queue.run_repeating(check_birthdays, interval=60, first=10)
