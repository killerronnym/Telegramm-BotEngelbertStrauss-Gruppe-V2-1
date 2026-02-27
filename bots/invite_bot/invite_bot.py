import logging
import os
import sys
import json
from datetime import datetime
from typing import Dict, Any, List, Optional

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

from flask import Flask
from web_dashboard.app.models import db, BotSettings, InviteApplication, InviteLog

# Import shared utils for DB URL resolution
from shared_bot_utils import get_db_url, get_bot_config, is_bot_active

# --- Database Helper ---
def get_db_session():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = get_db_url()
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app

flask_app = get_db_session()

# --- Logging Setup --- 
# Corrected paths for logging to be robust regardless of where the script is run from.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
LOGS_DIR = os.path.join(PROJECT_ROOT, 'logs')
INVITE_BOT_LOG_FILE = os.path.join(LOGS_DIR, "invite_bot.log")

# Ensure directories exist before logging attempts
os.makedirs(LOGS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(INVITE_BOT_LOG_FILE, encoding='utf-8'), # Bot's own log
        logging.StreamHandler(sys.stdout) # Output to console as well
    ]
)
logger = logging.getLogger(__name__)

# Globale Variablen komplett ausgebaut, Nutzung von SQLite DB!

def log_user_interaction(user_id, username, message_text):
    try:
        with flask_app.app_context():
            log_entry = InviteLog(telegram_user_id=user_id, username=username or "Unknown", action=message_text)
            db.session.add(log_entry)
            db.session.commit()
    except Exception as e:
        logger.error(f"Fehler beim Schreiben in die Datenbank (InviteLog): {e}")

# Conversation States
ASKING_QUESTIONS, CONFIRMING_RULES, WAITING_FOR_SOCIAL_DECISION, SELECTING_SOCIAL_PLATFORM = range(4)

PLATFORMS = {
    "instagram": {"name": "Instagram", "base_url": "https://instagram.com/"},
    "twitter": {"name": "X (Twitter)", "base_url": "https://x.com/"},
    "bluesky": {"name": "Bluesky", "base_url": "https://bsky.app/profile/"},
    "threads": {"name": "Threads", "base_url": "https://threads.net/@"},
    "tiktok": {"name": "TikTok", "base_url": "https://tiktok.com/@"},
    "snapchat": {"name": "Snapchat", "base_url": "https://snapchat.com/add/"},
    "facebook": {"name": "Facebook", "base_url": "https://facebook.com/"}
}

def detect_social_platform(text: str) -> Optional[Dict[str, str]]:
    """Erkennt Plattform aus URL oder Domain. Gibt {name, url} zurück oder None."""
    t = text.lower().strip()
    
    # URL-Check (darf keine Leerzeichen haben und muss Punkt enthalten oder mit http starten)
    if ' ' in t:
        return None
        
    has_dot = '.' in t
    is_url = t.startswith("http") or has_dot
    
    if not is_url:
        return None

    # Falls http fehlt, ergänzen für die finale URL
    final_url = text.strip()
    if not t.startswith("http"):
        final_url = f"https://{final_url}"

    # Bekannte Plattformen prüfen
    for key, data in PLATFORMS.items():
        if key in t or (key == "twitter" and "x.com" in t):
            return {"name": data["name"], "url": final_url}

    # Unbekannte URL: Domain extrahieren (z.B. romeo.com -> Romeo)
    try:
        # Hostname extrahieren
        clean_t = t.replace("https://", "").replace("http://", "").split("/")[0]
        # www. entfernen
        if clean_t.startswith("www."):
            clean_t = clean_t[4:]
            
        parts = clean_t.split(".")
        if len(parts) >= 2:
            # Den Namen vor der TLD nehmen
            domain_name = parts[-2].capitalize()
            return {"name": domain_name, "url": final_url}
    except Exception as e:
        logger.debug(f"detect_social_platform: Fehler beim Domain-Parsing: {e}")

    return {"name": "Link", "url": final_url}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_bot_active('invite'): return
    config = get_bot_config('invite')
    if not config.get('is_enabled'):
        await update.message.reply_text("Der Bot ist zur Zeit deaktiviert.")
        return
    await update.message.reply_text(config.get('start_message', 'Willkommen! Schreibe /letsgo um zu starten.'))
    log_user_interaction(update.effective_user.id, update.effective_user.username, "/start command aufgerufen")

async def datenschutz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_bot_active('invite'): return
    config = get_bot_config('invite')
    policy = config.get('privacy_policy')
    if not policy:
        policy = "Freischaltung aktuell nicht möglich.\n\nFür deinen Account kann im Moment kein Gruppenlink erstellt werden.\nBitte wende dich an einen Administrator, damit das kurz geprüft und ggf. freigeschaltet werden kann 😊\n\n👉 Admin: @didinils"
    await update.message.reply_text(policy)
    log_user_interaction(update.effective_user.id, update.effective_user.username, "/datenschutz aufgerufen")

async def letsgo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_bot_active('invite'): return ConversationHandler.END
    config = get_bot_config('invite')
    if not config.get('is_enabled'):
        await update.message.reply_text("Der Bot ist zur Zeit deaktiviert.")
        return ConversationHandler.END

    log_user_interaction(update.effective_user.id, update.effective_user.username, "/letsgo command aufgerufen")

    # Wir erlauben das Neustarten jederzeit. Falls bereits eine Bewerbung existiert, 
    # wird diese am Ende des Prozesses (nach den Regeln) einfach überschrieben.
    with flask_app.app_context():
        # Wir loggen nur, ob jemand bereits im System ist
        existing_app = InviteApplication.query.filter_by(telegram_user_id=update.effective_user.id).first()
        if existing_app:
            logger.info(f"letsgo: User {update.effective_user.id} startet eine neue Bewerbung (alter Status: {existing_app.status})")

    logger.info(f"letsgo: Starte Bewerbung für User {update.effective_user.id}")
    fields = [f for f in config.get('form_fields', []) if f.get('enabled', True)]
    logger.info(f"letsgo: {len(fields)} aktive Felder gefunden.")
    if not fields:
        await update.message.reply_text("Keine Fragen konfiguriert. Admin kontaktieren.")
        return ConversationHandler.END
    
    context.user_data.clear() # Alles löschen für sauberen Neustart
    context.user_data.update({'fields': fields, 'current_field_index': 0, 'answers': {}})
    
    first_field = fields[0]
    keyboard = None
    if not first_field.get('required'):
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⏭️ Überspringen / Nein", callback_data="skip_field")]])
    
    logger.info(f"letsgo: Sende erste Frage (Index 0): {first_field.get('label', 'Frage?')}")
    await update.message.reply_text(first_field.get('label', 'Frage?'), reply_markup=keyboard)
    return ASKING_QUESTIONS

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    idx = context.user_data.get('current_field_index', 0)
    fields = context.user_data.get('fields', [])
    
    logger.info(f"handle_answer: User {user.id}, Index {idx} von {len(fields)}")
    
    if idx >= len(fields):
        logger.warning(f"handle_answer: Index {idx} out of range for {len(fields)} fields")
        return ASKING_QUESTIONS
        
    field = fields[idx]
    answer = None

    if field['type'] == 'photo':
        if not update.message.photo:
            await update.message.reply_text("Bitte sende ein Foto.")
            return ASKING_QUESTIONS
        answer = update.message.photo[-1].file_id
        log_user_interaction(user.id, user.username, f"Antwort auf {field['id']}: photo {answer}")
    
    answer_text = update.message.text.strip() if update.message.text else ""

    # Validierung für numerische Typen (Zahl oder Puppy Alter)
    if field.get('type') in ['number', 'puppy_age']:
        if not answer_text.isdigit():
            await update.message.reply_text("Bitte gib eine Zahl ein.")
            return ASKING_QUESTIONS
        
        val_number = int(answer_text)
        min_age = field.get('min_age')
        
        if min_age and val_number < int(min_age):
            error_msg = field.get('min_age_error_msg') or f"⚠️ Du musst mindestens {min_age} Jahre alt sein."
            await update.message.reply_text(error_msg)
            return ASKING_QUESTIONS
        
        answer = str(val_number)
    else:
        # Standard Validierung für andere Typen
        if not answer_text and field.get('required'):
            await update.message.reply_text("Diese Antwort ist erforderlich.")
            return ASKING_QUESTIONS
            
        # Social Media / HTML Check
        if field['id'] == 'instagram' or 'social' in field['id'].lower():
            if '<' in answer_text and '>' in answer_text:
                await update.message.reply_text("Bitte sende keine HTML-Inhalte. Gib einfach deinen Benutzernamen oder Link ein.")
                return ASKING_QUESTIONS
            if answer_text.count('http') > 2 or len(answer_text) > 300:
                await update.message.reply_text("Die Eingabe ist zu lang oder enthält zu viele Links. Bitte gib nur deinen Social Media Namen oder Profil-Link an.")
                return ASKING_QUESTIONS
        
        answer = answer_text

    logger.info(f"handle_answer: Speichere Antwort für {field['id']}. Nächster Index: {idx+1}")
    log_user_interaction(user.id, user.username, f"Antwort auf {field['id']}: {answer}")
    
    # --- Multi-Social Support (nur wenn Social Media) ---
    is_social = field['id'] == 'instagram' or 'social' in field['id'].lower()
    if is_social and answer.lower() != 'nein': # 'nein' allows skipping social fields
        detected = detect_social_platform(answer)
        if detected:
            if field['id'] not in context.user_data['answers']:
                context.user_data['answers'][field['id']] = []
            context.user_data['answers'][field['id']].append(detected)
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("Ja, noch einen", callback_data="social_add_yes"),
                 InlineKeyboardButton("Nein, das reicht", callback_data="social_add_no")]
            ])
            await update.message.reply_text(
                f"Erkannt: {detected['name']}. Möchtest du einen weiteren Social Media Link hinzufügen?",
                reply_markup=keyboard
            )
            return WAITING_FOR_SOCIAL_DECISION
        else:
            # Kein Link -> Nach Plattform fragen (Möglichkeit B)
            context.user_data['temp_social_name'] = answer_raw
            keyboard = []
            keys = list(PLATFORMS.keys())
            for i in range(0, len(keys), 2):
                row = [InlineKeyboardButton(PLATFORMS[k]["name"], callback_data=f"social_platform_{k}") for k in keys[i:i+2]]
                keyboard.append(row)
            
            # Sonstiges-Button hinzufügen
            keyboard.append([InlineKeyboardButton("Sonstiges / Nur Link", callback_data="social_platform_other")])
            
            await update.message.reply_text(
                f"Für welche Plattform ist der Name '{answer_raw}'?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return SELECTING_SOCIAL_PLATFORM

    logger.info(f"handle_answer: Speichere Antwort für {field['id']}. Nächster Index: {idx+1}")
    context.user_data['answers'][field['id']] = answer
    return await next_question(update, context)

async def handle_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    idx = context.user_data.get('current_field_index', 0)
    fields = context.user_data.get('fields', [])
    field = fields[idx]
    
    logger.info(f"handle_skip: User überspringt Feld {field['id']}")
    context.user_data['answers'][field['id']] = "n/a" # Oder leer lassen
    return await next_question(update, context)

async def next_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    idx = context.user_data.get('current_field_index', 0) + 1
    fields = context.user_data.get('fields', [])
    context.user_data['current_field_index'] = idx
    
    effective_chat_id = update.effective_chat.id

    if idx < len(fields):
        next_field = fields[idx]
        next_label = next_field.get('label', 'Nächste Frage?')
        
        keyboard = None
        if not next_field.get('required'):
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⏭️ Überspringen / Nein", callback_data="skip_field")]])
            
        logger.info(f"next_question: Sende nächste Frage (Index {idx}): {next_label}")
        if update.callback_query:
            await context.bot.send_message(chat_id=effective_chat_id, text=next_label, reply_markup=keyboard)
        else:
            await update.message.reply_text(next_label, reply_markup=keyboard)
        return ASKING_QUESTIONS
    else:
        logger.info(f"next_question: Alle Fragen beantwortet. Sende Regeln.")
        config = get_bot_config('invite')
        rules = config.get('rules_message', 'Danke!')
        msg = f"{rules}\n\nSchreibe 'ok' zum Bestätigen."
        if update.callback_query:
            await context.bot.send_message(chat_id=effective_chat_id, text=msg)
        else:
            await update.message.reply_text(msg)
        return CONFIRMING_RULES

async def handle_social_platform_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    platform_key = query.data.replace("social_platform_", "")
    
    if platform_key == "other":
        platform_data = {"name": "Link", "base_url": ""}
        name = context.user_data.pop('temp_social_name', 'Nutzer')
        # Falls es doch eine URL ist aber als "Other" gewählt wurde, Link so lassen
        url = name if any(x in name.lower() for x in ['.com', '.de', 'http']) else f"{name}"
    else:
        platform_data = PLATFORMS.get(platform_key)
        if not platform_data:
            return SELECTING_SOCIAL_PLATFORM
        name = context.user_data.pop('temp_social_name', 'Nutzer')
        url = f"{platform_data['base_url']}{name.lstrip('@')}"
    
    idx = context.user_data.get('current_field_index', 0)
    fields = context.user_data.get('fields', [])
    field_id = fields[idx]['id']
    
    if field_id not in context.user_data['answers']:
        context.user_data['answers'][field_id] = []
    context.user_data['answers'][field_id].append({"name": platform_data["name"], "url": url})
    
    await query.edit_message_text(f"Gespeichert: {platform_data['name']} ({name})")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Ja, noch einen", callback_data="social_add_yes"),
         InlineKeyboardButton("Nein, das reicht", callback_data="social_add_no")]
    ])
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Möchtest du einen weiteren Social Media Link hinzufügen?",
        reply_markup=keyboard
    )
    return WAITING_FOR_SOCIAL_DECISION

async def handle_social_decision_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    action = query.data.replace("social_add_", "")
    idx = context.user_data.get('current_field_index', 0)
    fields = context.user_data.get('fields', [])
    
    if action == 'yes':
        await query.edit_message_text("✅ Weiteren Link hinzufügen gewählt.")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=fields[idx].get('label', 'Noch ein Link?')
        )
        return ASKING_QUESTIONS
    else:
        await query.edit_message_text("✅ Keine weiteren Links.")
        # Weiter zur nächsten Frage
        idx += 1
        context.user_data['current_field_index'] = idx
        
        if idx < len(fields):
            next_label = fields[idx].get('label', 'Nächste Frage?')
            await context.bot.send_message(chat_id=update.effective_chat.id, text=next_label)
            return ASKING_QUESTIONS
        else:
            config = get_bot_config('invite')
            rules = config.get('rules_message', 'Danke!')
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"{rules}\n\nSchreibe 'ok' zum Bestätigen.")
            return CONFIRMING_RULES

async def handle_social_decision(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.lower().strip() if update.message.text else ""
    idx = context.user_data.get('current_field_index', 0)
    fields = context.user_data.get('fields', [])
    
    if text == 'ja':
        # Erneut nach Social Media fragen (gleicher Index)
        await update.message.reply_text(fields[idx].get('label', 'Noch ein Link?'))
        return ASKING_QUESTIONS
    else:
        # Weiter zur nächsten Frage
        idx += 1
        context.user_data['current_field_index'] = idx
        
        if idx < len(fields):
            next_label = fields[idx].get('label', 'Nächste Frage?')
            await update.message.reply_text(next_label)
            return ASKING_QUESTIONS
        else:
            config = get_bot_config('invite')
            rules = config.get('rules_message', 'Danke!')
            await update.message.reply_text(f"{rules}\n\nSchreibe 'ok' zum Bestätigen.")
            return CONFIRMING_RULES

async def post_profile(bot, profile_data: Dict[str, Any], is_approval_post: bool = False):
    target_chat_id = profile_data['target_chat_id']
    kwargs = {"chat_id": target_chat_id}
    
    topic_id_key = 'whitelist_approval_topic_id' if is_approval_post else 'topic_id'
    topic_id = profile_data.get(topic_id_key)

    if topic_id and str(topic_id).isdigit():
        kwargs["message_thread_id"] = int(topic_id)

    if profile_data.get('photo_id'):
        kwargs.update({
            "photo": profile_data['photo_id'], 
            "caption": profile_data['text'][:1024],
            "parse_mode": "HTML"
        })
        await bot.send_photo(**kwargs)
    else:
        kwargs.update({
            "text": profile_data['text'],
            "parse_mode": "HTML"
        })
        await bot.send_message(**kwargs)

async def handle_rules_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    text = update.message.text.lower().strip() if update.message.text else ""
    logger.info(f"handle_rules_confirmation: Nutzer {user.id} schrieb: '{text}'")
    
    if text != 'ok':
        await update.message.reply_text('Bitte schreibe "ok" zum Bestätigen.')
        return CONFIRMING_RULES

    log_user_interaction(user.id, user.username, "Regeln mit OK bestätigt")

    config = get_bot_config('invite')
    chat_id_str = config.get('main_chat_id')
    if not chat_id_str:
        await update.message.reply_text("Bot nicht konfiguriert.")
        return ConversationHandler.END
    target_chat_id = int(chat_id_str) if chat_id_str.lstrip('-').isdigit() else chat_id_str
    
    is_already_member = False
    try:
        member = await context.bot.get_chat_member(chat_id=target_chat_id, user_id=user.id)
        if member:
            if member.status == "kicked":
                await update.message.reply_text(config.get('blocked_message', 'Du bist gesperrt.'))
                return ConversationHandler.END
            if member.status in ["member", "administrator", "creator"]:
                is_already_member = True
                logger.info(f"Nutzer {user.id} ist bereits Mitglied (Status: {member.status}).")
    except BadRequest:
        pass

    # Steckbrief-Daten vorbereiten
    answers = context.user_data['answers']
    ordered_fields = context.user_data.get('fields', [])
    
    # Steckbrief zusammenbauen
    lines = []
    
    photo_file_id = None
    for field in ordered_fields:
        answer = answers.get(field['id'])
        if answer is None or (isinstance(answer, str) and answer.lower().strip() == 'nein'):
            continue
        if field['type'] == 'photo':
            photo_file_id = answer
        else:
            emoji = field.get('emoji', '🔹')
            name = field.get('display_name', field['id'].capitalize())
            
            # Link-Formatierung für Social Media (HTML)
            if field['id'] == 'instagram' or 'social' in field['id'].lower():
                answers_list = answer if isinstance(answer, list) else [answer]
                formatted_socials = []
                for entry in answers_list:
                    if isinstance(entry, dict):
                        formatted_socials.append(f'<a href="{entry["url"]}">{entry["name"]}</a>')
                    else:
                        # Fallback für alte Einträge oder Plain-Text ohne Dictionary
                        formatted_socials.append(str(entry))
                answer = ", ".join(formatted_socials)
            
            steckbrief_lines.append(f"{emoji} {name}: {answer}")
    
    profile_data = {
        'text': "\n".join(steckbrief_lines), 
        'photo_id': photo_file_id,
        'target_chat_id': target_chat_id, 
        'topic_id': config.get('topic_id'),
        'whitelist_approval_topic_id': config.get('whitelist_approval_topic_id')
    }

    if is_already_member:
        approval_chat_id_str = config.get('whitelist_approval_chat_id')
        if not approval_chat_id_str:
            # Fallback falls kein Admin-Chat, posten wir es einfach? 
            # Der User will aber explizit Admin-Entscheidung bei Mitgliedern.
            await update.message.reply_text("Admin-Kanal nicht konfiguriert.")
            return ConversationHandler.END
            
        approval_chat_id = int(approval_chat_id_str) if approval_chat_id_str.lstrip('-').isdigit() else approval_chat_id_str
        
        # In DB speichern als 'pending_existing' (separater Status zur Sicherheit)
        with flask_app.app_context():
            existing_app = InviteApplication.query.filter_by(telegram_user_id=user.id).first()
            if existing_app:
                existing_app.status = 'pending_existing'
                existing_app.answers_json = json.dumps(profile_data)
            else:
                new_app = InviteApplication(
                    telegram_user_id=user.id,
                    username=user.username,
                    full_name=user.full_name,
                    answers_json=json.dumps(profile_data),
                    status='pending_existing'
                )
                db.session.add(new_app)
            db.session.commit()

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Steckbrief posten", callback_data=f"existing_accept_{user.id}"),
            InlineKeyboardButton("❌ Nicht posten", callback_data=f"existing_reject_{user.id}")
        ]])
        
        approval_post_data = profile_data.copy()
        approval_post_data['target_chat_id'] = approval_chat_id
        await post_profile(context.bot, approval_post_data, is_approval_post=True)
        await context.bot.send_message(
            approval_chat_id, 
            f"Nutzer {user.full_name} ist bereits in der Gruppe. Soll der Steckbrief gepostet werden?", 
            reply_markup=keyboard,
            message_thread_id=approval_post_data.get('whitelist_approval_topic_id') if str(approval_post_data.get('whitelist_approval_topic_id')).isdigit() else None
        )
        await update.message.reply_text("Dein Steckbrief wird überprüft, bitte warte.")
        return ConversationHandler.END

    if config.get('whitelist_enabled'):
        approval_chat_id_str = config.get('whitelist_approval_chat_id')
        if not approval_chat_id_str:
            await update.message.reply_text("Whitelist ist aktiv, aber kein Admin-Chat konfiguriert.")
            return ConversationHandler.END
        
        approval_chat_id = int(approval_chat_id_str) if approval_chat_id_str.lstrip('-').isdigit() else approval_chat_id_str
        
        # In Datenbank als 'pending' sichern
        with flask_app.app_context():
            # Alten Status überschreiben falls vorhanden
            existing = InviteApplication.query.filter_by(telegram_user_id=user.id).first()
            if existing:
                existing.status = 'pending'
                existing.answers_json = json.dumps(profile_data)
                existing.full_name = user.full_name
                existing.username = user.username
            else:
                new_app = InviteApplication(
                    telegram_user_id=user.id,
                    username=user.username,
                    full_name=user.full_name,
                    answers_json=json.dumps(profile_data),
                    status='pending'
                )
                db.session.add(new_app)
            db.session.commit()
        
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Annehmen", callback_data=f"whitelist_accept_{user.id}"),
            InlineKeyboardButton("❌ Ablehnen", callback_data=f"whitelist_reject_{user.id}")
        ]])
        
        approval_post_data = profile_data.copy()
        approval_post_data['target_chat_id'] = approval_chat_id
        await post_profile(context.bot, approval_post_data, is_approval_post=True)
        await context.bot.send_message(
            approval_chat_id, 
            "Neue Anfrage zur Freischaltung:", 
            reply_markup=keyboard,
            message_thread_id=approval_post_data.get('whitelist_approval_topic_id') if str(approval_post_data.get('whitelist_approval_topic_id')).isdigit() else None
        )
        await update.message.reply_text(config.get('whitelist_pending_message', 'Dein Antrag wird geprüft.'))
    else:
        # Whitelist ist AUS -> Sofort Link senden
        with flask_app.app_context():
            # In Datenbank als 'accepted' markieren (damit Join-Logik den Steckbrief postet)
            existing = InviteApplication.query.filter_by(telegram_user_id=user.id).first()
            if existing:
                existing.status = 'accepted'
                existing.answers_json = json.dumps(profile_data)
                existing.full_name = user.full_name
                existing.username = user.username
            else:
                new_app = InviteApplication(
                    telegram_user_id=user.id,
                    username=user.username,
                    full_name=user.full_name,
                    answers_json=json.dumps(profile_data),
                    status='accepted'
                )
                db.session.add(new_app)
            db.session.commit()
        
        # Link generieren (Wichtig: Link TTL beachten falls gewünscht, hier Standard)
        try:
            link = await context.bot.create_chat_invite_link(chat_id=target_chat_id, member_limit=1)
            await update.message.reply_text(f"Danke! Deine Anmeldung ist abgeschlossen. Hier ist dein Einladungslink zur Gruppe:\n\n{link.invite_link}")
        except Exception as e:
            logger.error(f"Fehler bei Link-Generierung (Chat ID: {target_chat_id}): {e}")
            await update.message.reply_text(f"❌ Fehler bei Link-Generierung (ID: {target_chat_id}): {e}")

    return ConversationHandler.END

async def handle_whitelist_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    action, user_id_str = query.data.split('_', 2)[1:]
    user_id = int(user_id_str)
    admin_user = query.from_user
    config = get_bot_config('invite')

    with flask_app.app_context():
        application = InviteApplication.query.filter_by(telegram_user_id=user_id).first()
        
        if not application or application.status != 'pending':
            await query.edit_message_text(f"Diese Anfrage ist nicht mehr verfügbar (vielleicht schon bearbeitet?).")
            return
            
        profile_data = application.answers

        if action == "accept":
            target_chat_id = profile_data.get('target_chat_id')
            if target_chat_id:
                try:
                    link = await context.bot.create_chat_invite_link(chat_id=target_chat_id, member_limit=1)
                    await context.bot.send_message(user_id, f"Gute Nachrichten! Deine Anfrage wurde angenommen. Hier ist dein Einladungslink zur Gruppe:\n\n{link.invite_link}")
                    await query.edit_message_text(f"✅ Angenommen von {admin_user.full_name}. Der Nutzer hat den Link erhalten.")
                    application.status = 'accepted'
                    db.session.commit()
                except Exception as e:
                    logger.error(f"Fehler bei Link-Generierung (Accept, ID: {target_chat_id}): {e}")
                    await query.edit_message_text(f"❌ Fehler bei Link-Generierung (ID: {target_chat_id}): {e}")
            else:
                await query.edit_message_text("Fehler: Target Chat ID nicht gefunden.")
                application.status = 'rejected'
                db.session.commit()
                
        elif action == "reject":
            rejection_message = config.get('whitelist_rejection_message', 'Deine Anfrage wurde leider abgelehnt.')
            await context.bot.send_message(user_id, rejection_message)
            await query.edit_message_text(f"❌ Abgelehnt von {admin_user.full_name}. Der Nutzer wurde benachrichtigt.")
            application.status = 'rejected'
            db.session.commit()

async def handle_existing_member_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split('_')
    if len(parts) < 3: return
    
    action = parts[1]
    user_id = int(parts[2])
    admin_user = query.from_user

    with flask_app.app_context():
        application = InviteApplication.query.filter_by(telegram_user_id=user_id).first()
        
        if not application or application.status != 'pending_existing':
            await query.edit_message_text("Diese Anfrage wurde bereits bearbeitet oder ist ungültig.")
            return
            
        profile_data = application.answers

        if action == "accept":
            # Steckbrief posten
            try:
                await post_profile(context.bot, profile_data)
                await context.bot.send_message(user_id, "Dein Steckbrief wurde gepostet!")
                await query.edit_message_text(f"✅ Steckbrief gepostet (Admin: {admin_user.full_name}).")
                application.status = 'completed'
                db.session.commit()
            except Exception as e:
                logger.error(f"Fehler beim Posten des Steckbriefs (Existing): {e}")
                await query.edit_message_text(f"❌ Fehler beim Posten: {e}")
                
        elif action == "reject":
            await context.bot.send_message(user_id, "Dein Steckbrief wird nicht gepostet.")
            await query.edit_message_text(f"❌ Abgelehnt von {admin_user.full_name}. Steckbrief wird nicht gepostet.")
            application.status = 'rejected'
            db.session.commit()

async def handle_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.chat_member or not update.chat_member.new_chat_member or update.chat_member.new_chat_member.status != "member":
        return

    user_id = update.chat_member.new_chat_member.user.id
    
    with flask_app.app_context():
        application = InviteApplication.query.filter_by(telegram_user_id=user_id, status='accepted').first()
        if application:
            profile_data = application.answers # property handles json.loads
            if profile_data and 'text' in profile_data:
                logger.info(f"handle_new_member: Poste Steckbrief für {user_id}")
                # Optional: Header anpassen für Willkommens-Post
                lines = profile_data['text'].split('\n')
                if lines:
                    lines[0] = "🎉 Willkommen in der Gruppe!"
                profile_data['text'] = "\n".join(lines)
                await post_profile(context.bot, profile_data)
                
            application.status = 'completed'
            db.session.commit()

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Prozess abgebrochen.")
    log_user_interaction(update.effective_user.id, update.effective_user.username, "/cancel command aufgerufen")
    return ConversationHandler.END

async def handle_custom_commands(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_bot_active('invite'): return
    if not update.message or not update.message.text: return
    
    text = update.message.text.lower().strip()
    if not text.startswith('/'): return
    
    # Extrahiere Befehl ohne /
    cmd_name = text[1:].split('@')[0].split(' ')[0]
    
    config = get_bot_config('invite')
    custom_commands = config.get('custom_commands', {})
    
    if cmd_name in custom_commands:
        response = custom_commands[cmd_name]
        await update.message.reply_text(response)
        log_user_interaction(update.effective_user.id, update.effective_user.username, f"Custom Command /{cmd_name} ausgeführt")

async def catch_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_bot_active('invite'): return
    if update.effective_chat.type != "private": return
    
    await update.message.reply_text(
        "Ich habe deine Nachricht erhalten, aber aktuell läuft keine Anmeldung.\n\n"
        "Nutze /letsgo um dich für die Gruppe anzumelden oder /start für weitere Infos."
    )

def get_handlers():
    """Gibt die Handler für den Master Bot zurück."""
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("letsgo", letsgo)],
        states={
            ASKING_QUESTIONS: [
                CommandHandler("datenschutz", datenschutz),
                MessageHandler(filters.PHOTO | (filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND), handle_answer)
            ],
            CONFIRMING_RULES: [
                CommandHandler("datenschutz", datenschutz),
                MessageHandler(filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND, handle_rules_confirmation)
            ],
            WAITING_FOR_SOCIAL_DECISION: [
                CommandHandler("datenschutz", datenschutz),
                CallbackQueryHandler(handle_social_decision_callback, pattern=r'^social_add_'),
                MessageHandler(filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND, handle_social_decision)
            ],
            SELECTING_SOCIAL_PLATFORM: [
                CallbackQueryHandler(handle_social_platform_selection, pattern=r'^social_platform_')
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel), 
            CommandHandler("start", start), 
            CommandHandler("datenschutz", datenschutz),
            CallbackQueryHandler(handle_skip, pattern=r'^skip_field$')
        ],
        persistent=True,
        name="invite_conversation",
        allow_reentry=True
    )

    return [
        (conv_handler, 0),
        (CommandHandler("start", start), 0),
        (CommandHandler("datenschutz", datenschutz), 0),
        (CallbackQueryHandler(handle_whitelist_callback, pattern=r'^whitelist_'), 0),
        (CallbackQueryHandler(handle_existing_member_callback, pattern=r'^existing_'), 0),
        (ChatMemberHandler(handle_new_member, ChatMemberHandler.CHAT_MEMBER), 0),
        (MessageHandler(filters.COMMAND, handle_custom_commands), 0)
    ]

def get_fallback_handlers():
    return [
        (MessageHandler(filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND, catch_all), 0)
    ]

# Nur wenn direkt ausgeführt (Legacy Fallback)
if __name__ == "__main__":
    logger.error("Dieses Skript sollte nicht direkt ausgeführt werden. Bitte main_bot.py nutzen.")
