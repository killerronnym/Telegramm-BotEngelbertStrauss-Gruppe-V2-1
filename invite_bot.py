import logging
import os
import json
from pathlib import Path
from datetime import datetime, timedelta
from telegram import Update, ChatInviteLink
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    ChatJoinRequestHandler,
    filters,
)

# --- Setup ------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# --- Dateien & Speicher -----------------------------------------
BOT_SETTINGS_CONFIG_FILE = 'bot_settings_config.json' # <-- NEU: Konfigurationsdatei für Bot-Einstellungen

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
PROFILES_FILE = DATA_DIR / "profiles.json"

FREIWILLIG_HINT = "_Diese Frage kannst du mit **nein** überspringen._"

def load_json(file_path, default_data):
    if not Path(file_path).exists() or Path(file_path).stat().st_size == 0:
        return default_data
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return default_data

def load_bot_settings_config():
    default = {
        "is_enabled": False,
        "bot_token": "", # <-- NEU: Bot-Token für diesen Bot
        "main_chat_id": "",
        "link_ttl_minutes": 15
    }
    return load_json(BOT_SETTINGS_CONFIG_FILE, default)

def is_valid(value: str) -> bool:
    return value and value.strip().lower() != "nein"

def _load_all_profiles():
    if not PROFILES_FILE.exists():
        return {}
    try:
        with PROFILES_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Fehler beim Laden der Profile: {e}")
        return {}

def _save_all_profiles(data: dict):
    try:
        with PROFILES_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Fehler beim Speichern der Profile: {e}")

def save_profile(user_id: int, profile: dict):
    data = _load_all_profiles()
    data[str(user_id)] = profile
    _save_all_profiles(data)

def load_profile(user_id: int):
    return _load_all_profiles().get(str(user_id))

def remove_profile(user_id: int):
    data = _load_all_profiles()
    if str(user_id) in data:
        del data[str(user_id)]
        _save_all_profiles(data)

# --- States -----------------------------------------------------
ASK_NAME, ASK_AGE, ASK_STATE, ASK_PHOTO, ASK_SECURITY, ASK_HOBBIES, ASK_INSTAGRAM, ASK_OTHER, ASK_SEXUALITY, ASK_RULES = range(10)
user_data_temp = {}

# --- Commands ---------------------------------------------------
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE): # type: ignore
    text = (
        "👋 *Hey und herzlich willkommen!*\n\n"
        "Du bist hier, weil du in unsere *Engelbert‑Strauss Gruppe* möchtest 👷‍♂️🦺\n\n"
        "Damit wir wissen, wer du bist und dich richtig freischalten können, hilft dir dieser Bot dabei, "
        "einen kurzen Steckbrief auszufüllen 📋\n\n"
        "➡️ Das dauert nur *1–2 Minuten!*\n"
        "➡️ Danach bekommst du *automatisch den Einladungslink* zur Gruppe 🔗\n\n"
        "Das hier ist *kein Spam*, sondern eine kleine Sicherheitsabfrage ✅\n\n"
        "👉 *Schreibe jetzt einfach /letsgo, um zu starten!*"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def start_form(update: Update, context: ContextTypes.DEFAULT_TYPE): # type: ignore
    await update.message.reply_text("Wie ist dein Name? Es reicht dein Vorname.")
    return ASK_NAME


# --- Formular Schritte ------------------------------------------
async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE): # type: ignore
    logger.info(f"DEBUG: get_name triggered. User ID: {update.message.from_user.id}, Text: {update.message.text}") # <-- NEUE DEBUG-AUSGABE
    user = update.message.from_user
    user_data_temp[user.id] = {
        "name": update.message.text.strip(),
        "telegram_id": user.id,
        "username": user.username or "",
        "first_name": user.first_name or "",
    }
    await update.message.reply_text("Wie alt bist du? (zwischen 10 und 100)")
    return ASK_AGE


async def get_age(update: Update, context: ContextTypes.DEFAULT_TYPE): # type: ignore
    age_text = update.message.text.strip()
    if not age_text.isdigit() or not 10 <= int(age_text) <= 100:
        await update.message.reply_text("Bitte gib dein Alter als Zahl zwischen 10 und 100 ein.")
        return ASK_AGE
    user_data_temp[update.message.from_user.id]["age"] = age_text
    await update.message.reply_text("Aus welchem Bundesland kommst du? (z.B. NRW, Bayern, Berlin …)")
    return ASK_STATE


async def get_state(update: Update, context: ContextTypes.DEFAULT_TYPE): # type: ignore
    user_data_temp[update.message.from_user.id]["state"] = update.message.text.strip()
    await update.message.reply_text("Bitte sende ein *normales Foto* von dir (kein Dokument).", parse_mode="Markdown")
    return ASK_PHOTO


async def get_photo(update: Update, context: ContextTypes.DEFAULT_TYPE): # type: ignore
    user_id = update.message.from_user.id
    if not update.message.photo:
        await update.message.reply_text("Bitte sende ein Foto, kein Dokument.")
        return ASK_PHOTO
    user_data_temp[user_id]["photo_file_id"] = update.message.photo[-1].file_id
    await update.message.reply_text(f"💥 Was ist dein Kink oder Fetisch?\n\n{FREIWILLIG_HINT}", parse_mode="Markdown")
    return ASK_SECURITY


async def get_security(update: Update, context: ContextTypes.DEFAULT_TYPE): # type: ignore
    text = update.message.text.strip()
    if is_valid(text):
        user_data_temp[update.message.from_user.id]["security"] = text
    await update.message.reply_text(f"🎯 Was sind deine Hobbys oder Interessen?\n\n{FREIWILLIG_HINT}", parse_mode="Markdown")
    return ASK_HOBBIES


async def get_hobbies(update: Update, context: ContextTypes.DEFAULT_TYPE): # type: ignore
    text = update.message.text.strip()
    if is_valid(text):
        user_data_temp[update.message.from_user.id]["hobbies"] = text
    await update.message.reply_text(f"📱 Trage hier deinen Instagram oder einen anderen Social Media Account ein:\n\n{FREIWILLIG_HINT}", parse_mode="Markdown")
    return ASK_INSTAGRAM


async def get_instagram(update: Update, context: ContextTypes.DEFAULT_TYPE): # type: ignore
    text = update.message.text.strip()
    if is_valid(text):
        user_data_temp[update.message.from_user.id]["instagram"] = text
    await update.message.reply_text(f"💬 Möchtest du noch etwas über dich sagen?\n\n{FREIWILLIG_HINT}", parse_mode="Markdown")
    return ASK_OTHER


async def get_other(update: Update, context: ContextTypes.DEFAULT_TYPE): # type: ignore
    text = update.message.text.strip()
    if is_valid(text):
        user_data_temp[update.message.from_user.id]["other"] = text
    await update.message.reply_text(f"🏳️‍🌈 Wie ist deine Sexualität?\n\n{FREIWILLIG_HINT}", parse_mode="Markdown")
    return ASK_SEXUALITY


async def get_sexuality(update: Update, context: ContextTypes.DEFAULT_TYPE): # type: ignore
    text = update.message.text.strip()
    if is_valid(text):
        user_data_temp[update.message.from_user.id]["sexuality"] = text

    regeln = (
        "📜 *Bevor du in die Gruppe kommst, lies bitte unsere Regeln:*\n\n"
        "✅ *DOS:*\n"
        "• Respektvoller Umgang\n"
        "• Überwiegend gute Laune 😄\n\n"
        "❌ *DON'TS:*\n"
        "✖️ Beleidigungen\n"
        "✖️ Diskriminierung\n"
        "✖️ Hardcore-Inhalte\n"
        "✖️ Blut oder offene Wunden\n"
        "✖️ Inhalte mit Kindern\n"
        "✖️ Inhalte mit Tieren (sexuell)\n"
        "✖️ Inhalte mit Bezug auf Tod\n"
        "✖️ Exkremente\n\n"
        "_Verstöße werden durch Admins geprüft und bei Wiederholung erfolgt Ausschluss._\n\n"
        "👉 *Wenn du einverstanden bist, bestätige mit OK.*"
    )
    await update.message.reply_text(regeln, parse_mode="Markdown")
    return ASK_RULES


async def get_rules_ok(update: Update, context: ContextTypes.DEFAULT_TYPE): # type: ignore
    if update.message.text.strip().lower() != "ok":
        await update.message.reply_text("Bitte antworte mit *OK*, um den Regeln zuzustimmen.", parse_mode="Markdown")
        return ASK_RULES

    user_id = update.message.from_user.id
    user_data_temp[user_id]["created_at"] = datetime.utcnow().isoformat()
    save_profile(user_id, user_data_temp[user_id])

    config = load_bot_settings_config()
    GROUP_ID = int(config.get("main_chat_id", 0)) if config.get("main_chat_id") else 0
    LINK_TTL_MINUTES = config.get("link_ttl_minutes", 15)

    if not GROUP_ID:
        logger.error("GROUP_ID ist nicht konfiguriert. Kann keinen Einladungslink erstellen.")
        await update.message.reply_text("⚠️ Fehler: Die Gruppen-ID ist nicht konfiguriert. Bitte informiere einen Administrator.")
        user_data_temp.pop(user_id, None)
        return ConversationHandler.END

    try:
        link: ChatInviteLink = await context.bot.create_chat_invite_link(
            chat_id=GROUP_ID,
            expire_date=datetime.utcnow() + timedelta(minutes=LINK_TTL_MINUTES),
            creates_join_request=True,
        )
        await update.message.reply_text(f"✅ Super! Hier ist dein Einladungslink (gültig für {LINK_TTL_MINUTES} Minuten):\n{link.invite_link}")
    except Exception as e:
        logger.error(f"Fehler beim Link-Erstellen: {e}")
        await update.message.reply_text("⚠️ Fehler beim Erstellen des Links. Bitte versuche es später erneut.")

    user_data_temp.pop(user_id, None)
    return ConversationHandler.END


# --- Willkommensnachricht in Gruppe -----------------------------
def format_welcome(profile: dict) -> str:
    lines = [
        f"🎉 *Willkommen in der Gruppe!*",
        f"👤 *Name:* {profile.get('name', '-')}",
        f"🎂 *Alter:* {profile.get('age', '-')}",
        f"📍 *Bundesland:* {profile.get('state', '-')}",
        f"🔗 *Telegram:* @{profile.get('username') or 'Kein Benutzername'}",
    ]
    if is_valid(profile.get("security", "")):
        lines.append(f"💥 *Kink/Fetisch:* {profile['security']}")
    if is_valid(profile.get("hobbies", "")):
        lines.append(f"🎯 *Hobbys:* {profile['hobbies']}")
    if is_valid(profile.get("instagram", "")):
        lines.append(f"📱 *Social Media:* {profile['instagram']}")
    if is_valid(profile.get("other", "")):
        lines.append(f"💬 *Sonstiges:* {profile['other']}")
    if is_valid(profile.get("sexuality", "")):
        lines.append(f"🏳️‍🌈 *Sexualität:* {profile['sexuality']}")
    lines.append(f"🕐 *Beigetreten am:* {datetime.now().strftime('%d.%m.%Y – %H:%M')}")
    return "\n".join(lines)


async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE): # type: ignore
    user = update.chat_join_request.from_user
    profile = load_profile(user.id)

    config = load_bot_settings_config()
    GROUP_ID = int(config.get("main_chat_id", 0)) if config.get("main_chat_id") else 0

    if not GROUP_ID:
        logger.error("GROUP_ID ist nicht konfiguriert. Kann Beitrittsanfrage nicht bearbeiten.")
        # Hier könnte man die Anfrage ablehnen oder eine Nachricht senden
        return

    try:
        await context.bot.approve_chat_join_request(chat_id=GROUP_ID, user_id=user.id)
    except Exception as e:
        logger.error(f"Genehmigung fehlgeschlagen: {e}")
        return
    if profile:
        welcome = format_welcome(profile)
        try:
            if profile.get("photo_file_id"):
                await context.bot.send_photo(chat_id=GROUP_ID, photo=profile["photo_file_id"], caption=welcome, parse_mode="Markdown")
            else:
                await context.bot.send_message(chat_id=GROUP_ID, text=welcome, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Fehler bei Begrüßung: {e}")
        remove_profile(user.id)


# --- Wenn jemand die Gruppe verlässt -----------------------------
async def handle_member_left(update: Update, context: ContextTypes.DEFAULT_TYPE): # type: ignore
    if not update.message or not update.message.left_chat_member: return
    user = update.message.left_chat_member
    if user:
        user_id_str = str(user.id)
        if user_id_str in _load_all_profiles():
            remove_profile(user.id)
            config = load_bot_settings_config()
            GROUP_ID = int(config.get("main_chat_id", 0)) if config.get("main_chat_id") else 0
            if GROUP_ID:
                try:
                    await context.bot.send_message(
                        chat_id=GROUP_ID,
                        text=f"👋 {user.full_name} hat die Gruppe verlassen. Steckbrief wurde gelöscht."
                    )
                except Exception as e:
                    logger.error(f"Fehler beim Senden der Austrittsnachricht: {e}")
            else:
                logger.warning("GROUP_ID ist nicht konfiguriert. Kann Austrittsnachricht nicht senden.")
        else:
            logger.warning(f"⚠️ Kein Profil gefunden für Benutzer {user_id_str}.")


# --- Bot Start --------------------------------------------------
if __name__ == "__main__":
    config = load_bot_settings_config()
    BOT_TOKEN = config.get("bot_token")
    is_enabled = config.get("is_enabled", False)

    if not BOT_TOKEN or BOT_TOKEN == "" or not is_enabled:
        logger.info("Invite-Bot ist nicht aktiviert oder BOT_TOKEN fehlt in bot_settings_config.json. Wird nicht gestartet.")
    else:
        app = ApplicationBuilder().token(BOT_TOKEN).build()

        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("letsgo", start_form)],
            states={
                ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
                ASK_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_age)],
                ASK_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_state)],
                ASK_PHOTO: [MessageHandler(filters.PHOTO, get_photo)],
                ASK_SECURITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_security)],
                ASK_HOBBIES: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_hobbies)],
                ASK_INSTAGRAM: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_instagram)],
                ASK_OTHER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_other)],
                ASK_SEXUALITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_sexuality)],
                ASK_RULES: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_rules_ok)],
            },
            fallbacks=[],
            per_message=False,
        )

        app.add_handler(CommandHandler("start", welcome))
        app.add_handler(conv_handler)
        app.add_handler(ChatJoinRequestHandler(handle_join_request))
        app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, handle_member_left))

        logger.info("🤖 Invite-Bot läuft …")
        app.run_polling()
