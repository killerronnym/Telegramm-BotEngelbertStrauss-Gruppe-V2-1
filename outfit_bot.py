
import telebot
import schedule
import time
import threading
import json
import os
import random
import logging
from telebot import types

# --- LOGGING SETUP ---
logging.basicConfig(
    filename='outfit_bot.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- CONFIG & DATA MANAGEMENT ---
CONFIG_FILE = 'outfit_bot_config.json'
DATA_FILE = 'outfit_bot_data.json'

DEFAULT_CONFIG = {
    "BOT_TOKEN": "DEIN_TELEGRAM_BOT_TOKEN_HIER",
    "CHAT_ID": "DEINE_GRUPPEN_CHAT_ID_HIER",
    "TOPIC_ID": "", # NEU
    "POST_TIME": "18:00",
    "WINNER_TIME": "22:00",
    "AUTO_POST_ENABLED": True,
    "ADMIN_USER_IDS": []
}

def load_json(filename, default_data=None):
    if not os.path.exists(filename) or os.path.getsize(filename) == 0:
        if default_data: save_json(filename, default_data)
        return default_data or {}
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            # Stelle sicher, dass die globale config-Variable aktualisiert wird
            if filename == CONFIG_FILE:
                global config
                config = json.load(f)
                return config
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        logging.error(f"Fehler beim Laden von JSON-Datei {filename}: {e}", exc_info=True)
        return default_data or {}

def save_json(filename, data):
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logging.info(f"Daten erfolgreich in {filename} gespeichert.")
    except Exception as e:
        logging.error(f"Fehler beim Speichern von JSON-Datei {filename}: {e}", exc_info=True)

config = load_json(CONFIG_FILE, DEFAULT_CONFIG)
logging.info("Outfit-Bot Skript gestartet.")
bot = telebot.TeleBot(config.get("BOT_TOKEN", "DUMMY"), threaded=False)

# --- HELPER ---
def get_topic_id():
    """Lädt die Konfiguration neu und gibt die Topic ID als Integer zurück, falls vorhanden."""
    current_conf = load_json(CONFIG_FILE)
    topic_id_str = current_conf.get("TOPIC_ID")
    return int(topic_id_str) if topic_id_str and topic_id_str.isdigit() else None

def is_admin(user_id):
    current_admins = load_json(CONFIG_FILE).get("ADMIN_USER_IDS", [])
    return user_id in current_admins

def reset_contest_data():
    empty_data = {"submissions": {}, "votes": {}}
    save_json(DATA_FILE, empty_data)
    logging.info("Wettbewerbsdaten zurückgesetzt.")

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
    for vote_type in votes_dict.values():
        if vote_type in counts:
            counts[vote_type] += 1
    return counts

# --- CORE FUNCTIONS ---
def send_daily_post():
    logging.info("Versuche, täglichen Post zu senden...")
    reset_contest_data()
    current_conf = load_json(CONFIG_FILE)
    chat_id = current_conf.get("CHAT_ID")
    topic_id = get_topic_id()
    if bot.token != current_conf.get("BOT_TOKEN"): bot.token = current_conf.get("BOT_TOKEN")

    if not chat_id: return

    try:
        bot_username = bot.get_me().username
        start_url = f"https://t.me/{bot_username}?start=participate"
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("Mitmachen", url=start_url))
        bot.send_message(chat_id, "📸 Outfit des Tages – zeigt eure heutigen E.S-Outfits!", reply_markup=markup, message_thread_id=topic_id)
        logging.info(f"Täglicher Post erfolgreich an Chat {chat_id} (Topic: {topic_id}) gesendet.")
    except Exception as e: logging.error(f"Fehler beim Senden des Posts: {e}", exc_info=True)

def determine_winner():
    logging.info("Ermittle Gewinner...")
    current_conf = load_json(CONFIG_FILE)
    chat_id = current_conf.get("CHAT_ID")
    topic_id = get_topic_id()
    if bot.token != current_conf.get("BOT_TOKEN"): bot.token = current_conf.get("BOT_TOKEN")

    bot_data = load_json(DATA_FILE)
    if not bot_data.get("submissions"):
        if chat_id:
            try: bot.send_message(chat_id, "Für den heutigen Wettbewerb gab es leider keine Einreichungen.", message_thread_id=topic_id)
            except: pass
        return
    
    # ... (Rest der Gewinnerlogik bleibt gleich, da sie nur die Daten analysiert)
    
    winner_info = {}
    max_votes = -1
    for msg_id, votes in bot_data.get("votes", {}).items():
        total_votes = len(votes)
        if total_votes > max_votes:
            max_votes = total_votes
            winner_info = {msg_id: total_votes}
        elif total_votes == max_votes:
            winner_info[msg_id] = total_votes

    if not winner_info or max_votes <= 0:
        if chat_id:
            try: bot.send_message(chat_id, "Es wurden keine Stimmen abgegeben. Es gibt heute keinen Gewinner.", message_thread_id=topic_id)
            except: pass
        reset_contest_data()
        return

    winner_message_id = random.choice(list(winner_info.keys()))
    winner_user_id = next((uid for uid, sdata in bot_data["submissions"].items() if str(sdata["message_id"]) == winner_message_id), None)
    
    if winner_user_id:
        try:
            user_info = bot.get_chat(winner_user_id)
            username = user_info.username or user_info.first_name
            photo_id = bot_data["submissions"][winner_user_id]["photo_id"]
            caption = f"🏆 Outfit des Tages: @{username} mit {max_votes} Reaktionen! Herzlichen Glückwunsch! 🥳"
            bot.send_photo(chat_id, photo_id, caption=caption, message_thread_id=topic_id)
            logging.info(f"Gewinner bekannt gegeben: {username} in Chat {chat_id} (Topic: {topic_id}).")
        except Exception as e: logging.error(f"Fehler bei Gewinner-Bekanntgabe: {e}", exc_info=True)
    reset_contest_data()

# --- HANDLERS ---
@bot.message_handler(content_types=['photo'])
def handle_photo_submission(message):
    if message.chat.type != 'private': return
    user_id = str(message.from_user.id)
    username = message.from_user.username or message.from_user.first_name
    
    current_conf = load_json(CONFIG_FILE)
    chat_id = current_conf.get("CHAT_ID")
    topic_id = get_topic_id()

    bot_data = load_json(DATA_FILE)
    if user_id in bot_data.get("submissions", {}):
        bot.reply_to(message, "🚫 Du hast bereits ein Bild für diesen Wettbewerb hochgeladen.")
        return

    photo_id = message.photo[-1].file_id
    caption = f"Outfit von @{username}"
    markup = generate_markup(int(user_id))
    
    try:
        sent_message = bot.send_photo(chat_id, photo_id, caption=caption, reply_markup=markup, message_thread_id=topic_id)
        
        if "submissions" not in bot_data: bot_data["submissions"] = {}
        if "votes" not in bot_data: bot_data["votes"] = {}
        
        bot_data["submissions"][user_id] = {"message_id": sent_message.message_id, "photo_id": photo_id, "username": username}
        bot_data["votes"][str(sent_message.message_id)] = {}
        save_json(DATA_FILE, bot_data)
        
        bot.reply_to(message, "✅ Dein Outfit wurde erfolgreich in der Gruppe gepostet!")
    except Exception as e:
        bot.reply_to(message, "😥 Fehler beim Posten. Ist der Bot Admin in der Gruppe?")
        logging.error(f"Fehler beim Posten von Foto: {e}", exc_info=True)

# ... (Rest der Handler bleibt gleich) ...
@bot.callback_query_handler(func=lambda call: call.data.startswith('vote_'))
def handle_vote(call):
    voter_id = call.from_user.id
    message_id = str(call.message.message_id)
    chat_id = call.message.chat.id
    
    try:
        _, vote_type, submitter_id_str = call.data.split('_')
        submitter_id = int(submitter_id_str)
    except ValueError: 
        logging.error(f"Parse Error Callback: {call.data}")
        return

    bot_data = load_json(DATA_FILE)
    votes = bot_data.get("votes", {}).get(message_id, {})
    voter_id_str = str(voter_id)

    feedback = ''
    if votes.get(voter_id_str) == vote_type:
        del votes[voter_id_str]
        feedback = f'Stimme ({vote_type}) zurückgezogen.'
    else:
        votes[voter_id_str] = vote_type
        feedback = f'Du hast mit {vote_type} gestimmt.'
    
    bot_data["votes"][message_id] = votes
    save_json(DATA_FILE, bot_data)
    
    counts = count_votes(votes)
    new_markup = generate_markup(submitter_id, counts['like'], counts['love'], counts['fire'])
    
    try:
        bot.edit_message_reply_markup(chat_id=chat_id, message_id=int(message_id), reply_markup=new_markup)
    except Exception as e:
        if "message is not modified" not in str(e).lower():
            logging.error(f"Fehler beim Update der Buttons für Message {message_id}: {e}", exc_info=True)

    try:
        bot.answer_callback_query(call.id, feedback)
    except Exception: pass

@bot.message_handler(commands=['start'])
def handle_start(message):
    if message.chat.type == 'private':
        bot.reply_to(message, "Hallo! Schick mir jetzt dein Outfit-Foto.")

# --- ADMIN COMMANDS ---
@bot.message_handler(commands=['start_contest', 'announce_winner'])
def handle_admin_commands(message):
    if not is_admin(message.from_user.id): return
    command = message.text.split()[0][1:]
    if command == "start_contest":
        bot.reply_to(message, "Start manuell ausgelöst.")
        send_daily_post()
    elif command == "announce_winner":
        bot.reply_to(message, "Gewinner-Ermittlung ausgelöst.")
        determine_winner()

# --- THREADS ---
def command_listener():
    logging.info("Befehls-listener gestartet.")
    while True:
        try:
            if os.path.exists("command_start_contest.tmp"):
                send_daily_post()
                os.remove("command_start_contest.tmp")
            if os.path.exists("command_announce_winner.tmp"):
                determine_winner()
                os.remove("command_announce_winner.tmp")
        except Exception: pass
        time.sleep(2)

def run_scheduler():
    load_schedules()
    schedule.every(30).minutes.do(load_schedules)
    while True:
        schedule.run_pending()
        time.sleep(1)

def load_schedules():
    schedule.clear()
    cfg = load_json(CONFIG_FILE)
    if cfg.get("AUTO_POST_ENABLED"):
        post_time = cfg.get("POST_TIME", "18:00")
        winner_time = cfg.get("WINNER_TIME", "22:00")
        schedule.every().day.at(post_time).do(send_daily_post)
        schedule.every().day.at(winner_time).do(determine_winner)

if __name__ == "__main__":
    threading.Thread(target=command_listener, daemon=True).start()
    threading.Thread(target=run_scheduler, daemon=True).start()
    
    while True:
        try:
            current_token = load_json(CONFIG_FILE).get("BOT_TOKEN")
            if current_token and current_token != bot.token:
                bot.token = current_token
            
            if bot.token and bot.token != "DEIN_TELEGRAM_BOT_TOKEN_HIER":
                bot.polling(none_stop=True, skip_pending=True)
            else:
                time.sleep(10)
        except Exception as e:
            logging.error(f"Polling Crash: {e}", exc_info=True)
            time.sleep(15)
