import os
import sys
import json
import logging
import asyncio
from datetime import datetime

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from shared_bot_utils import get_bot_config, is_bot_active

# --- PATH SETUP ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, '..', '..'))
LOG_FILE = os.path.join(BASE_DIR, 'outfit_bot.log')
DATA_FILE = os.path.join(PROJECT_ROOT, 'instance', 'outfit_bot_data.json')

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('outfit_bot')

DEFAULT_CONFIG = {
    "CHAT_ID": "",
    "TOPIC_ID": "",
    "POST_TIME": "18:00",
    "WINNER_TIME": "22:00",
    "AUTO_POST_ENABLED": True,
    "ADMIN_USER_IDS": [],
    "DUEL_MODE": False,
    "DUEL_TYPE": "tie_breaker",
    "DUEL_DURATION_MINUTES": 60,
    "TEMPORARY_MESSAGE_DURATION_SECONDS": 30,
    "PIN_DAILY_POST": True,
    "PIN_DISABLE_NOTIFICATION": True
}

def load_data(filename, default=None):
    if not os.path.exists(filename): return default if default is not None else {}
    try:
        with open(filename, 'r', encoding='utf-8') as f: return json.load(f)
    except: return default if default is not None else {}

def save_data(filename, data):
    try:
        with open(filename, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4)
    except Exception as e: logger.error(f"Error saving data: {e}")

def get_config():
    db_config = get_bot_config("outfit")
    config = DEFAULT_CONFIG.copy()
    config.update(db_config)
    return config

def get_topic_id(cfg):
    topic_id_str = cfg.get("TOPIC_ID")
    return int(topic_id_str) if topic_id_str and str(topic_id_str).isdigit() else None

# --- PIN / UNPIN HELPERS ---
def _save_pinned_message_id(message_id: int):
    data = load_data(DATA_FILE, {})
    data["pinned_message_id"] = int(message_id)
    save_data(DATA_FILE, data)

def _clear_pinned_message_id():
    data = load_data(DATA_FILE, {})
    if "pinned_message_id" in data:
        del data["pinned_message_id"]
        save_data(DATA_FILE, data)

async def pin_daily_post_message(bot, chat_id, message_id: int):
    cfg = get_config()
    if not cfg.get("PIN_DAILY_POST", True): return
    try:
        await bot.pin_chat_message(
            chat_id=chat_id,
            message_id=int(message_id),
            disable_notification=cfg.get("PIN_DISABLE_NOTIFICATION", True)
        )
        _save_pinned_message_id(int(message_id))
    except Exception as e:
        logger.error(f"Error pinning: {e}")

async def unpin_daily_post_message(bot, chat_id):
    data = load_data(DATA_FILE, {})
    pinned_id = data.get("pinned_message_id")
    if not pinned_id: return
    try:
        await bot.unpin_chat_message(chat_id=chat_id, message_id=int(pinned_id))
        _clear_pinned_message_id()
    except Exception as e:
        logger.error(f"Error unpinning: {e}")

async def reset_contest_data(bot, is_starting_new_contest=False):
    cfg = get_config()
    chat_id = cfg.get("CHAT_ID")
    if chat_id: await unpin_daily_post_message(bot, chat_id)

    new_data = {
        "submissions": {},
        "votes": {},
        "contest_active": is_starting_new_contest,
        "max_votes": 0,
        "current_duel": None
    }
    save_data(DATA_FILE, new_data)

def generate_markup(user_id, likes=0, loves=0, fires=0):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"👍 ({likes})", callback_data=f"outfitvote_like_{user_id}"),
            InlineKeyboardButton(f"❤️ ({loves})", callback_data=f"outfitvote_love_{user_id}"),
            InlineKeyboardButton(f"🔥 ({fires})", callback_data=f"outfitvote_fire_{user_id}")
        ]
    ])

def count_votes(votes_dict):
    counts = {'like': 0, 'love': 0, 'fire': 0}
    for v in votes_dict.values():
        if v in counts: counts[v] += 1
    return counts

# --- CORE LOGIC ---
async def send_daily_post(context: ContextTypes.DEFAULT_TYPE):
    if not is_bot_active('outfit'): return
    await reset_contest_data(context.bot, is_starting_new_contest=True)
    cfg = get_config()
    chat_id = cfg.get("CHAT_ID")
    if not chat_id: return
    
    topic_id = get_topic_id(cfg)
    try:
        bot_user = await context.bot.get_me()
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("Mitmachen", url=f"https://t.me/{bot_user.username}?start=participate")]])
        sent = await context.bot.send_message(
            chat_id=chat_id,
            text="📸 Outfit des Tages – zeigt eure heutigen E.S-Outfits!",
            reply_markup=markup,
            message_thread_id=topic_id
        )
        await pin_daily_post_message(context.bot, chat_id, sent.message_id)
    except Exception as e:
        logger.error(f"Daily post error: {e}")

async def determine_winner(context: ContextTypes.DEFAULT_TYPE):
    if not is_bot_active('outfit'): return
    cfg = get_config()
    chat_id = cfg.get("CHAT_ID")
    if not chat_id: return
    topic_id = get_topic_id(cfg)

    data = load_data(DATA_FILE)
    votes = data.get("votes", {})
    
    if not votes:
        try: await context.bot.send_message(chat_id=chat_id, text="Keine Stimmen heute.", message_thread_id=topic_id)
        except: pass
        await reset_contest_data(context.bot, False)
        return

    results = {}
    for msg_id, v_dict in votes.items():
        results[msg_id] = len(v_dict)
    
    if not results:
        await reset_contest_data(context.bot, False)
        return

    max_votes = max(results.values())
    winners = [mid for mid, c in results.items() if c == max_votes]
    
    if max_votes <= 0:
        await context.bot.send_message(chat_id=chat_id, text="Keine Stimmen abgegeben.", message_thread_id=topic_id)
        await reset_contest_data(context.bot, False)
        return

    submissions = data.get("submissions", {})
    winner_names = []
    for uid, sub in submissions.items():
        if str(sub["message_id"]) in winners:
            winner_names.append(f"@{sub.get('username', 'Unknown')}")
            
    text = f"🏆 Gewinner: {', '.join(winner_names)} mit {max_votes} Stimmen!"
    await context.bot.send_message(chat_id=chat_id, text=text, message_thread_id=topic_id)
    await reset_contest_data(context.bot, False)

# --- HANDLERS ---
async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_bot_active('outfit'): return
    if update.message.chat.type == 'private':
        if "participate" in update.message.text:
            await update.message.reply_text("Bitte sende jetzt dein Foto (Outfit des Tages)!")
        else:
            await update.message.reply_text("Hallo vom Outfit-Bot!")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_bot_active('outfit'): return
    if update.message.chat.type != 'private': return
    
    data = load_data(DATA_FILE)
    if not data.get("contest_active"):
        await update.message.reply_text("Aktuell ist kein Wettbewerb gestartet.")
        return
        
    user_id = str(update.effective_user.id)
    if user_id in data.get("submissions", {}):
        await update.message.reply_text("Du hast heute schon teilgenommen!")
        return

    cfg = get_config()
    chat_id = cfg.get("CHAT_ID")
    topic_id = get_topic_id(cfg)
    
    try:
        photo_file_id = update.message.photo[-1].file_id
        sent = await context.bot.send_photo(
            chat_id=chat_id, 
            photo=photo_file_id, 
            caption=f"Outfit von @{update.effective_user.username}", 
            reply_markup=generate_markup(update.effective_user.id),
            message_thread_id=topic_id
        )
        
        data.setdefault("submissions", {})[user_id] = {
            "message_id": sent.message_id,
            "photo_id": photo_file_id,
            "username": update.effective_user.username
        }
        data.setdefault("votes", {})[str(sent.message_id)] = {}
        save_data(DATA_FILE, data)
        await update.message.reply_text("Foto erfolgreich eingereicht! Viel Erfolg.")
    except Exception as e:
        logger.error(f"Send photo error: {e}")
        await update.message.reply_text("Fehler beim Senden in die Gruppe.")

async def handle_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_bot_active('outfit'): return
    query = update.callback_query
    
    try:
        _, vote_type, target_user_id = query.data.split('_')
    except: return

    data = load_data(DATA_FILE)
    user_id = str(query.from_user.id)
    
    target_msg_id = None
    for uid, sub in data.get("submissions", {}).items():
        if str(uid) == target_user_id:
            target_msg_id = str(sub["message_id"])
            break
            
    if not target_msg_id: 
        await query.answer("Beitrag nicht gefunden.")
        return
    
    votes = data.get("votes", {}).get(target_msg_id, {})
    if votes.get(user_id) == vote_type:
        del votes[user_id]
        txt = "Stimme entfernt."
    else:
        votes[user_id] = vote_type
        txt = f"Abgestimmt: {vote_type.capitalize()}!"
        
    data["votes"][target_msg_id] = votes
    save_data(DATA_FILE, data)
    
    counts = count_votes(votes)
    try:
        await query.edit_message_reply_markup(
            reply_markup=generate_markup(target_user_id, counts['like'], counts['love'], counts['fire'])
        )
        await query.answer(txt)
    except: 
        pass

# --- SCHEDULER WERKZEUGE ---
async def check_triggers(context: ContextTypes.DEFAULT_TYPE):
    if not is_bot_active('outfit'): return
    start_trigger = os.path.join(BASE_DIR, "start_contest.tmp")
    winner_trigger = os.path.join(BASE_DIR, "announce_winner.tmp")
    
    if os.path.exists(start_trigger):
        logger.info("Manueller Trigger erkannt: Wettbewerb starten")
        os.remove(start_trigger)
        await send_daily_post(context)
        
    if os.path.exists(winner_trigger):
        logger.info("Manueller Trigger erkannt: Gewinner auslosen")
        os.remove(winner_trigger)
        await determine_winner(context)

async def check_schedule(context: ContextTypes.DEFAULT_TYPE):
    if not is_bot_active('outfit'): return
    cfg = get_config()
    if not cfg.get("AUTO_POST_ENABLED"): return
    
    now = datetime.now()
    post_time_str = cfg.get("POST_TIME", "18:00")
    winner_time_str = cfg.get("WINNER_TIME", "22:00")
    
    # Very simple time check for exact minute hit:
    current_time_str = now.strftime("%H:%M")
    
    # Um Doppelpostings zu vermeiden, speichern wir das Datum in config/data
    data = load_data(DATA_FILE)
    last_post = data.get("last_auto_post_date", "")
    last_winner = data.get("last_auto_winner_date", "")
    today_str = now.strftime("%Y-%m-%d")
    
    if current_time_str == post_time_str and last_post != today_str:
        await send_daily_post(context)
        data["last_auto_post_date"] = today_str
        save_data(DATA_FILE, data)
        
    if current_time_str == winner_time_str and last_winner != today_str:
        await determine_winner(context)
        data["last_auto_winner_date"] = today_str
        save_data(DATA_FILE, data)

# --- PLUGIN EXPORT ---
def get_handlers():
    return [
        CommandHandler("start", handle_start),
        MessageHandler(filters.PHOTO, handle_photo),
        CallbackQueryHandler(handle_vote, pattern=r'^outfitvote_')
    ]

def setup_jobs(job_queue):
    logger.info("Outfit Bot Job Queue registriert...")
    job_queue.run_repeating(check_triggers, interval=5)
    job_queue.run_repeating(check_schedule, interval=60)

if __name__ == "__main__":
    print("Bitte main_bot.py verwenden!")
