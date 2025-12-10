import logging
import os
import json
import re
from datetime import datetime, timedelta
from collections import defaultdict, deque

from telegram import Update, ChatPermissions
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from telegram.error import TelegramError

# --- Logging Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Konfiguration & Pfade ---
CONFIG_FILE = 'id_finder_config.json'
COMMAND_LOG_FILE = 'id_finder_command.log'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

MODERATION_DATA_FILE = os.path.join(DATA_DIR, "moderation_data.json")
ADMINS_FILE = os.path.join(os.path.dirname(BASE_DIR), 'dashboard', 'admins.json')


# ---------------------------
# Load/Save Helpers
# ---------------------------

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Fehler beim Laden der Konfiguration: {e}")
        return {}

def save_config(config: dict):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Fehler beim Speichern der Konfiguration: {e}")

def load_moderation_data():
    if not os.path.exists(MODERATION_DATA_FILE):
        return {}
    try:
        with open(MODERATION_DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Fehler beim Laden der Moderationsdaten: {e}")
        return {}

def save_moderation_data(data):
    try:
        with open(MODERATION_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Fehler beim Speichern der Moderationsdaten: {e}")

def load_admins():
    if not os.path.exists(ADMINS_FILE):
        return {}
    try:
        with open(ADMINS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Fehler beim Laden der Admin-Daten: {e}")
        return {}

def log_command(user_id, user_name, command, target_id=None, details=None):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] User: {user_name} ({user_id}) | Cmd: {command} | Target: {target_id} | Details: {details}\n"
    try:
        with open(COMMAND_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_entry)
    except Exception as e:
        logger.error(f"Fehler beim Schreiben des Command-Logs: {e}")


# ---------------------------
# Utility
# ---------------------------

def get_reply_parameters(config, update: Update):
    log_topic_id = config.get('log_topic_id')
    main_group_id = config.get('main_group_id')

    if log_topic_id:
        try:
            log_topic_id = int(log_topic_id)
        except:
            log_topic_id = None
    if main_group_id:
        try:
            main_group_id = int(main_group_id)
        except:
            main_group_id = None

    if log_topic_id and main_group_id:
        return {"chat_id": main_group_id, "message_thread_id": log_topic_id}
    else:
        return {
            "chat_id": update.effective_chat.id,
            "message_thread_id": update.effective_message.message_thread_id if update.effective_message else None
        }

async def get_target_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user = None
    args = list(context.args)

    if update.message and update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
    elif args:
        # Erstes Argument kann eine User-ID sein
        try:
            user_id = int(args[0])
            try:
                chat_id = update.effective_chat.id
                member = await context.bot.get_chat_member(chat_id, user_id)
                target_user = member.user
                args = args[1:]
            except Exception:
                # User evtl. nicht im Chat – wir lassen target_user None
                pass
        except ValueError:
            pass

    return target_user, args

def parse_duration(token: str) -> timedelta | None:
    """
    Unterstützt: 10m, 2h, 1d
    """
    if not token:
        return None
    m = re.match(r'^(\d+)([mhd])$', token.strip().lower())
    if not m:
        return None
    amount = int(m.group(1))
    unit = m.group(2)
    if unit == 'm':
        return timedelta(minutes=amount)
    if unit == 'h':
        return timedelta(hours=amount)
    if unit == 'd':
        return timedelta(days=amount)
    return None

def ensure_user_block(data: dict, user_id: int):
    uid = str(user_id)
    if uid not in data:
        data[uid] = {"warns": 0, "history": []}
    if "warns" not in data[uid]:
        data[uid]["warns"] = 0
    if "history" not in data[uid]:
        data[uid]["history"] = []
    return data[uid]

def get_roles_block(data: dict):
    if "roles" not in data:
        data["roles"] = {}
    if "mods" not in data:
        data["mods"] = []
    return data

def get_blacklist_block(data: dict):
    if "blacklist" not in data:
        data["blacklist"] = []
    return data

def user_has_role(data: dict, user_id: int, role: str) -> bool:
    roles = data.get("roles", {})
    return roles.get(str(user_id)) == role

def get_user_role(data: dict, user_id: int) -> str:
    roles = data.get("roles", {})
    return roles.get(str(user_id), "user")


# ---------------------------
# Permission Decorator
# ---------------------------

def check_permission(permission_key: str):
    def decorator(func):
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            if not update.effective_user or not update.message:
                return
            user_id = str(update.effective_user.id)
            admins = load_admins()

            if user_id not in admins:
                await update.message.reply_text("Du hast keine Berechtigung für diesen Befehl.")
                log_command(user_id, update.effective_user.full_name, f"PERMISSION_DENIED: {func.__name__}")
                return

            perms = admins[user_id].get("permissions", {})
            if not perms.get(permission_key, False):
                await update.message.reply_text("Du hast keine Berechtigung für diesen Befehl.")
                log_command(user_id, update.effective_user.full_name, f"PERMISSION_DENIED: {func.__name__}")
                return

            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator


# ---------------------------
# In-Memory Flood Tracking
# ---------------------------

# pro chat_id -> pro user_id -> deque[timestamps]
FLOOD_TRACKER = defaultdict(lambda: defaultdict(deque))


# ---------------------------
# Commands: ID Tools
# ---------------------------

@check_permission("can_see_ids")
async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    chat = update.effective_chat
    topic_id = update.message.message_thread_id

    response = f"👤 Deine ID: `{user.id}`\n"
    response += f"💬 Chat ID: `{chat.id}`\n"
    if topic_id:
        response += f"🧵 Topic ID: `{topic_id}`"

    if update.message.reply_to_message:
        original_msg = update.message.reply_to_message
        original_user = original_msg.from_user
        response += f"\n\n👇 **Ziel-Nachricht** 👇\n"
        response += f"👤 User ID: `{original_user.id}`\n"
        response += f"📄 Message ID: `{original_msg.message_id}`"

    await update.message.reply_text(response, parse_mode='Markdown')
    log_command(user.id, user.full_name, "/id")

@check_permission("can_see_ids")
async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    response = f"💬 Die ID dieses Chats ist: `{chat.id}`"
    if update.effective_message.message_thread_id:
        response += f"\n🧵 Topic ID: `{update.effective_message.message_thread_id}`"
    await update.message.reply_text(response, parse_mode='Markdown')
    log_command(update.effective_user.id, update.effective_user.full_name, "/chatid")

@check_permission("can_see_ids")
async def get_topic_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_message.message_thread_id:
        response = f"🧵 Topic ID: `{update.effective_message.message_thread_id}`"
    else:
        response = "Diese Nachricht befindet sich in keinem spezifischen Topic oder das Forum-Feature ist nicht aktiv."
    await update.message.reply_text(response, parse_mode='Markdown')
    log_command(update.effective_user.id, update.effective_user.full_name, "/topicid")

@check_permission("can_see_ids")
async def get_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    response = f"👤 Deine User ID ist: `{user.id}`"
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        response += f"\n\n👇 **Ziel-Nachricht User ID** 👇\n👤 User ID: `{target_user.id}`"
    await update.message.reply_text(response, parse_mode='Markdown')
    log_command(user.id, user.full_name, "/userid")


# ---------------------------
# Commands: Warn System
# ---------------------------

@check_permission("can_warn")
async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user, args = await get_target_user(update, context)
    if not target_user:
        await update.message.reply_text("Bitte antworte auf eine Nachricht oder gib eine User-ID an, um jemanden zu verwarnen.")
        return

    reason = " ".join(args) if args else "Kein Grund angegeben"

    data = load_moderation_data()
    block = ensure_user_block(data, target_user.id)

    block["warns"] += 1
    block["history"].append({
        "type": "warn",
        "reason": reason,
        "date": datetime.now().isoformat(),
        "by": update.effective_user.id
    })

    save_moderation_data(data)

    log_command(update.effective_user.id, update.effective_user.full_name, "/warn", target_user.id, reason)

    config = load_config()
    reply_params = get_reply_parameters(config, update)

    msg_text = (
        f"⚠️ Benutzer {target_user.full_name} (`{target_user.id}`) wurde verwarnt.\n"
        f"Grund: {reason}\n"
        f"Anzahl Verwarnungen: {block['warns']}"
    )

    try:
        await context.bot.send_message(text=msg_text, parse_mode='Markdown', **reply_params)
    except Exception as e:
        logger.error(f"Konnte Verwarnung nicht senden: {e}")
        await update.message.reply_text(msg_text, parse_mode='Markdown')

@check_permission("can_warn")
async def get_warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user, _args = await get_target_user(update, context)
    if not target_user:
        await update.message.reply_text("Bitte antworte auf eine Nachricht oder gib eine User-ID an.")
        return

    data = load_moderation_data()
    uid = str(target_user.id)

    if uid in data and data[uid].get("warns", 0) > 0:
        history = data[uid].get("history", [])
        msg_text = f"⚠️ Verwarnungen für {target_user.full_name}:\nAnzahl: {data[uid]['warns']}\n\nHistorie (letzte 5):\n"
        for entry in history[-5:]:
            date_short = entry.get("date", "")[:10]
            reason = entry.get("reason", "—")
            by = entry.get("by", "—")
            msg_text += f"- {date_short}: {reason} (von {by})\n"
    else:
        msg_text = f"✅ Keine Verwarnungen für {target_user.full_name} gefunden."

    await update.message.reply_text(msg_text, parse_mode='Markdown')

@check_permission("can_warn")
async def unwarn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user, _args = await get_target_user(update, context)
    if not target_user:
        await update.message.reply_text("Bitte antworte auf eine Nachricht oder gib eine User-ID an.")
        return

    data = load_moderation_data()
    uid = str(target_user.id)

    if uid in data and data[uid].get("warns", 0) > 0:
        data[uid]["warns"] -= 1
        data[uid]["history"].append({
            "type": "unwarn",
            "reason": "Manuell entfernt",
            "date": datetime.now().isoformat(),
            "by": update.effective_user.id
        })
        save_moderation_data(data)
        msg_text = f"✅ Eine Verwarnung für {target_user.full_name} wurde entfernt. Aktuell: {data[uid]['warns']}"
    else:
        msg_text = f"ℹ️ {target_user.full_name} hat keine Verwarnungen."

    await update.message.reply_text(msg_text, parse_mode='Markdown')

@check_permission("can_warn")
async def clear_warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user, _args = await get_target_user(update, context)
    if not target_user:
        await update.message.reply_text("Bitte antworte auf eine Nachricht oder gib eine User-ID an.")
        return

    data = load_moderation_data()
    uid = str(target_user.id)

    if uid in data:
        data[uid]["warns"] = 0
        data[uid]["history"] = []
        save_moderation_data(data)
        msg_text = f"✅ Alle Verwarnungen für {target_user.full_name} wurden zurückgesetzt."
    else:
        msg_text = f"ℹ️ {target_user.full_name} hat keine Verwarnungen."

    await update.message.reply_text(msg_text, parse_mode='Markdown')


# ---------------------------
# Commands: Kick/Ban/Mute
# ---------------------------

@check_permission("can_kick")
async def kick_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user, args = await get_target_user(update, context)
    if not target_user:
        await update.message.reply_text("Zielnutzer nicht gefunden.")
        return

    reason = " ".join(args) if args else "Kein Grund angegeben"

    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target_user.id)
        await context.bot.unban_chat_member(update.effective_chat.id, target_user.id)

        log_command(update.effective_user.id, update.effective_user.full_name, "/kick", target_user.id, reason)

        config = load_config()
        reply_params = get_reply_parameters(config, update)
        msg_text = f"👢 Benutzer {target_user.full_name} (`{target_user.id}`) wurde gekickt.\nGrund: {reason}"

        try:
            await context.bot.send_message(text=msg_text, parse_mode='Markdown', **reply_params)
        except:
            await update.message.reply_text(msg_text, parse_mode='Markdown')

    except TelegramError as e:
        await update.message.reply_text(f"Fehler beim Kicken: {e}")

@check_permission("can_ban")
async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user, args = await get_target_user(update, context)
    if not target_user:
        await update.message.reply_text("Zielnutzer nicht gefunden.")
        return

    reason = " ".join(args) if args else "Kein Grund angegeben"

    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target_user.id)

        log_command(update.effective_user.id, update.effective_user.full_name, "/ban", target_user.id, reason)

        config = load_config()
        reply_params = get_reply_parameters(config, update)
        msg_text = f"🔨 Benutzer {target_user.full_name} (`{target_user.id}`) wurde gebannt.\nGrund: {reason}"

        try:
            await context.bot.send_message(text=msg_text, parse_mode='Markdown', **reply_params)
        except:
            await update.message.reply_text(msg_text, parse_mode='Markdown')

    except TelegramError as e:
        await update.message.reply_text(f"Fehler beim Bannen: {e}")

@check_permission("can_ban")
async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user, args = await get_target_user(update, context)

    if not target_user and args:
        try:
            user_id = int(args[0])
        except ValueError:
            await update.message.reply_text("Bitte gib eine gültige User-ID an.")
            return
    elif target_user:
        user_id = target_user.id
    else:
        await update.message.reply_text("Bitte gib eine User-ID an.")
        return

    try:
        await context.bot.unban_chat_member(update.effective_chat.id, user_id)
        await update.message.reply_text(f"✅ Benutzer mit ID `{user_id}` wurde entbannt.", parse_mode='Markdown')
        log_command(update.effective_user.id, update.effective_user.full_name, "/unban", user_id)

    except TelegramError as e:
        await update.message.reply_text(f"Fehler beim Entbannen: {e}")

@check_permission("can_mute")
async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user, args = await get_target_user(update, context)
    if not target_user:
        await update.message.reply_text("Bitte antworte auf eine Nachricht oder gib eine User-ID an, um jemanden stummzuschalten.")
        return

    duration = None
    reason = "Kein Grund angegeben"

    if args:
        maybe_duration = parse_duration(args[0])
        if maybe_duration:
            duration = maybe_duration
            args = args[1:]
            reason = " ".join(args) if args else "Kein Grund angegeben"
        else:
            reason = " ".join(args)

    if not duration:
        duration = timedelta(hours=1)
        duration_str = "1h"
    else:
        duration_str = context.args[0]

    until_date = datetime.now() + duration

    try:
        await context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=target_user.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date
        )

        log_command(update.effective_user.id, update.effective_user.full_name, "/mute", target_user.id, f"{duration_str} {reason}")

        config = load_config()
        reply_params = get_reply_parameters(config, update)
        msg_text = (
            f"🤐 Benutzer {target_user.full_name} (`{target_user.id}`) wurde für {duration_str} stummgeschaltet."
            f"\nGrund: {reason}\nAufhebung am: {until_date.strftime('%Y-%m-%d %H:%M:%S')}"
        )

        try:
            await context.bot.send_message(text=msg_text, parse_mode='Markdown', **reply_params)
        except:
            await update.message.reply_text(msg_text, parse_mode='Markdown')

    except TelegramError as e:
        await update.message.reply_text(f"Fehler beim Muten: {e}")

@check_permission("can_mute")
async def unmute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user, _args = await get_target_user(update, context)
    if not target_user:
        await update.message.reply_text("Bitte antworte auf eine Nachricht oder gib eine User-ID an.")
        return

    try:
        await context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=target_user.id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        )
        await update.message.reply_text(f"🔊 {target_user.full_name} wurde entstummt.")
        log_command(update.effective_user.id, update.effective_user.full_name, "/unmute", target_user.id)
    except TelegramError as e:
        await update.message.reply_text(f"Fehler beim Aufheben der Stummschaltung: {e}")


# ---------------------------
# Commands: Message Management
# ---------------------------

@check_permission("can_manage_messages")
async def delete_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Bitte antworte auf die Nachricht, die gelöscht werden soll.")
        return

    try:
        await update.message.reply_to_message.delete()
        await update.message.delete()
    except TelegramError as e:
        await update.message.reply_text(f"Fehler beim Löschen: {e}")

@check_permission("can_manage_messages")
async def purge_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Bitte antworte auf die erste Nachricht, ab der gelöscht werden soll.")
        return

    message_id = update.message.reply_to_message.message_id
    current_id = update.message.message_id
    chat_id = update.effective_chat.id

    deleted_count = 0
    ids_to_delete = list(range(message_id, current_id + 1))

    for mid in ids_to_delete:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=mid)
            deleted_count += 1
        except Exception:
            pass

    await update.message.reply_text(f"🗑️ {deleted_count} Nachrichten gelöscht.")

@check_permission("can_manage_messages")
async def pin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Bitte antworte auf die Nachricht, die angepinnt werden soll.")
        return
    try:
        await update.message.reply_to_message.pin()
        await update.message.reply_text("📌 Nachricht angepinnt.")
    except TelegramError as e:
        await update.message.reply_text(f"Fehler beim Anpinnen: {e}")

@check_permission("can_manage_messages")
async def unpin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message.reply_to_message:
            await update.message.reply_to_message.unpin()
        else:
            await context.bot.unpin_chat_message(chat_id=update.effective_chat.id)
        await update.message.reply_text("📌 Pin entfernt.")
    except TelegramError as e:
        await update.message.reply_text(f"Fehler beim Entfernen des Pins: {e}")

@check_permission("can_manage_messages")
async def lock_feature(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Bitte gib an, was gesperrt werden soll: links, media, stickers.")
        return

    feature = context.args[0].lower()
    if feature not in ("links", "media", "stickers"):
        await update.message.reply_text("Unbekanntes Feature. Nutze: links | media | stickers")
        return

    config = load_config()
    locks = config.get("locks", {})
    locks[feature] = True
    config["locks"] = locks
    save_config(config)

    await update.message.reply_text(f"🔒 {feature} wurde gesperrt.")
    log_command(update.effective_user.id, update.effective_user.full_name, "/lock", details=feature)

@check_permission("can_manage_messages")
async def unlock_feature(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Bitte gib an, was entsperrt werden soll: links, media, stickers.")
        return

    feature = context.args[0].lower()
    if feature not in ("links", "media", "stickers"):
        await update.message.reply_text("Unbekanntes Feature. Nutze: links | media | stickers")
        return

    config = load_config()
    locks = config.get("locks", {})
    locks[feature] = False
    config["locks"] = locks
    save_config(config)

    await update.message.reply_text(f"🔓 {feature} wurde entsperrt.")
    log_command(update.effective_user.id, update.effective_user.full_name, "/unlock", details=feature)


# ---------------------------
# Commands: Anti-Spam / Link Mode / Blacklist
# ---------------------------

@check_permission("can_antispam")
async def antispam_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Nutzung: /antispam on|off")
        return

    mode = context.args[0].lower()
    if mode not in ("on", "off"):
        await update.message.reply_text("Nutzung: /antispam on|off")
        return

    config = load_config()
    config["antispam_enabled"] = (mode == "on")
    save_config(config)

    await update.message.reply_text(f"🛡️ Anti-Spam ist jetzt **{mode.upper()}**.", parse_mode="Markdown")
    log_command(update.effective_user.id, update.effective_user.full_name, "/antispam", details=mode)

@check_permission("can_setflood")
async def setflood_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Nutzung: /setflood <zahl>")
        return

    try:
        limit = int(context.args[0])
        if limit < 1 or limit > 50:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Bitte gib eine sinnvolle Zahl an (1-50).")
        return

    config = load_config()
    config["flood_limit"] = limit
    # Optional: Default-Window
    if "flood_window_seconds" not in config:
        config["flood_window_seconds"] = 10
    save_config(config)

    await update.message.reply_text(f"🌊 Flood-Limit gesetzt auf **{limit}** Nachrichten pro Fenster.", parse_mode="Markdown")
    log_command(update.effective_user.id, update.effective_user.full_name, "/setflood", details=str(limit))

@check_permission("can_setlinkmode")
async def setlinkmode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Nutzung: /setlinkmode allow|warn|mute|ban")
        return

    mode = context.args[0].lower()
    if mode not in ("allow", "warn", "mute", "ban"):
        await update.message.reply_text("Nutzung: /setlinkmode allow|warn|mute|ban")
        return

    config = load_config()
    config["link_mode"] = mode
    save_config(config)

    await update.message.reply_text(f"🔗 Link-Mode ist jetzt **{mode.upper()}**.", parse_mode="Markdown")
    log_command(update.effective_user.id, update.effective_user.full_name, "/setlinkmode", details=mode)

@check_permission("can_blacklist")
async def blacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Nutzung: /blacklist add|remove|list [wort]")
        return

    action = context.args[0].lower()
    data = load_moderation_data()
    data = get_blacklist_block(data)
    bl = data["blacklist"]

    if action == "list":
        if not bl:
            await update.message.reply_text("📄 Blacklist ist leer.")
        else:
            text = "🚫 **Blacklist:**\n" + "\n".join([f"- `{w}`" for w in bl])
            await update.message.reply_text(text, parse_mode="Markdown")
        return

    if action in ("add", "remove"):
        if len(context.args) < 2:
            await update.message.reply_text("Bitte gib ein Wort/Pattern mit an.")
            return

        word = " ".join(context.args[1:]).strip()
        if not word:
            await update.message.reply_text("Bitte gib ein gültiges Wort/Pattern an.")
            return

        if action == "add":
            if word not in bl:
                bl.append(word)
                save_moderation_data(data)
            await update.message.reply_text(f"✅ `{word}` zur Blacklist hinzugefügt.", parse_mode="Markdown")
            log_command(update.effective_user.id, update.effective_user.full_name, "/blacklist add", details=word)
            return

        if action == "remove":
            if word in bl:
                bl.remove(word)
                save_moderation_data(data)
            await update.message.reply_text(f"✅ `{word}` von der Blacklist entfernt.", parse_mode="Markdown")
            log_command(update.effective_user.id, update.effective_user.full_name, "/blacklist remove", details=word)
            return

    await update.message.reply_text("Nutzung: /blacklist add|remove|list [wort]")


# ---------------------------
# Commands: Roles & Permissions
# ---------------------------

@check_permission("can_see_logs")
async def get_admin_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admins = load_admins()
    if not admins:
        await update.message.reply_text("Keine Admins konfiguriert.")
        return

    response = "**Aktuelle Admins:**\n"
    for admin_id, admin_data in admins.items():
        perms_list = [p for p, granted in admin_data.get('permissions', {}).items() if granted]
        perms_str = ', '.join(perms_list) if perms_list else "Keine Rechte"
        response += f"- {admin_data.get('name', 'Unbekannt')} (`{admin_id}`): {perms_str}\n"

    await update.message.reply_text(response, parse_mode='Markdown')
    log_command(update.effective_user.id, update.effective_user.full_name, "/adminlist")

@check_permission("can_roles")
async def mod_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Nutzung: /mod add|remove @user|id")
        return

    action = context.args[0].lower()
    target_user, args = await get_target_user(update, context)

    # Falls nicht per Reply/ID gefunden, aber @name gegeben – lassen wir es simpel:
    if not target_user:
        await update.message.reply_text("Bitte antworte auf eine Nachricht oder gib eine User-ID an.")
        return

    data = load_moderation_data()
    data = get_roles_block(data)
    mods = data["mods"]

    uid_str = str(target_user.id)

    if action == "add":
        if uid_str not in mods:
            mods.append(uid_str)
            save_moderation_data(data)
        await update.message.reply_text(f"✅ {target_user.full_name} ist jetzt Bot-Moderator.")
        log_command(update.effective_user.id, update.effective_user.full_name, "/mod add", target_user.id)
        return

    if action == "remove":
        if uid_str in mods:
            mods.remove(uid_str)
            save_moderation_data(data)
        await update.message.reply_text(f"✅ {target_user.full_name} ist kein Bot-Moderator mehr.")
        log_command(update.effective_user.id, update.effective_user.full_name, "/mod remove", target_user.id)
        return

    await update.message.reply_text("Nutzung: /mod add|remove @user|id")

@check_permission("can_roles")
async def setrole_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Nutzung: /setrole @user|id admin|mod|trusted|user")
        return

    target_user, args = await get_target_user(update, context)
    if not target_user:
        await update.message.reply_text("Bitte antworte auf eine Nachricht oder gib eine User-ID an.")
        return

    role = args[0].lower() if args else context.args[-1].lower()
    if role not in ("admin", "mod", "trusted", "user"):
        await update.message.reply_text("Rolle muss sein: admin|mod|trusted|user")
        return

    data = load_moderation_data()
    data = get_roles_block(data)
    data["roles"][str(target_user.id)] = role
    save_moderation_data(data)

    await update.message.reply_text(f"✅ Rolle von {target_user.full_name} gesetzt auf **{role.upper()}**.", parse_mode="Markdown")
    log_command(update.effective_user.id, update.effective_user.full_name, "/setrole", target_user.id, role)

@check_permission("can_roles")
async def permissions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admins = load_admins()
    uid = str(update.effective_user.id)
    perms = admins.get(uid, {}).get("permissions", {})

    config = load_config()
    antispam = config.get("antispam_enabled", False)
    flood_limit = config.get("flood_limit", 5)
    flood_window = config.get("flood_window_seconds", 10)
    link_mode = config.get("link_mode", "allow")
    locks = config.get("locks", {})

    text = "🧩 **Bot-Rechte & Module**\n\n"
    text += "**Deine Permissions:**\n"
    if perms:
        for k, v in perms.items():
            text += f"- `{k}`: {'✅' if v else '❌'}\n"
    else:
        text += "- Keine gefunden.\n"

    text += "\n**Aktive Module (Config):**\n"
    text += f"- Anti-Spam: {'✅' if antispam else '❌'}\n"
    text += f"- Flood-Limit: `{flood_limit}` / Fenster `{flood_window}s`\n"
    text += f"- Link-Mode: `{link_mode}`\n"
    if locks:
        text += "- Locks:\n"
        for lk, lv in locks.items():
            text += f"  - `{lk}`: {'🔒' if lv else '🔓'}\n"

    await update.message.reply_text(text, parse_mode="Markdown")
    log_command(update.effective_user.id, update.effective_user.full_name, "/permissions")


# ---------------------------
# Commands: Welcome / Rules / Verify (lightweight)
# ---------------------------

@check_permission("can_config")
async def welcome_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Nutzung: /welcome on|off")
        return

    mode = context.args[0].lower()
    if mode not in ("on", "off"):
        await update.message.reply_text("Nutzung: /welcome on|off")
        return

    config = load_config()
    config["welcome_enabled"] = (mode == "on")
    if "welcome_text" not in config:
        config["welcome_text"] = "Willkommen {user} in {group}! 👋"
    save_config(config)

    await update.message.reply_text(f"👋 Welcome ist jetzt **{mode.upper()}**.", parse_mode="Markdown")
    log_command(update.effective_user.id, update.effective_user.full_name, "/welcome", details=mode)

@check_permission("can_config")
async def setwelcome_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text("Nutzung: /setwelcome <Text>")
        return

    config = load_config()
    config["welcome_text"] = text
    save_config(config)

    await update.message.reply_text("✅ Welcome-Text gespeichert.")
    log_command(update.effective_user.id, update.effective_user.full_name, "/setwelcome", details=text)

async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config = load_config()
    rules = config.get("rules_text", "Es wurden noch keine Regeln gesetzt.")
    await update.message.reply_text(f"📜 **Regeln:**\n{rules}", parse_mode="Markdown")
    log_command(update.effective_user.id, update.effective_user.full_name, "/rules")

@check_permission("can_config")
async def setrules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text("Nutzung: /setrules <Text>")
        return

    config = load_config()
    config["rules_text"] = text
    save_config(config)

    await update.message.reply_text("✅ Regeln gespeichert.")
    log_command(update.effective_user.id, update.effective_user.full_name, "/setrules", details=text)

@check_permission("can_config")
async def verify_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Nutzung: /verify on|off")
        return

    mode = context.args[0].lower()
    if mode not in ("on", "off"):
        await update.message.reply_text("Nutzung: /verify on|off")
        return

    config = load_config()
    config["verify_enabled"] = (mode == "on")
    save_config(config)

    await update.message.reply_text(f"✅ Verify ist jetzt **{mode.upper()}**.", parse_mode="Markdown")
    log_command(update.effective_user.id, update.effective_user.full_name, "/verify", details=mode)


# ---------------------------
# Commands: System / Status
# ---------------------------

@check_permission("can_config")
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config = load_config()
    text = "⚙️ **Einstellungen (kurz):**\n"
    text += f"- Anti-Spam: `{config.get('antispam_enabled', False)}`\n"
    text += f"- Flood-Limit: `{config.get('flood_limit', 5)}`\n"
    text += f"- Flood-Fenster: `{config.get('flood_window_seconds', 10)}s`\n"
    text += f"- Link-Mode: `{config.get('link_mode', 'allow')}`\n"
    text += f"- Welcome: `{config.get('welcome_enabled', False)}`\n"
    text += f"- Verify: `{config.get('verify_enabled', False)}`\n"
    await update.message.reply_text(text, parse_mode="Markdown")
    log_command(update.effective_user.id, update.effective_user.full_name, "/settings")

@check_permission("can_config")
async def config_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config = load_config()
    dumped = json.dumps(config, indent=2, ensure_ascii=False)
    await update.message.reply_text(f"🧾 **Config:**\n```json\n{dumped}\n```", parse_mode="Markdown")
    log_command(update.effective_user.id, update.effective_user.full_name, "/config")

@check_permission("can_config")
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config = load_config()
    locks = config.get("locks", {})
    text = "📡 **NexusMod Bot Status**\n\n"
    text += f"- Anti-Spam: {'✅' if config.get('antispam_enabled', False) else '❌'}\n"
    text += f"- Link-Mode: `{config.get('link_mode', 'allow')}`\n"
    text += f"- Flood: `{config.get('flood_limit', 5)}` / `{config.get('flood_window_seconds', 10)}s`\n"
    text += f"- Welcome: {'✅' if config.get('welcome_enabled', False) else '❌'}\n"
    text += f"- Verify: {'✅' if config.get('verify_enabled', False) else '❌'}\n"
    if locks:
        text += "- Locks:\n"
        for k, v in locks.items():
            text += f"  - `{k}`: {'🔒' if v else '🔓'}\n"

    await update.message.reply_text(text, parse_mode="Markdown")
    log_command(update.effective_user.id, update.effective_user.full_name, "/status")

@check_permission("can_config")
async def reload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Da wir aus Datei lesen, reicht eine Bestätigung.
    load_config()
    await update.message.reply_text("🔄 Config neu geladen.")
    log_command(update.effective_user.id, update.effective_user.full_name, "/reload")

@check_permission("can_debug")
async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Nutzung: /debug on|off")
        return
    mode = context.args[0].lower()
    if mode not in ("on", "off"):
        await update.message.reply_text("Nutzung: /debug on|off")
        return

    config = load_config()
    config["debug_enabled"] = (mode == "on")
    save_config(config)

    await update.message.reply_text(f"🧪 Debug ist jetzt **{mode.upper()}**.", parse_mode="Markdown")
    log_command(update.effective_user.id, update.effective_user.full_name, "/debug", details=mode)


# ---------------------------
# Auto-Moderation Handler
# ---------------------------

def message_contains_link(text: str) -> bool:
    if not text:
        return False
    # simple link detection
    return bool(re.search(r'(https?://|www\.|t\.me/)', text, re.IGNORECASE))

def text_hits_blacklist(text: str, blacklist: list[str]) -> str | None:
    if not text:
        return None
    lowered = text.lower()
    for w in blacklist:
        try:
            if w.lower() in lowered:
                return w
        except Exception:
            continue
    return None

async def apply_link_action(update: Update, context: ContextTypes.DEFAULT_TYPE, mode: str):
    if mode == "allow":
        return

    user = update.effective_user
    if not user:
        return

    if mode == "warn":
        # Nutze warn-Logik minimal ohne Permission-Check (Auto-Mod)
        data = load_moderation_data()
        block = ensure_user_block(data, user.id)
        block["warns"] += 1
        block["history"].append({
            "type": "auto_warn_link",
            "reason": "Link-Regel",
            "date": datetime.now().isoformat(),
            "by": "bot"
        })
        save_moderation_data(data)
        await update.message.reply_text(f"⚠️ {user.full_name}: Links sind hier eingeschränkt. Verwarnung +1.")
        return

    if mode == "mute":
        duration = timedelta(minutes=10)
        until_date = datetime.now() + duration
        try:
            await context.bot.restrict_chat_member(
                chat_id=update.effective_chat.id,
                user_id=user.id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until_date
            )
            await update.message.reply_text(f"🤐 {user.full_name} wurde wegen Link-Postings 10m stummgeschaltet.")
        except Exception as e:
            logger.error(f"Auto-Link-Mute Fehler: {e}")
        return

    if mode == "ban":
        try:
            await context.bot.ban_chat_member(update.effective_chat.id, user.id)
            await update.message.reply_text(f"🔨 {user.full_name} wurde wegen Link-Postings gebannt.")
        except Exception as e:
            logger.error(f"Auto-Link-Ban Fehler: {e}")
        return

async def automod_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Nur Gruppen/Topics
    if not update.message or update.effective_chat is None:
        return
    if update.effective_chat.type not in ("group", "supergroup"):
        return

    cfg = load_config()
    debug = cfg.get("debug_enabled", False)

    user = update.effective_user
    if not user or user.is_bot:
        return

    text = update.message.text or update.message.caption or ""

    # 1) Locks (basic)
    locks = cfg.get("locks", {})
    if locks.get("links", False) and message_contains_link(text):
        try:
            await update.message.delete()
        except:
            pass
        if debug:
            await update.message.reply_text("🔒 Links sind aktuell gesperrt.")
        return

    # Media lock (very light)
    if locks.get("media", False) and (update.message.photo or update.message.video or update.message.document):
        try:
            await update.message.delete()
        except:
            pass
        if debug:
            await update.message.reply_text("🔒 Medien sind aktuell gesperrt.")
        return

    # 2) Blacklist
    data = load_moderation_data()
    data = get_blacklist_block(data)
    hit = text_hits_blacklist(text, data["blacklist"])
    if hit:
        try:
            await update.message.delete()
        except:
            pass
        try:
            await update.message.reply_text(f"🚫 Nachricht entfernt (Blacklist-Treffer: `{hit}`).", parse_mode="Markdown")
        except:
            pass
        return

    # 3) Link Mode
    if message_contains_link(text):
        link_mode = cfg.get("link_mode", "allow")
        await apply_link_action(update, context, link_mode)
        # optional: delete link message when mode != allow
        if link_mode in ("warn", "mute", "ban"):
            try:
                await update.message.delete()
            except:
                pass

    # 4) Flood / Anti-Spam
    if cfg.get("antispam_enabled", False):
        limit = int(cfg.get("flood_limit", 5))
        window = int(cfg.get("flood_window_seconds", 10))

        chat_id = update.effective_chat.id
        user_id = user.id

        now = datetime.now().timestamp()
        dq = FLOOD_TRACKER[chat_id][user_id]
        dq.append(now)

        # purge old
        while dq and now - dq[0] > window:
            dq.popleft()

        if len(dq) > limit:
            # einfache Reaktion: kurze Mute
            try:
                until_date = datetime.now() + timedelta(minutes=1)
                await context.bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=until_date
                )
                try:
                    await update.message.reply_text(f"🌊 {user.full_name} zu viele Nachrichten – 1m Slowdown.")
                except:
                    pass
            except Exception as e:
                logger.error(f"Flood-Aktion Fehler: {e}")


# ---------------------------
# Bot Start
# ---------------------------

if __name__ == "__main__":
    config = load_config()
    token = config.get("bot_token")

    if not token:
        logger.info("NexusMod/ID Finder Bot ist deaktiviert oder Token fehlt.")
    else:
        app = ApplicationBuilder().token(token).build()

        # ID Tools
        app.add_handler(CommandHandler("id", get_id))
        app.add_handler(CommandHandler("chatid", get_chat_id))
        app.add_handler(CommandHandler("userid", get_user_id))
        app.add_handler(CommandHandler("topicid", get_topic_id))

        # Warn
        app.add_handler(CommandHandler("warn", warn_user))
        app.add_handler(CommandHandler("warnings", get_warnings))
        app.add_handler(CommandHandler("unwarn", unwarn_user))
        app.add_handler(CommandHandler("clearwarnings", clear_warnings))

        # Kick/Ban/Mute
        app.add_handler(CommandHandler("kick", kick_user))
        app.add_handler(CommandHandler("ban", ban_user))
        app.add_handler(CommandHandler("unban", unban_user))
        app.add_handler(CommandHandler("mute", mute_user))
        app.add_handler(CommandHandler("unmute", unmute_user))

        # Message Tools
        app.add_handler(CommandHandler("del", delete_message))
        app.add_handler(CommandHandler("purge", purge_messages))
        app.add_handler(CommandHandler("pin", pin_message))
        app.add_handler(CommandHandler("unpin", unpin_message))
        app.add_handler(CommandHandler("lock", lock_feature))
        app.add_handler(CommandHandler("unlock", unlock_feature))

        # Anti-Spam / Link / Blacklist
        app.add_handler(CommandHandler("antispam", antispam_command))
        app.add_handler(CommandHandler("setflood", setflood_command))
        app.add_handler(CommandHandler("setlinkmode", setlinkmode_command))
        app.add_handler(CommandHandler("blacklist", blacklist_command))

        # Roles & Rights
        app.add_handler(CommandHandler("adminlist", get_admin_list))
        app.add_handler(CommandHandler("mod", mod_command))
        app.add_handler(CommandHandler("permissions", permissions_command))
        app.add_handler(CommandHandler("setrole", setrole_command))

        # Onboarding
        app.add_handler(CommandHandler("welcome", welcome_command))
        app.add_handler(CommandHandler("setwelcome", setwelcome_command))
        app.add_handler(CommandHandler("rules", rules_command))
        app.add_handler(CommandHandler("setrules", setrules_command))
        app.add_handler(CommandHandler("verify", verify_command))

        # System
        app.add_handler(CommandHandler("settings", settings_command))
        app.add_handler(CommandHandler("config", config_command))
        app.add_handler(CommandHandler("status", status_command))
        app.add_handler(CommandHandler("reload", reload_command))
        app.add_handler(CommandHandler("debug", debug_command))

        # Auto-Mod Listener
        app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, automod_handler))

        logger.info("🧩 NexusMod Bot läuft...")
        app.run_polling()
