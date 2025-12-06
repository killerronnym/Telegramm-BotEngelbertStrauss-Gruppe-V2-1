import logging
import os
import json
import re
from pathlib import Path
from datetime import datetime, timedelta
from telegram import Update, ChatInviteLink
from telegram.helpers import escape_markdown
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
    level=logging.INFO, # Changed back to INFO for production, use DEBUG for detailed local debugging
)
logger = logging.getLogger(__name__)

# --- Dateien & Speicher -----------------------------------------
BOT_SETTINGS_CONFIG_FILE = 'bot_settings_config.json'
USER_INTERACTIONS_LOG_FILE = 'user_interactions.log'

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
PROFILES_FILE = DATA_DIR / "profiles.json"

FREIWILLIG_HINT = "_Diese Frage kannst du mit **nein** überspringen\\._"

def log_user_interaction(user_id: int, question: str, answer: str):
    """Loggt die Eingaben des Benutzers in eine separate Datei."""
    with open(USER_INTERACTIONS_LOG_FILE, 'a', encoding='utf-8') as f:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        f.write(f"[{timestamp}] UserID: {user_id}\n  Frage: {question}\n  Antwort: {answer}\n\n")

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
        "bot_token": "",
        "main_chat_id": "",
        "topic_id": "",
        "link_ttl_minutes": 15,
        "repost_profile_for_existing_members": True
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

async def reply_with_developer_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("Vielen Dank\\. Ich wurde entwickelt von @pup_Rinno_cgn", parse_mode="MarkdownV2")

# --- Commands ---------------------------------------------------
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 *Hey und herzlich willkommen\\!* \n\n"
        "Du bist hier, weil du in unsere *Engelbert—Strauss Gruppe* möchtest 👷‍♂️🦺\n\n"
        "Damit wir wissen, wer du bist und dich richtig freischalten können, hilft dir dieser Bot dabei, "
        "einen kurzen Steckbrief auszufüllen 📋\n\n"
        "➡️ Das dauert nur *1–2 Minuten\\!* \n"
        "➡️ Danach bekommst du *automatisch den Einladungslink* zur Gruppe 🔗\n\n"
        "Das hier ist *kein Spam*, sondern eine kleine Sicherheitsabfrage ✅\n\n"
        "👉 *Schreibe jetzt einfach /letsgo, um zu starten\\!*"
    )
    await update.message.reply_text(text, parse_mode="MarkdownV2")


async def start_form(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Wie ist dein Name? Es reicht dein Vorname\\.", parse_mode="MarkdownV2")
    return ASK_NAME

# --- Formular Schritte ---
async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    answer = update.message.text.strip()
    log_user_interaction(user.id, "Name", answer)
    user_data_temp[user.id] = {
        "name": answer,
        "telegram_id": user.id,
        "username": user.username or "",
        "first_name": user.first_name or "",
    }
    await update.message.reply_text("Wie alt bist du? \\(zwischen 10 und 100\\)", parse_mode="MarkdownV2")
    return ASK_AGE

async def get_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user # Added this line
    age_text = update.message.text.strip()
    if not age_text.isdigit() or not 10 <= int(age_text) <= 100:
        await update.message.reply_text("Bitte gib dein Alter als Zahl zwischen 10 und 100 ein\\.", parse_mode="MarkdownV2")
        return ASK_AGE
    log_user_interaction(update.message.from_user.id, "Alter", age_text)
    user_data_temp[update.message.from_user.id]["age"] = age_text
    await update.message.reply_text("Aus welchem Bundesland kommst du? \\(z\\.B\\. NRW, Bayern, Berlin …\\)", parse_mode="MarkdownV2")
    return ASK_STATE

async def get_state(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user # Added this line
    answer = update.message.text.strip()
    log_user_interaction(user.id, "Bundesland", answer)
    user_data_temp[user.id]["state"] = answer
    await update.message.reply_text("Bitte sende ein *normales Foto* von dir \\(kein Dokument\\)\\.", parse_mode="MarkdownV2")
    return ASK_PHOTO

async def get_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not update.message.photo:
        await update.message.reply_text("Bitte sende ein Foto, kein Dokument\\.", parse_mode="MarkdownV2")
        return ASK_PHOTO
    log_user_interaction(user_id, "Foto", "Foto erhalten")
    user_data_temp[user_id]["photo_file_id"] = update.message.photo[-1].file_id
    await update.message.reply_text(f"💥 Was ist dein Kink oder Fetisch?\n\n{FREIWILLIG_HINT}", parse_mode="MarkdownV2")
    return ASK_SECURITY

async def get_security(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    log_user_interaction(update.message.from_user.id, "Kink/Fetisch", text)
    if is_valid(text):
        user_data_temp[update.message.from_user.id]["security"] = text
    await update.message.reply_text(f"🎯 Was sind deine Hobbys oder Interessen?\n\n{FREIWILLIG_HINT}", parse_mode="MarkdownV2")
    return ASK_HOBBIES

async def get_hobbies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    log_user_interaction(update.message.from_user.id, "Hobbys", text)
    if is_valid(text):
        user_data_temp[update.message.from_user.id]["hobbies"] = text
    await update.message.reply_text(f"📱 Trage hier deinen Instagram oder einen anderen Social Media Account ein:\n\n{FREIWILLIG_HINT}", parse_mode="MarkdownV2")
    return ASK_INSTAGRAM

async def get_instagram(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    log_user_interaction(update.message.from_user.id, "Instagram", text)
    if is_valid(text):
        user_data_temp[update.message.from_user.id]["instagram"] = text
    await update.message.reply_text(f"💬 Möchtest du noch etwas über dich sagen?\n\n{FREIWILLIG_HINT}", parse_mode="MarkdownV2")
    return ASK_OTHER

async def get_other(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    log_user_interaction(update.message.from_user.id, "Sonstiges", text)
    if is_valid(text):
        user_data_temp[update.message.from_user.id]["other"] = text
    await update.message.reply_text(f"🏳️‍🌈 Wie ist deine Sexualität?\n\n{FREIWILLIG_HINT}", parse_mode="MarkdownV2")
    return ASK_SEXUALITY

async def get_sexuality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    log_user_interaction(update.message.from_user.id, "Sexualität", text)
    if is_valid(text):
        user_data_temp[update.message.from_user.id]["sexuality"] = text
    regeln = ( "📜 *Bevor du in die Gruppe kommst, lies bitte unsere Regeln:*\n\n" "✅ *DOS:*\n" "• Respektvoller Umgang\n" "• Überwiegend gute Laune 😄\n\n" "❌ *DON'TS:*\n" "✖️ Beleidigungen\n" "✖️ Diskriminierung\n" "✖️ Hardcore\-Inhalte\n" "✖️ Blut oder offene Wunden\n" "✖️ Inhalte mit Kindern\n" "✖️ Inhalte mit Tieren \\(sexuell\\)\\n" "✖️ Inhalte mit Bezug auf Tod\n" "✖️ Exkremente\n\n" "_Verstöße werden durch Admins geprüft und bei Wiederholung erfolgt Ausschluss\\._\n\n" "👉 *Wenn du einverstanden bist, bestätige mit OK\\.*" )
    await update.message.reply_text(regeln, parse_mode="MarkdownV2")
    return ASK_RULES

# --- Willkommensnachricht & Beitritt ---
def format_welcome(profile: dict) -> str:
    # Helper function to escape text for MarkdownV2
    def esc(text):
        return escape_markdown(str(text), version=2)

    username = profile.get('username')
    # Create a user link. The @ is removed as it's not part of the MarkdownV2 link syntax
    # and could cause issues with usernames containing special characters.
    if username:
        user_link = f"[{esc(username)}](tg://user?id={profile.get('telegram_id')})"
    else:
        user_link = esc(profile.get('first_name', 'Unbekannt'))

    join_date_str = datetime.now().strftime('%d\\.%m\\.%Y – %H\\:%M') # Escaping hyphens and colons for MarkdownV2

    lines = [
        f"🎉 *Willkommen in der Gruppe\\!*",
        f"👤 *Name:* {esc(profile.get('name', '-'))}",
        f"🎂 *Alter:* {esc(profile.get('age', '-'))}",
        f"📍 *Bundesland:* {esc(profile.get('state', '-'))}",
        f"🔗 *Telegram:* {user_link}",
    ]
    if is_valid(profile.get("security", "")): lines.append(f"💥 *Kink/Fetisch:* {esc(profile['security'])}")
    if is_valid(profile.get("hobbies", "")): lines.append(f"🎯 *Hobbys:* {esc(profile['hobbies'])}")
    if is_valid(profile.get("instagram", "")): lines.append(f"📱 *Social Media:* {esc(profile['instagram'])}")
    if is_valid(profile.get("other", "")): lines.append(f"💬 *Sonstiges:* {esc(profile['other'])}")
    if is_valid(profile.get("sexuality", "")): lines.append(f"🏳️‍🌈 *Sexualität:* {esc(profile['sexuality'])}")
    lines.append(f"🕐 *Beigetreten am:* {join_date_str}")
    return "\n".join(lines)

async def _send_profile_to_group(user_id: int, profile: dict, chat_id: int, topic_id: int | None, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = format_welcome(profile)
    try:
        if profile.get("photo_file_id"):
            logger.info(f"[send_profile_to_group] Sende Foto mit Profil für User {user_id} an Gruppe {chat_id}, Topic {topic_id}")
            await context.bot.send_photo(chat_id=chat_id, photo=profile["photo_file_id"], caption=welcome_message, parse_mode="MarkdownV2", message_thread_id=topic_id)
        else:
            logger.info(f"[send_profile_to_group] Sende Textprofil für User {user_id} an Gruppe {chat_id}, Topic {topic_id}")
            await context.bot.send_message(chat_id=chat_id, text=welcome_message, parse_mode="MarkdownV2", message_thread_id=topic_id)
        logger.info(f"[send_profile_to_group] Profil erfolgreich in Gruppe gepostet für User {user_id}")
        return True
    except Exception as e:
        logger.error(f"[send_profile_to_group] Fehler bei Begrüßung in Gruppe/Topic für User {user_id}: {e}", exc_info=True)
        return False

async def get_rules_ok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if update.message.text.strip().lower() != "ok":
        await update.message.reply_text("Bitte antworte mit *OK*, um den Regeln zuzustimmen\\.", parse_mode="MarkdownV2")
        return ASK_RULES
    
    # Save profile data
    user_data_temp[user_id]["created_at"] = datetime.utcnow().isoformat()
    save_profile(user_id, user_data_temp[user_id])

    config = load_bot_settings_config()
    GROUP_ID = int(config.get("main_chat_id", 0)) if config.get("main_chat_id") else 0
    TOPIC_ID_STR = config.get("topic_id")
    TOPIC_ID = int(TOPIC_ID_STR) if TOPIC_ID_STR and TOPIC_ID_STR.isdigit() else None
    LINK_TTL_MINUTES = config.get("link_ttl_minutes", 15)
    repost_setting = config.get("repost_profile_for_existing_members", True)

    logger.debug(f"[get_rules_ok] User: {user_id}, GROUP_ID: {GROUP_ID}, TOPIC_ID: {TOPIC_ID}, Repost Setting: {repost_setting}")

    if not GROUP_ID:
        logger.error("GROUP_ID ist nicht konfiguriert oder ungültig.")
        await update.message.reply_text("⚠️ Fehler: Die Gruppen-ID ist nicht konfiguriert\\.", parse_mode="MarkdownV2")
        user_data_temp.pop(user_id, None)
        return ConversationHandler.END
    
    is_already_member = False
    try:
        member = await context.bot.get_chat_member(chat_id=GROUP_ID, user_id=user_id)
        is_already_member = member.status in ['member', 'administrator', 'creator']
        logger.debug(f"[get_rules_ok] User {user_id} member status: {member.status}, is_already_member: {is_already_member}")
    except TelegramError as e:
        # User is not a member, get_chat_member will raise an error (e.g., ChatMemberNotFound)
        logger.debug(f"[get_rules_ok] User {user_id} ist kein aktuelles Mitglied der Gruppe (Fehler: {e}).")
        is_already_member = False
    except Exception as e:
        logger.error(f"[get_rules_ok] Fehler beim Abrufen des Chat-Mitgliedsstatus für User {user_id}: {e}", exc_info=True)
        await update.message.reply_text(f"⚠️ Fehler beim Überprüfen des Mitgliederstatus\\: {escape_markdown(str(e), version=2)}", parse_mode="MarkdownV2")
        user_data_temp.pop(user_id, None)
        return ConversationHandler.END

    if is_already_member and repost_setting:
        logger.info(f"[get_rules_ok] User {user_id} ist bereits Mitglied und Reposting ist aktiviert. Sende Profil.")
        profile = load_profile(user_id)
        if profile:
            success = await _send_profile_to_group(user_id, profile, GROUP_ID, TOPIC_ID, context)
            if success:
                await update.message.reply_text("✅ Dein Steckbrief wurde erfolgreich in der Gruppe gepostet\\.", parse_mode="MarkdownV2")
            else:
                await update.message.reply_text("⚠️ Fehler beim Posten des Steckbriefs in der Gruppe\\.", parse_mode="MarkdownV2")
        else:
            logger.error(f"[get_rules_ok] Profil für User {user_id} konnte nicht geladen werden, obwohl es gespeichert sein sollte.")
            await update.message.reply_text("⚠️ Ein interner Fehler ist aufgetreten\\. Dein Steckbrief konnte nicht gefunden werden\\.", parse_mode="MarkdownV2")
    else:
        logger.info(f"[get_rules_ok] User {user_id} ist kein Mitglied ODER Reposting ist deaktiviert. Sende Einladungslink.")
        try:
            link: ChatInviteLink = await context.bot.create_chat_invite_link(chat_id=GROUP_ID, expire_date=datetime.utcnow() + timedelta(minutes=LINK_TTL_MINUTES), creates_join_request=True)
            await update.message.reply_text(f"✅ Super\\! Hier ist dein Einladungslink \\(gültig für {LINK_TTL_MINUTES} Minuten\\):\n{escape_markdown(link.invite_link, version=2)}", parse_mode='MarkdownV2')
        except Exception as e:
            logger.error(f"[get_rules_ok] Fehler beim Link-Erstellen für User {user_id}: {e}")
            await update.message.reply_text(f"⚠️ Fehler beim Erstellen des Links\\: {escape_markdown(str(e), version=2)}", parse_mode="MarkdownV2")
    
    user_data_temp.pop(user_id, None)
    remove_profile(user_id) # Remove profile regardless of whether it was posted or not
    return ConversationHandler.END

async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.chat_join_request.from_user
    config = load_bot_settings_config()
    GROUP_ID = int(config.get("main_chat_id", 0)) if config.get("main_chat_id") else 0
    TOPIC_ID_STR = config.get("topic_id")
    TOPIC_ID = int(TOPIC_ID_STR) if TOPIC_ID_STR and TOPIC_ID_STR.isdigit() else None
    repost_setting = config.get("repost_profile_for_existing_members", True)

    logger.debug(f"[handle_join_request] User: {user.id}, GROUP_ID: {GROUP_ID}, TOPIC_ID: {TOPIC_ID}, Repost Setting: {repost_setting}")

    if not GROUP_ID:
        logger.error("GROUP_ID ist nicht konfiguriert oder ungültig.")
        return

    is_already_member = False
    try:
        member = await context.bot.get_chat_member(chat_id=GROUP_ID, user_id=user.id)
        is_already_member = member.status in ['member', 'administrator', 'creator']
        logger.debug(f"[handle_join_request] User {user.id} member status: {member.status}, is_already_member: {is_already_member}")
    except TelegramError as e:
        logger.debug(f"[handle_join_request] User {user.id} ist kein aktuelles Mitglied der Gruppe (Fehler: {e}).")
        is_already_member = False
    except Exception as e:
        logger.error(f"[handle_join_request] Fehler beim Abrufen des Chat-Mitgliedsstatus für User {user.id}: {e}", exc_info=True)

    try:
        await context.bot.approve_chat_join_request(chat_id=GROUP_ID, user_id=user.id)
        logger.info(f"[handle_join_request] Join request approved for user {user.id}")
    except Exception as e:
        logger.error(f"[handle_join_request] Genehmigung fehlgeschlagen für User {user.id}: {e}")
        return

    profile = load_profile(user.id)
    if not profile:
        logger.warning(f"[handle_join_request] Kein Profil für User {user.id} gefunden nach Genehmigung.")
        return
    logger.debug(f"[handle_join_request] Profil für User {user.id} geladen: {profile}")

    should_post_profile = (not is_already_member) or (is_already_member and repost_setting)
    logger.debug(f"[handle_join_request] should_post_profile for User {user.id}: {should_post_profile}")

    if should_post_profile:
        success = await _send_profile_to_group(user.id, profile, GROUP_ID, TOPIC_ID, context)
        if not success:
            logger.error(f"[handle_join_request] Profil konnte nicht in Gruppe gepostet werden für User {user.id}")
    else:
        logger.info(f"[handle_join_request] Profil für User {user.id} nicht gepostet (should_post_profile ist False).")
    
    remove_profile(user.id)


async def handle_member_left(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.left_chat_member: return
    user = update.message.left_chat_member
    if user: remove_profile(user.id); logger.info(f"Benutzer {user.full_name} hat die Gruppe verlassen.")

# --- Bot Start --------------------------------------------------
if __name__ == "__main__":
    config = load_bot_settings_config()
    BOT_TOKEN = config.get("bot_token")
    is_enabled = config.get("is_enabled", False)

    if not BOT_TOKEN or not is_enabled:
        logger.info("Invite-Bot ist nicht aktiviert oder BOT_TOKEN fehlt.")
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

        developer_filter = filters.Regex(re.compile(r'^wer ist dein entwickler\??$', re.IGNORECASE))
        app.add_handler(MessageHandler(developer_filter & filters.TEXT & ~filters.COMMAND, reply_with_developer_info))

        praise_filter = filters.Regex(re.compile(r'^cooler bot!?$', re.IGNORECASE))
        app.add_handler(MessageHandler(praise_filter & filters.TEXT & ~filters.COMMAND, reply_with_developer_info))

        logger.info("🤖 Invite-Bot läuft …")
        app.run_polling()
