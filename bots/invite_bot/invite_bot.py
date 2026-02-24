import logging
import os
import sys
from datetime import datetime
from typing import Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ChatMemberHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from shared_bot_utils import get_bot_config

# --- Logging Setup --- 
# Corrected paths for logging to be robust regardless of where the script is run from.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
WEB_DASHBOARD_DIR = os.path.join(PROJECT_ROOT, 'web_dashboard')
USER_INTERACTION_LOG_FILE = os.path.join(PROJECT_ROOT, "user_interactions.log")
INVITE_BOT_LOG_FILE = os.path.join(WEB_DASHBOARD_DIR, "invite_bot.log")

# Ensure directories exist before logging attempts
os.makedirs(WEB_DASHBOARD_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(INVITE_BOT_LOG_FILE, encoding='utf-8'), # Bot's own log
        logging.StreamHandler(sys.stdout) # Output to console as well
    ]
)
logger = logging.getLogger(__name__)

# --- Speicher --- 
PENDING_PROFILES: Dict[int, Dict[str, Any]] = {} 
PENDING_WHITELIST: Dict[int, Dict[str, Any]] = {} 

def log_user_interaction(user_id, username, message_text):
    log_entry = f"{datetime.now():%Y-%m-%d %H:%M:%S} - User ID: {user_id} - Username: @{username} - Message: {message_text}\n"
    try:
        with open(USER_INTERACTION_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_entry)
    except Exception as e:
        logger.error(f"Fehler beim Schreiben der User-Log-Datei {USER_INTERACTION_LOG_FILE}: {e}")

# Conversation States
ASKING_QUESTIONS, CONFIRMING_RULES = range(2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config = get_bot_config('invite')
    if not config.get('is_enabled'):
        await update.message.reply_text("Der Bot ist zur Zeit deaktiviert.")
        return
    await update.message.reply_text(config.get('start_message', 'Willkommen! Schreibe /letsgo um zu starten.'))

async def letsgo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    config = get_bot_config('invite')
    if not config.get('is_enabled'):
        await update.message.reply_text("Der Bot ist zur Zeit deaktiviert.")
        return ConversationHandler.END
    fields = [f for f in config.get('form_fields', []) if f.get('enabled', True)]
    if not fields:
        await update.message.reply_text("Keine Fragen konfiguriert. Admin kontaktieren.")
        return ConversationHandler.END
    context.user_data.update({'fields': fields, 'current_field_index': 0, 'answers': {}})
    await update.message.reply_text(fields[0].get('label', 'Frage?'))
    return ASKING_QUESTIONS

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    idx = context.user_data.get('current_field_index', 0)
    fields = context.user_data.get('fields', [])
    field = fields[idx]
    answer = None

    if field['type'] == 'photo':
        if not update.message.photo:
            await update.message.reply_text("Bitte sende ein Foto.")
            return ASKING_QUESTIONS
        answer = update.message.photo[-1].file_id
    else:
        answer_text = update.message.text
        if not answer_text and field.get('required'):
            await update.message.reply_text("Diese Antwort ist erforderlich.")
            return ASKING_QUESTIONS
        if field['type'] == 'number':
            if not answer_text.isdigit():
                await update.message.reply_text("Bitte sende eine gültige Zahl.")
                return ASKING_QUESTIONS
            answer = int(answer_text)
        else:
            answer = answer_text
    
    log_user_interaction(user.id, user.username, f"Antwort auf {field['id']}: {answer if isinstance(answer, (str, int)) else 'Photo'}")
    context.user_data['answers'][field['id']] = answer
    idx += 1
    context.user_data['current_field_index'] = idx
    
    if idx < len(fields):
        await update.message.reply_text(fields[idx].get('label', 'Nächste Frage?'))
        return ASKING_QUESTIONS
    else:
        config = get_bot_config('invite')
        await update.message.reply_text(f"{config.get('rules_message', 'Danke!')}\n\nSchreibe 'ok' zum Bestätigen.")
        return CONFIRMING_RULES

async def post_profile(bot, profile_data: Dict[str, Any], is_approval_post: bool = False):
    target_chat_id = profile_data['target_chat_id']
    kwargs = {"chat_id": target_chat_id}
    
    topic_id_key = 'whitelist_approval_topic_id' if is_approval_post else 'topic_id'
    topic_id = profile_data.get(topic_id_key)

    if topic_id and str(topic_id).isdigit():
        kwargs["message_thread_id"] = int(topic_id)

    if profile_data.get('photo_id'):
        kwargs.update({"photo": profile_data['photo_id'], "caption": profile_data['text']})
        await bot.send_photo(**kwargs)
    else:
        kwargs["text"] = profile_data['text']
        await bot.send_message(**kwargs)

async def handle_rules_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not update.message.text or update.message.text.lower().strip() != 'ok':
        await update.message.reply_text('Bitte schreibe "ok" zum Bestätigen.')
        return CONFIRMING_RULES

    config = get_bot_config('invite')
    chat_id_str = config.get('main_chat_id')
    if not chat_id_str:
        await update.message.reply_text("Bot nicht konfiguriert.")
        return ConversationHandler.END
    target_chat_id = int(chat_id_str) if chat_id_str.lstrip('-').isdigit() else chat_id_str
    
    try:
        member = await context.bot.get_chat_member(chat_id=target_chat_id, user_id=user.id)
        if member and member.status == "kicked":
            await update.message.reply_text(config.get('blocked_message', 'Du bist gesperrt.'))
            return ConversationHandler.END
    except BadRequest:
        pass

    answers = context.user_data['answers']
    ordered_fields = context.user_data.get('fields', [])
    steckbrief_lines = [f"🎉 Steckbrief von {user.full_name} (@{user.username or 'N/A'})"]
    photo_file_id = None
    for field in ordered_fields:
        answer = answers.get(field['id'])
        if answer is None or (isinstance(answer, str) and answer.lower().strip() == 'nein'):
            continue
        if field['type'] == 'photo':
            photo_file_id = answer
        else:
            steckbrief_lines.append(f"{field.get('emoji', '🔹')} {field.get('display_name', field['id'])}: {answer}")
    
    profile_data = {
        'text': "\n".join(steckbrief_lines), 'photo_id': photo_file_id,
        'target_chat_id': target_chat_id, 'topic_id': config.get('topic_id'),
        'whitelist_approval_topic_id': config.get('whitelist_approval_topic_id')
    }

    if config.get('whitelist_enabled'):
        approval_chat_id_str = config.get('whitelist_approval_chat_id')
        if not approval_chat_id_str:
            await update.message.reply_text("Whitelist ist aktiv, aber kein Admin-Chat konfiguriert.")
            return ConversationHandler.END
        
        approval_chat_id = int(approval_chat_id_str) if approval_chat_id_str.lstrip('-').isdigit() else approval_chat_id_str
        PENDING_PROFILES[user.id] = profile_data
        PENDING_WHITELIST[user.id] = {'full_name': user.full_name, 'username': user.username}
        
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Annehmen", callback_data=f"whitelist_accept_{user.id}"),
                                          InlineKeyboardButton("❌ Ablehnen", callback_data=f"whitelist_reject_{user.id}")]])
        
        approval_post_data = profile_data.copy()
        approval_post_data['target_chat_id'] = approval_chat_id
        await post_profile(context.bot, approval_post_data, is_approval_post=True)
        await context.bot.send_message(approval_chat_id, "Neue Anfrage zur Freischaltung:", reply_markup=keyboard, 
                                       message_thread_id=approval_post_data.get('whitelist_approval_topic_id') if str(approval_post_data.get('whitelist_approval_topic_id')).isdigit() else None)
        await update.message.reply_text(config.get('whitelist_pending_message', 'Dein Antrag wird geprüft.'))
    else:
        try:
            member = await context.bot.get_chat_member(chat_id=target_chat_id, user_id=user.id)
            if member and member.status in ["creator", "administrator", "member"]:
                profile_data['text'] = profile_data['text'].replace("Steckbrief von", "Willkommen in der Gruppe!")
                await post_profile(context.bot, profile_data)
                await update.message.reply_text("Dein Steckbrief wurde gepostet!")
            else:
                raise BadRequest("User not a member")
        except BadRequest:
            PENDING_PROFILES[user.id] = profile_data
            link = await context.bot.create_chat_invite_link(chat_id=target_chat_id, member_limit=1)
            await update.message.reply_text(f"Danke! Hier ist dein Link:\n{link.invite_link}")

    return ConversationHandler.END

async def handle_whitelist_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    action, user_id_str = query.data.split('_', 2)[1:]
    user_id = int(user_id_str)
    admin_user = query.from_user
    config = get_bot_config('invite')

    if user_id not in PENDING_WHITELIST and user_id not in PENDING_PROFILES:
        pass

    if user_id not in PENDING_PROFILES:
         await query.edit_message_text(f"Diese Anfrage ist nicht mehr verfügbar (vielleicht schon bearbeitet?).")
         return

    user_info = PENDING_WHITELIST.get(user_id, {'full_name': 'Unknown', 'username': 'Unknown'})
    
    if action == "accept":
        profile_data = PENDING_PROFILES.get(user_id)
        if profile_data:
            target_chat_id = profile_data['target_chat_id']
            link = await context.bot.create_chat_invite_link(chat_id=target_chat_id, member_limit=1)
            await context.bot.send_message(user_id, f"Gute Nachrichten! Deine Anfrage wurde angenommen. Hier ist dein Einladungslink:\n{link.invite_link}")
            await query.edit_message_text(f"✅ Angenommen von {admin_user.full_name}. Der Nutzer hat den Link erhalten.")
            
            # WICHTIG: Profil NICHT löschen! Wir brauchen es für handle_new_member.
            PENDING_WHITELIST.pop(user_id, None)
            
        else:
            await query.edit_message_text("Fehler: Profildaten nicht gefunden.")
            
    elif action == "reject":
        rejection_message = config.get('whitelist_rejection_message', 'Deine Anfrage wurde leider abgelehnt.')
        await context.bot.send_message(user_id, rejection_message)
        await query.edit_message_text(f"❌ Abgelehnt von {admin_user.full_name}. Der Nutzer wurde benachrichtigt.")
        
        # Bei Ablehnung alles löschen
        PENDING_PROFILES.pop(user_id, None)
        PENDING_WHITELIST.pop(user_id, None)

async def handle_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.chat_member or not update.chat_member.new_chat_member or update.chat_member.new_chat_member.status != "member":
        return

    user_id = update.chat_member.new_chat_member.user.id
    
    if user_id in PENDING_PROFILES:
        profile_data = PENDING_PROFILES.pop(user_id)
        profile_data['text'] = profile_data['text'].replace("Steckbrief von", "Willkommen in der Gruppe!")
        
        await post_profile(context.bot, profile_data)
        
        PENDING_WHITELIST.pop(user_id, None)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Prozess abgebrochen.")
    return ConversationHandler.END

def run_bot():
    try:
        config = get_bot_config('invite')
        token = config.get('bot_token')
        if not token:
            logger.error("Kein Bot Token in der Datenbank gefunden. Bot startet nicht.")
            return

        application = Application.builder().token(token).build()
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("letsgo", letsgo)],
            states={
                ASKING_QUESTIONS: [MessageHandler(filters.TEXT | filters.PHOTO, handle_answer)],
                CONFIRMING_RULES: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_rules_confirmation)],
            },
            fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)],
        )
        application.add_handler(conv_handler)
        # HIER: /start Befehl auch außerhalb des Dialogs verfügbar machen
        application.add_handler(CommandHandler("start", start))
        
        application.add_handler(CallbackQueryHandler(handle_whitelist_callback, pattern=r'^whitelist_'))
        application.add_handler(ChatMemberHandler(handle_new_member, ChatMemberHandler.CHAT_MEMBER))
        
        logger.info("Invite Bot gestartet und lauscht auf Updates...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

    except Exception as e:
        logger.exception(f"Kritischer Fehler im Invite Bot: {e}")

if __name__ == "__main__":
    run_bot()
