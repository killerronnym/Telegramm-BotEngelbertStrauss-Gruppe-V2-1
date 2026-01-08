import logging
import os
import json
import re
import sys
from pathlib import Path
from datetime import datetime, timedelta
from telegram import Update, ChatInviteLink
from telegram.helpers import escape_markdown
from telegram.error import TelegramError
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    ChatJoinRequestHandler,
    filters,
)

# --- Setup Logging (Direct to File & Console) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, 'invite_bot.log')

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# --- Dateien & Speicher -----------------------------------------
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DATA_DIR = Path(os.path.join(PROJECT_ROOT, "data"))
DATA_DIR.mkdir(exist_ok=True)

CONFIG_FILE = Path(BASE_DIR) / 'invite_bot_config.json'
PROFILES_FILE = DATA_DIR / "profiles.json"
USER_INTERACTIONS_LOG_FILE = Path(BASE_DIR) / 'user_interactions.log'

def load_config():
    default = {
        "is_enabled": False,
        "bot_token": "",
        "main_chat_id": "",
        "topic_id": "",
        "link_ttl_minutes": 15,
        "repost_profile_for_existing_members": True,
        "start_message": "Willkommen! Nutze /letsgo zum Starten.",
        "rules_message": "Bitte bestätige die Regeln mit OK.",
        "privacy_policy": "Datenschutzerklärung wurde noch nicht konfiguriert.",
        "form_fields": []
    }
    if not CONFIG_FILE.exists(): return default
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except: return default

def log_user_interaction(user_id: int, username: str, action: str, details: str = ""):
    with open(USER_INTERACTIONS_LOG_FILE, 'a', encoding='utf-8') as f:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        user_info = f"@{username}" if username else f"ID:{user_id}"
        safe_details = str(details).replace('|', ':')
        f.write(f"[{timestamp}] User: {user_info} | Aktion: {action} | Details: {safe_details}\n")

def _load_all_profiles():
    if not PROFILES_FILE.exists(): return {}
    try:
        with PROFILES_FILE.open("r", encoding="utf-8") as f: return json.load(f)
    except: return {}

def save_profile(user_id: int, profile: dict):
    data = _load_all_profiles()
    data[str(user_id)] = profile
    try:
        with PROFILES_FILE.open("w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e: logger.error(f"Fehler beim Speichern der Profile: {e}")

def remove_profile(user_id: int):
    data = _load_all_profiles()
    if str(user_id) in data:
        del data[str(user_id)]
        try:
            with open(PROFILES_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
        except: pass

def escape_md(text):
    if not text: return ""
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(escape_chars)}])", r"\\\1", str(text))

# --- Conversation States ---
FILLING_FORM, CONFIRM_RULES = range(2)

def get_enabled_fields(config):
    return [f for f in config.get("form_fields", []) if f.get("enabled", True)]

async def ask_next_field(update: Update, context: ContextTypes.DEFAULT_TYPE, config: dict):
    fields = get_enabled_fields(config)
    current_idx = context.user_data.get("form_idx", 0)
    
    if current_idx >= len(fields):
        # ✅ FIX: Load customizable rules message
        regeln = config.get("rules_message", "Bitte bestätige die Regeln mit OK.")
        try:
            await update.effective_message.reply_text(regeln, parse_mode="MarkdownV2")
        except:
            await update.effective_message.reply_text(regeln.replace('*','').replace('_','').replace('\\',''))
        log_user_interaction(update.effective_user.id, update.effective_user.username, "Formular Ende", "Regeln werden angezeigt")
        return CONFIRM_RULES

    field = fields[current_idx]
    label = escape_md(field["label"])
    if not field.get("required"): label += "\n\n_Diese Frage kannst du mit **nein** überspringen\\._"
    
    await update.effective_message.reply_text(label, parse_mode="MarkdownV2")
    log_user_interaction(update.effective_user.id, update.effective_user.username, "Frage gestellt", f"Feld: {field['id']}")
    return FILLING_FORM

async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config = load_config()
    log_user_interaction(update.effective_user.id, update.effective_user.username, "Command /start", "Willkommensnachricht")
    raw_text = config.get("start_message", "👋 *Hey!* \n\n👉 *Schreibe /letsgo, um zu starten!*")
    try:
        await update.message.reply_text(raw_text, parse_mode="MarkdownV2")
    except Exception as e:
        logger.error(f"Markdown Error in welcome: {e}")
        await update.message.reply_text(raw_text.replace('*','').replace('\\',''))

async def datenschutz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_user_interaction(update.effective_user.id, update.effective_user.username, "Command /datenschutz", "Datenschutz aufgerufen")
    config = load_config()
    text = config.get("privacy_policy", "Keine Datenschutzerklärung hinterlegt.")
    try:
        await update.message.reply_text(text, parse_mode="MarkdownV2")
    except Exception as e:
        logger.error(f"Markdown Error in privacy: {e}")
        await update.message.reply_text(text.replace('*','').replace('\\',''))

async def start_form(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_user_interaction(update.effective_user.id, update.effective_user.username, "Command /letsgo", "Formular gestartet")
    config = load_config()
    if not config.get("main_chat_id"):
        await update.message.reply_text("⚠️ Bot ist noch nicht fertig konfiguriert (Gruppen-ID fehlt).")
        return ConversationHandler.END
    context.user_data["form_idx"] = 0
    context.user_data["answers"] = {"telegram_id": update.effective_user.id, "username": update.effective_user.username or "", "first_name": update.effective_user.first_name or ""}
    return await ask_next_field(update, context, config)

async def handle_field_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config = load_config()
    fields = get_enabled_fields(config)
    idx = context.user_data.get("form_idx", 0)
    if idx >= len(fields): return ConversationHandler.END
    field = fields[idx]
    user_input = ""
    
    # Validation Logic
    if field["type"] == "photo":
        if not update.message.photo:
            if not field.get("required") and update.message.text and update.message.text.lower() == "nein": user_input = None
            else:
                await update.message.reply_text("Bitte sende ein Foto.")
                log_user_interaction(update.effective_user.id, update.effective_user.username, "Input Fehler", f"Erwartete Foto für {field['id']}")
                return FILLING_FORM
        else: user_input = update.message.photo[-1].file_id
    elif field["type"] == "number":
        user_input = update.message.text.strip() if update.message.text else ""
        if not user_input and field.get("required"):
            await update.message.reply_text("Bitte gib eine Zahl ein.")
            return FILLING_FORM
        if user_input.lower() == "nein" and not field.get("required"):
            user_input = None
        else:
            if not user_input.isdigit():
                await update.message.reply_text("Bitte gib dein Alter als reine Zahl ein (z.B. 25).")
                log_user_interaction(update.effective_user.id, update.effective_user.username, "Input Fehler", f"Keine Zahl für {field['id']}: {user_input}")
                return FILLING_FORM
            
            val = int(user_input)
            min_v = field.get("min_value")
            max_v = field.get("max_value")
            
            if min_v is not None and val < min_v:
                await update.message.reply_text(f"Du musst mindestens {min_v} Jahre alt sein.")
                log_user_interaction(update.effective_user.id, update.effective_user.username, "Validierung Fehler", f"Zu jung ({val} < {min_v})")
                return FILLING_FORM
            if max_v is not None and val > max_v:
                await update.message.reply_text(f"Das Alter darf maximal {max_v} sein.")
                log_user_interaction(update.effective_user.id, update.effective_user.username, "Validierung Fehler", f"Zu alt ({val} > {max_v})")
                return FILLING_FORM

    else: # Text
        user_input = update.message.text.strip() if update.message.text else ""
        if not user_input and field.get("required"):
            await update.message.reply_text("Bitte gib eine Antwort ein.")
            log_user_interaction(update.effective_user.id, update.effective_user.username, "Input Fehler", f"Leerer Text für {field['id']}")
            return FILLING_FORM
        if user_input and user_input.lower() == "nein" and not field.get("required"): user_input = None

    context.user_data["answers"][field["id"]] = user_input
    log_detail = "Foto" if field["type"] == "photo" and user_input else (user_input if user_input else "Übersprungen")
    log_user_interaction(update.effective_user.id, update.effective_user.username, "Antwort erhalten", f"Feld: {field['id']} | Wert: {log_detail}")
    context.user_data["form_idx"] = idx + 1
    return await ask_next_field(update, context, config)

async def rules_confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip().lower() != "ok":
        await update.message.reply_text("Bitte antworte mit *OK*, um fortzufahren\\.", parse_mode="MarkdownV2")
        return CONFIRM_RULES
    log_user_interaction(update.effective_user.id, update.effective_user.username, "Regeln akzeptiert", "Abgeschlossen")
    user_id = update.effective_user.id
    profile = context.user_data["answers"]
    profile["created_at"] = datetime.utcnow().isoformat()
    save_profile(user_id, profile)
    config = load_config()
    group_id = int(config["main_chat_id"])
    try:
        link = await context.bot.create_chat_invite_link(chat_id=group_id, expire_date=datetime.utcnow() + timedelta(minutes=config.get("link_ttl_minutes", 15)), creates_join_request=True)
        await update.message.reply_text(f"✅ Hier ist dein Link:\n{link.invite_link}")
        log_user_interaction(user_id, update.effective_user.username, "Link gesendet", link.invite_link)
    except Exception as e:
        logger.error(f"Link Error: {e}")
        await update.message.reply_text("Fehler beim Link.")
    return ConversationHandler.END

async def post_profile_to_group(context, profile, config):
    chat_id = int(config["main_chat_id"])
    topic_id = config.get("topic_id")
    def esc(t): return escape_md(str(t))
    user_link = f"[{esc(profile.get('username') or profile.get('first_name'))}](tg://user?id={profile['telegram_id']})"
    lines = ["🎉 *Neuer Steckbrief\\!*", f"👤 *User:* {user_link}"]
    photo_id = None
    for f in config.get("form_fields", []):
        val = profile.get(f["id"])
        if val:
            if f["type"] == "photo": photo_id = val
            else: lines.append(f"🔹 *{esc(f['label'])}* {esc(val)}")
    text = "\n".join(lines)
    try:
        if photo_id: await context.bot.send_photo(chat_id=chat_id, photo=photo_id, caption=text, parse_mode="MarkdownV2", message_thread_id=topic_id)
        else: await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="MarkdownV2", message_thread_id=topic_id)
    except Exception as e: logger.error(f"Post failed: {e}")

async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.chat_join_request.from_user.id
    config = load_config()
    await context.bot.approve_chat_join_request(chat_id=int(config["main_chat_id"]), user_id=user_id)
    profiles = _load_all_profiles()
    profile = profiles.get(str(user_id))
    if profile:
        await post_profile_to_group(context, profile, config)
        remove_profile(user_id)

if __name__ == "__main__":
    config = load_config()
    if not config.get("bot_token"):
        logger.error("Kein Token konfiguriert!")
        sys.exit(1)
    logger.info("Bot-System startet...")
    app = ApplicationBuilder().token(config["bot_token"]).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("letsgo", start_form)],
        states={FILLING_FORM: [MessageHandler(filters.ALL & ~filters.COMMAND, handle_field_input)], CONFIRM_RULES: [MessageHandler(filters.TEXT & ~filters.COMMAND, rules_confirmed)]},
        fallbacks=[CommandHandler("start", welcome)],
    )
    app.add_handler(CommandHandler("start", welcome))
    app.add_handler(CommandHandler("datenschutz", datenschutz))
    app.add_handler(conv)
    app.add_handler(ChatJoinRequestHandler(handle_join_request))
    logger.info("Bot ist bereit und wartet auf Nachrichten.")
    app.run_polling()
