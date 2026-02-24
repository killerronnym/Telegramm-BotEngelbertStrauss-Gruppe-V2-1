import telebot
import schedule
import time
import threading
import json
import os
import random
import logging
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# --- Pfad-Hack für Shared Utils ---
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from shared_bot_utils import get_bot_config, get_env_var

# --- PATH SETUP ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, 'outfit_bot.log')
DATA_FILE = os.path.join(BASE_DIR, 'outfit_bot_data.json')

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

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
    except Exception as e: logging.error(f"Error saving data: {e}")

# --- CONFIG LOADER ---
def get_config():
    """Lädt Config aus DB + Env + Defaults"""
    db_config = get_bot_config("outfit")
    
    # Merge defaults
    config = DEFAULT_CONFIG.copy()
    config.update(db_config)
    
    # Token priority
    env_token = get_env_var("OUTFIT_BOT_TOKEN")
    if env_token:
        config["BOT_TOKEN"] = env_token
        
    return config

# --- BOT INIT ---
cfg = get_config()
token = cfg.get("bot_token") or cfg.get("BOT_TOKEN")

if not token or token == "DUMMY":
    logging.warning("Outfit-Bot hat keinen Token. Bitte OUTFIT_BOT_TOKEN setzen oder DB konfigurieren.")
    # No polling if no valid token
    bot = None
else:
    bot = telebot.TeleBot(token, threaded=False)


def get_topic_id(cfg):
    """Returns the Topic ID as an integer if it exists."""
    topic_id_str = cfg.get("TOPIC_ID")
    return int(topic_id_str) if topic_id_str and str(topic_id_str).isdigit() else None

def is_admin(user_id):
    """Checks if a user is an admin."""
    admins = get_config().get("ADMIN_USER_IDS", [])
    return str(user_id) in [str(uid) for uid in admins]

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

def pin_daily_post_message(chat_id, message_id: int, topic_id=None):
    cfg = get_config()
    if not cfg.get("PIN_DAILY_POST", True): return

    try:
        bot.pin_chat_message(
            chat_id=chat_id,
            message_id=int(message_id),
            disable_notification=cfg.get("PIN_DISABLE_NOTIFICATION", True)
        )
        _save_pinned_message_id(int(message_id))
    except Exception as e:
        logging.error(f"Error pinning: {e}")

def unpin_daily_post_message(chat_id, topic_id=None):
    data = load_data(DATA_FILE, {})
    pinned_id = data.get("pinned_message_id")
    if not pinned_id: return

    try:
        bot.unpin_chat_message(chat_id=chat_id, message_id=int(pinned_id))
        _clear_pinned_message_id()
    except Exception as e:
        logging.error(f"Error unpinning: {e}")

def reset_contest_data(is_starting_new_contest=False):
    cfg = get_config()
    chat_id = cfg.get("CHAT_ID")
    topic_id = get_topic_id(cfg)

    if chat_id: unpin_daily_post_message(chat_id, topic_id)

    new_data = {
        "submissions": {},
        "votes": {},
        "contest_active": is_starting_new_contest,
        "max_votes": 0,
        "current_duel": None
    }
    save_data(DATA_FILE, new_data)

def generate_markup(user_id, likes=0, loves=0, fires=0):
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton(f"👍 ({likes})", callback_data=f"vote_like_{user_id}"),
        types.InlineKeyboardButton(f"❤️ ({loves})", callback_data=f"vote_love_{user_id}"),
        types.InlineKeyboardButton(f"🔥 ({fires})", callback_data=f"vote_fire_{user_id}")
    )
    return markup

def count_votes(votes_dict):
    counts = {'like': 0, 'love': 0, 'fire': 0}
    for v in votes_dict.values():
        if v in counts: counts[v] += 1
    return counts

# --- CORE LOGIC ---
def send_daily_post():
    reset_contest_data(is_starting_new_contest=True)
    cfg = get_config()
    chat_id = cfg.get("CHAT_ID")
    if not chat_id: return
    
    topic_id = get_topic_id(cfg)
    try:
        bot_username = bot.get_me().username
        markup = types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("Mitmachen", url=f"https://t.me/{bot_username}?start=participate")
        )
        sent = bot.send_message(
            chat_id,
            "📸 Outfit des Tages – zeigt eure heutigen E.S-Outfits!",
            reply_markup=markup,
            message_thread_id=topic_id
        )
        pin_daily_post_message(chat_id, sent.message_id, topic_id)
    except Exception as e:
        logging.error(f"Daily post error: {e}")

def determine_winner():
    cfg = get_config()
    chat_id = cfg.get("CHAT_ID")
    if not chat_id: return
    topic_id = get_topic_id(cfg)

    data = load_data(DATA_FILE)
    votes = data.get("votes", {})
    
    if not votes:
        try: bot.send_message(chat_id, "Keine Stimmen heute.", message_thread_id=topic_id)
        except: pass
        reset_contest_data(False)
        return

    # Count votes per submission (message_id)
    results = {}
    for msg_id, v_dict in votes.items():
        results[msg_id] = len(v_dict)
    
    if not results:
        reset_contest_data(False)
        return

    max_votes = max(results.values())
    winners = [mid for mid, c in results.items() if c == max_votes]
    
    if max_votes <= 0:
        bot.send_message(chat_id, "Keine Stimmen abgegeben.", message_thread_id=topic_id)
        reset_contest_data(False)
        return

    # Announce
    submissions = data.get("submissions", {})
    winner_names = []
    
    # Map message_id back to user submission
    for uid, sub in submissions.items():
        if str(sub["message_id"]) in winners:
            winner_names.append(f"@{sub.get('username', 'Unknown')}")
            
    text = f"🏆 Gewinner: {', '.join(winner_names)} mit {max_votes} Stimmen!"
    bot.send_message(chat_id, text, message_thread_id=topic_id)
    
    reset_contest_data(False)

# --- HANDLERS ---
@bot.message_handler(commands=['start'])
def handle_start(message):
    if message.chat.type == 'private':
        if "participate" in message.text:
            bot.send_message(message.chat.id, "Bitte sende jetzt dein Foto!")
        else:
            bot.send_message(message.chat.id, "Hallo vom Outfit-Bot!")

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    if message.chat.type != 'private': return
    
    data = load_data(DATA_FILE)
    if not data.get("contest_active"):
        bot.send_message(message.chat.id, "Kein Wettbewerb aktiv.")
        return
        
    user_id = str(message.from_user.id)
    if user_id in data.get("submissions", {}):
        bot.send_message(message.chat.id, "Du hast schon teilgenommen.")
        return

    cfg = get_config()
    chat_id = cfg.get("CHAT_ID")
    topic_id = get_topic_id(cfg)
    
    try:
        sent = bot.send_photo(
            chat_id, 
            message.photo[-1].file_id, 
            caption=f"Outfit von @{message.from_user.username}", 
            reply_markup=generate_markup(message.from_user.id),
            message_thread_id=topic_id
        )
        
        data.setdefault("submissions", {})[user_id] = {
            "message_id": sent.message_id,
            "photo_id": message.photo[-1].file_id,
            "username": message.from_user.username
        }
        data.setdefault("votes", {})[str(sent.message_id)] = {}
        save_data(DATA_FILE, data)
        bot.send_message(message.chat.id, "Foto gesendet!")
    except Exception as e:
        logging.error(f"Send photo error: {e}")
        bot.send_message(message.chat.id, "Fehler beim Senden.")

@bot.callback_query_handler(func=lambda call: True)
def handle_vote(call):
    try:
        _, vote_type, target_user_id = call.data.split('_')
    except: return

    data = load_data(DATA_FILE)
    user_id = str(call.from_user.id)
    
    # Find message ID
    target_msg_id = None
    for uid, sub in data.get("submissions", {}).items():
        if str(uid) == target_user_id:
            target_msg_id = str(sub["message_id"])
            break
            
    if not target_msg_id: return
    
    votes = data.get("votes", {}).get(target_msg_id, {})
    if votes.get(user_id) == vote_type:
        del votes[user_id]
        txt = "Entfernt."
    else:
        votes[user_id] = vote_type
        txt = f"{vote_type}!"
        
    data["votes"][target_msg_id] = votes
    save_data(DATA_FILE, data)
    
    counts = count_votes(votes)
    try:
        bot.edit_message_reply_markup(
            call.message.chat.id,
            call.message.message_id,
            reply_markup=generate_markup(target_user_id, counts['like'], counts['love'], counts['fire'])
        )
        bot.answer_callback_query(call.id, txt)
    except: pass

def process_triggers():
    """Prüft auf manuelle Trigger-Dateien vom Dashboard."""
    start_trigger = os.path.join(BASE_DIR, "start_contest.tmp")
    winner_trigger = os.path.join(BASE_DIR, "announce_winner.tmp")
    
    while True:
        try:
            if os.path.exists(start_trigger):
                logging.info("Manueller Trigger: Wettbewerb starten")
                os.remove(start_trigger)
                send_daily_post()
            
            if os.path.exists(winner_trigger):
                logging.info("Manueller Trigger: Gewinner auslosen")
                os.remove(winner_trigger)
                determine_winner()
        except Exception as e:
            logging.error(f"Fehler bei Trigger-Verarbeitung: {e}")
            
        time.sleep(5)

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    cfg = get_config()
    if cfg.get("AUTO_POST_ENABLED"):
        schedule.every().day.at(cfg.get("POST_TIME", "18:00")).do(send_daily_post)
        schedule.every().day.at(cfg.get("WINNER_TIME", "22:00")).do(determine_winner)

    threading.Thread(target=run_scheduler, daemon=True).start()
    threading.Thread(target=process_triggers, daemon=True).start()
    
    if bot and token and token != "DUMMY":
        try:
            logging.info("Outfit Bot startet...")
            bot.polling(non_stop=True)
        except Exception as e:
            logging.error(f"Polling Crash: {e}")
    else:
        logging.error("Outfit Bot konnte nicht gestartet werden (kein valider Token). Beende...")
