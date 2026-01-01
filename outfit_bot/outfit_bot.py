import telebot
import schedule
import time
import threading
import json
import os
import random
import logging
from telebot import types
from datetime import datetime, timedelta

# --- LOGGING SETUP ---
LOG_FILE = 'outfit_bot.log'
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- CONFIG & DATA MANAGEMENT ---
CONFIG_FILE = 'outfit_bot_config.json'
DATA_FILE = 'outfit_bot_data.json'

DEFAULT_CONFIG = {
    "BOT_TOKEN": "DUMMY",
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
    "PIN_DAILY_POST": True,                 # ✅ NEU: Daily-Post wird angepinnt
    "PIN_DISABLE_NOTIFICATION": True        # ✅ NEU: Pin ohne Benachrichtigung
}


def load_json(filename, default_data=None):
    if not os.path.exists(filename) or os.path.getsize(filename) == 0:
        if default_data:
            save_json(filename, default_data)
        return default_data or {}
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        logging.error(f"Error loading JSON file {filename}: {e}", exc_info=True)
        return default_data or {}


def save_json(filename, data):
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logging.info(f"Data successfully saved to {filename}.")
    except Exception as e:
        logging.error(f"Error saving JSON file {filename}: {e}", exc_info=True)


config = load_json(CONFIG_FILE, DEFAULT_CONFIG)

# --- WICHTIGER FIX ---
initial_token = config.get("BOT_TOKEN")
if not initial_token or initial_token == "DUMMY":
    logging.warning(
        "Outfit-Bot startet mit Platzhalter-Token. Bitte einen gültigen BOT_TOKEN in outfit_bot_config.json setzen."
    )
    initial_token = "0:dummy"

bot = telebot.TeleBot(initial_token, threaded=False)


# --- HELPER FUNCTIONS ---
def get_config():
    """Safely reloads the config from file."""
    return load_json(CONFIG_FILE, DEFAULT_CONFIG)


def get_topic_id(cfg):
    """Returns the Topic ID as an integer if it exists."""
    topic_id_str = cfg.get("TOPIC_ID")
    return int(topic_id_str) if topic_id_str and str(topic_id_str).isdigit() else None


def is_admin(user_id):
    """Checks if a user is an admin."""
    return user_id in get_config().get("ADMIN_USER_IDS", [])


# --- PIN / UNPIN HELPERS ---
def _save_pinned_message_id(message_id: int):
    """Speichert die message_id der angepinnten Daily-Post Nachricht."""
    try:
        bot_data = load_json(DATA_FILE, {})
        bot_data["pinned_message_id"] = int(message_id)
        save_json(DATA_FILE, bot_data)
        logging.info(f"Saved pinned_message_id={message_id} to DATA_FILE.")
    except Exception as e:
        logging.error(f"Could not save pinned_message_id: {e}", exc_info=True)


def _clear_pinned_message_id():
    """Entfernt die gespeicherte pinned_message_id aus den Bot-Daten."""
    try:
        bot_data = load_json(DATA_FILE, {})
        if "pinned_message_id" in bot_data:
            del bot_data["pinned_message_id"]
            save_json(DATA_FILE, bot_data)
            logging.info("Cleared pinned_message_id from DATA_FILE.")
    except Exception as e:
        logging.error(f"Could not clear pinned_message_id: {e}", exc_info=True)


def pin_daily_post_message(chat_id, message_id: int, topic_id=None):
    """Pinnt die Daily-Post Nachricht (versucht topic pin, falls supported)."""
    cfg = get_config()
    if not cfg.get("PIN_DAILY_POST", True):
        return

    disable_notification = cfg.get("PIN_DISABLE_NOTIFICATION", True)

    try:
        # Versuch: Topic-Pin (falls die Telebot-Version message_thread_id unterstützt)
        try:
            bot.pin_chat_message(
                chat_id=chat_id,
                message_id=int(message_id),
                disable_notification=disable_notification,
                message_thread_id=topic_id
            )
            logging.info(f"Pinned daily post message {message_id} in chat {chat_id} (topic {topic_id}).")
        except TypeError:
            # Fallback: normales Pin (ohne topic-Parameter)
            bot.pin_chat_message(
                chat_id=chat_id,
                message_id=int(message_id),
                disable_notification=disable_notification
            )
            logging.info(f"Pinned daily post message {message_id} in chat {chat_id} (no topic param support).")

        _save_pinned_message_id(int(message_id))
    except Exception as e:
        logging.error(f"Error pinning daily post message: {e}", exc_info=True)


def unpin_daily_post_message(chat_id, topic_id=None):
    """
    Entfernt den Pin NUR von der gespeicherten Daily-Post Nachricht.
    (WICHTIG: unpin_all_* wird NICHT verwendet!)
    """
    try:
        bot_data = load_json(DATA_FILE, {})
        pinned_id = bot_data.get("pinned_message_id")
        if not pinned_id:
            return

        pinned_id = int(pinned_id)

        # Versuch: Topic-Unpin (falls supported)
        try:
            bot.unpin_chat_message(
                chat_id=chat_id,
                message_id=pinned_id,
                message_thread_id=topic_id
            )
            logging.info(f"Unpinned daily post message {pinned_id} in chat {chat_id} (topic {topic_id}).")
        except TypeError:
            # Fallback: normales unpin
            bot.unpin_chat_message(
                chat_id=chat_id,
                message_id=pinned_id
            )
            logging.info(f"Unpinned daily post message {pinned_id} in chat {chat_id} (no topic param support).")

        _clear_pinned_message_id()
    except Exception as e:
        logging.error(f"Error unpinning daily post message: {e}", exc_info=True)


def reset_contest_data(is_starting_new_contest=False):
    """
    Setzt die Wettbewerbsdaten sauber zurück.

    Zusätzlich:
    - Wenn der Contest beendet wird -> Pin der Daily-Post Nachricht entfernen.
    - Wenn ein neuer Contest startet -> ggf. alten Pin entfernen (failsafe),
      damit nie ein alter Daily-Post hängen bleibt.
    """
    cfg = get_config()
    chat_id = cfg.get("CHAT_ID")
    topic_id = get_topic_id(cfg)

    # Pin-Handling:
    # - Bei Start eines neuen Contests: alten Pin vorsichtshalber entfernen.
    # - Bei Beenden des Contests: Pin entfernen.
    if chat_id:
        if is_starting_new_contest:
            # Failsafe: falls vorheriger Pin noch hängt
            unpin_daily_post_message(chat_id, topic_id)
        else:
            # Contest endet wirklich -> Pin entfernen
            unpin_daily_post_message(chat_id, topic_id)

    new_data = {
        "submissions": {},
        "votes": {},
        "contest_active": is_starting_new_contest,
        "max_votes": 0,
        "current_duel": None
    }

    # pinned_message_id NICHT in new_data übernehmen, weil wir gerade unpin gemacht haben.
    save_json(DATA_FILE, new_data)
    logging.info(f"Contest data has been reset. Contest active: {is_starting_new_contest}.")


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


# --- DUEL & WINNER ANNOUNCEMENT LOGIC ---
def announce_winners_grouped(winner_user_ids, votes, reason=""):
    cfg = get_config()
    chat_id = cfg.get("CHAT_ID")
    if not chat_id:
        return
    topic_id = get_topic_id(cfg)
    bot_data = load_json(DATA_FILE)
    submissions = bot_data.get("submissions", {})

    media = []
    winner_names = []

    for user_id in winner_user_ids:
        user_id_str = str(user_id)
        if user_id_str in submissions:
            username = submissions[user_id_str].get("username", "Unknown")
            photo_id = submissions[user_id_str]["photo_id"]
            winner_names.append(f"@{username}")
            media.append(types.InputMediaPhoto(photo_id))

    if not media:
        logging.error("No valid media found for grouped winner announcement. Skipping.")
        return

    caption = (
        f"🏆 Outfit des Tages: {', '.join(winner_names)} mit {votes} Reaktionen! "
        f"Herzlichen Glückwunsch! 🥳"
    )
    media[0].caption = caption

    try:
        bot.send_media_group(chat_id, media, message_thread_id=topic_id)
        logging.info(f"Grouped winners announced ({reason}): {', '.join(winner_names)} in chat {chat_id}.")
    except Exception as e:
        logging.error(f"Error during grouped winner announcement: {e}", exc_info=True)


def start_duel(tied_message_ids):
    logging.info(f"Starting a duel for tied message IDs: {tied_message_ids}")
    cfg = get_config()
    chat_id = cfg.get("CHAT_ID")
    topic_id = get_topic_id(cfg)
    bot_data = load_json(DATA_FILE)
    submissions = bot_data.get("submissions", {})

    if len(tied_message_ids) < 2:
        logging.error("Not enough tied messages to start a duel.")
        tied_user_ids = [
            uid for uid, s in submissions.items()
            if str(s.get("message_id")) in tied_message_ids
        ]
        if tied_user_ids:
            max_votes = bot_data.get("max_votes", 0)
            announce_winners_grouped([random.choice(tied_user_ids)], max_votes, "duel-fallback-not-enough-tied")
        reset_contest_data(is_starting_new_contest=False)
        return

    contestant_msg_ids = random.sample(tied_message_ids, 2)

    contestants = []
    for msg_id in contestant_msg_ids:
        user_id = next(
            (uid for uid, sdata in submissions.items()
             if str(sdata.get("message_id")) == msg_id),
            None
        )
        if user_id:
            contestants.append({
                "user_id": user_id,
                "username": submissions[user_id].get("username", "Unknown"),
                "photo_id": submissions[user_id].get("photo_id")
            })

    if len(contestants) != 2:
        logging.error("Could not find two valid contestants for the duel. Fallback to single winner.")
        tied_user_ids = [
            uid for uid, s in submissions.items()
            if str(s.get("message_id")) in tied_message_ids
        ]
        if tied_user_ids:
            max_votes = bot_data.get("max_votes", 0)
            announce_winners_grouped([random.choice(tied_user_ids)], max_votes, "duel-fallback-invalid-contestants")
        reset_contest_data(is_starting_new_contest=False)
        return

    c1, c2 = contestants[0], contestants[1]

    try:
        media = [
            types.InputMediaPhoto(c1['photo_id'], caption=f"Kandidat 1: @{c1['username']}"),
            types.InputMediaPhoto(c2['photo_id'], caption=f"Kandidat 2: @{c2['username']}")
        ]
        bot.send_media_group(chat_id, media, message_thread_id=topic_id)

        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton(f"👍 für @{c1['username']}", callback_data=f"duel_vote_{c1['user_id']}"),
            types.InlineKeyboardButton(f"👍 für @{c2['username']}", callback_data=f"duel_vote_{c2['user_id']}")
        )
        poll_message = bot.send_message(
            chat_id,
            "⚔️ DUEL! Wer soll gewinnen? Stimmt jetzt ab!",
            reply_markup=markup,
            message_thread_id=topic_id
        )

        duel_data = {
            "poll_message_id": poll_message.message_id,
            "contestants": {
                c1['user_id']: {'username': c1['username'], 'photo_id': c1['photo_id'], 'votes': 0},
                c2['user_id']: {'username': c2['username'], 'photo_id': c2['photo_id'], 'votes': 0}
            },
            "voters": {}
        }
        bot_data["current_duel"] = duel_data
        save_json(DATA_FILE, bot_data)

        duration = cfg.get("DUEL_DURATION_MINUTES", 60)
        end_time = datetime.now() + timedelta(minutes=duration)
        schedule.every().day.at(end_time.strftime('%H:%M')).do(end_duel).tag('duel-end')
        logging.info(f"Duel started. Scheduled to end at {end_time.strftime('%H:%M')}.")

    except Exception as e:
        logging.error(f"Failed to start duel: {e}", exc_info=True)
        tied_user_ids = [
            uid for uid, s in submissions.items()
            if str(s.get("message_id")) in tied_message_ids
        ]
        if tied_user_ids:
            max_votes = bot_data.get("max_votes", 0)
            announce_winners_grouped([random.choice(tied_user_ids)], max_votes, "duel-start-failed-fallback")
        reset_contest_data(is_starting_new_contest=False)


def end_duel():
    logging.info("Ending the duel...")
    cfg = get_config()
    chat_id = cfg.get("CHAT_ID")
    topic_id = get_topic_id(cfg)
    bot_data = load_json(DATA_FILE)
    duel_data = bot_data.get("current_duel")

    if not duel_data:
        logging.warning("end_duel called but no duel data found.")
        reset_contest_data(is_starting_new_contest=False)
        return schedule.CancelJob

    contestants = duel_data.get("contestants", {})
    max_votes = -1
    winners_user_ids = []

    for user_id, data in contestants.items():
        if data['votes'] > max_votes:
            max_votes = data['votes']
            winners_user_ids = [user_id]
        elif data['votes'] == max_votes:
            winners_user_ids.append(user_id)

    if not winners_user_ids or max_votes <= 0:
        bot.send_message(
            chat_id,
            "Das Duell endet ohne Stimmen. Es gibt keinen Gewinner.",
            message_thread_id=topic_id
        )
    else:
        announce_winners_grouped(winners_user_ids, max_votes, "duel_winner")

    # ✅ Nach dem Duell ist der Wettbewerb endgültig beendet -> reset + UNPIN passiert in reset_contest_data()
    reset_contest_data(is_starting_new_contest=False)
    logging.info("Duel ended and data has been cleaned up.")

    schedule.clear('duel-end')
    return schedule.CancelJob


# --- CORE BOT FUNCTIONS ---
def send_daily_post():
    logging.info("Attempting to send daily post...")

    # Neuen Contest starten (inkl. failsafe UNPIN alter Message)
    reset_contest_data(is_starting_new_contest=True)

    cfg = get_config()
    chat_id = cfg.get("CHAT_ID")
    if not chat_id:
        return
    topic_id = get_topic_id(cfg)

    try:
        bot_username = bot.get_me().username
        start_url = f"https://t.me/{bot_username}?start=participate"
        markup = types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("Mitmachen", url=start_url)
        )

        sent = bot.send_message(
            chat_id,
            "📸 Outfit des Tages – zeigt eure heutigen E.S-Outfits!",
            reply_markup=markup,
            message_thread_id=topic_id
        )

        # ✅ PIN genau dieser Nachricht
        pin_daily_post_message(chat_id=chat_id, message_id=sent.message_id, topic_id=topic_id)

        logging.info(f"Daily post sent to chat {chat_id} (Topic: {topic_id}) and pinned (msg_id={sent.message_id}).")
    except Exception as e:
        logging.error(f"Error sending daily post: {e}", exc_info=True)


def determine_winner():
    logging.info("Determining winner(s)....")
    cfg = get_config()
    chat_id = cfg.get("CHAT_ID")
    if not chat_id:
        return
    topic_id = get_topic_id(cfg)

    bot_data = load_json(DATA_FILE)
    if not bot_data.get("submissions"):
        bot.send_message(
            chat_id,
            "Für den heutigen Wettbewerb gab es leider keine Einreichungen.",
            message_thread_id=topic_id
        )
        # ✅ Wettbewerb endet -> reset + UNPIN
        reset_contest_data(is_starting_new_contest=False)
        return

    winner_info = {}
    max_votes = -1
    for msg_id, votes in bot_data.get("votes", {}).items():
        total_votes = len(votes)
        if total_votes > max_votes:
            max_votes = total_votes
            winner_info = {msg_id: total_votes}
        elif total_votes == max_votes:
            winner_info[msg_id] = total_votes

    bot_data["max_votes"] = max_votes
    save_json(DATA_FILE, bot_data)

    if not winner_info or max_votes <= 0:
        bot.send_message(
            chat_id,
            "Es wurden keine Stimmen abgegeben. Es gibt heute keinen Gewinner.",
            message_thread_id=topic_id
        )
        # ✅ Wettbewerb endet -> reset + UNPIN
        reset_contest_data(is_starting_new_contest=False)
        return

    tied_message_ids = list(winner_info.keys())
    submissions = bot_data.get("submissions", {})
    tied_user_ids = []
    for msg_id in tied_message_ids:
        user_id = next(
            (uid for uid, sdata in submissions.items()
             if str(sdata.get("message_id")) == msg_id),
            None
        )
        if user_id:
            tied_user_ids.append(user_id)

    # Wenn Duel startet -> Wettbewerb ist noch nicht wirklich vorbei -> Pin bleibt bis end_duel()
    if len(tied_message_ids) > 1 and cfg.get("DUEL_MODE"):
        if cfg.get("DUEL_TYPE") == "tie_breaker" and len(tied_message_ids) >= 2:
            bot.send_message(
                chat_id,
                f"Unentschieden mit {max_votes} Stimmen! Ein Duell wird gestartet...",
                message_thread_id=topic_id
            )
            start_duel(tied_message_ids)
        elif cfg.get("DUEL_TYPE") == "multiple_winners":
            bot.send_message(
                chat_id,
                f"Unentschieden mit {max_votes} Stimmen! Es gibt mehrere Gewinner!",
                message_thread_id=topic_id
            )
            announce_winners_grouped(tied_user_ids, max_votes, "multiple_winners")
            # ✅ Wettbewerb endet -> reset + UNPIN
            reset_contest_data(is_starting_new_contest=False)
        else:
            announce_winners_grouped([random.choice(tied_user_ids)], max_votes, "random_single_fallback")
            # ✅ Wettbewerb endet -> reset + UNPIN
            reset_contest_data(is_starting_new_contest=False)
    else:
        announce_winners_grouped([random.choice(tied_user_ids)], max_votes, "single_winner")
        # ✅ Wettbewerb endet -> reset + UNPIN
        reset_contest_data(is_starting_new_contest=False)


# --- TELEBOT HANDLERS ---
@bot.message_handler(commands=['start'])
def handle_start(message):
    if message.chat.type == 'private':
        args = message.text.split()
        if len(args) > 1 and args[1] == 'participate':
            bot.send_message(
                message.chat.id,
                "Hallo! Schick mir jetzt dein Outfit-Foto, um am Wettbewerb teilzunehmen."
            )
        else:
            bot.send_message(
                message.chat.id,
                "Hallo! Ich bin der Outfit-Bot. Details zum Wettbewerb findest du in der Gruppe."
            )


@bot.message_handler(commands=['start_contest', 'announce_winner', 'end_duel'])
def handle_admin_commands(message):
    # ALWAYS delete the incoming command message
    try:
        bot.delete_message(message.chat.id, message.message_id)
        logging.info(f"Admin command message deleted: {message.text} from {message.from_user.id}")
    except Exception as e:
        logging.error(f"Could not delete admin command message {message.message_id}: {e}", exc_info=True)

    logging.info(
        f"Admin command received in chat {message.chat.id}: {message.text} from user {message.from_user.id}"
    )
    cfg = get_config()
    temp_msg_duration = cfg.get("TEMPORARY_MESSAGE_DURATION_SECONDS", 30)

    if not is_admin(message.from_user.id):
        try:
            sent_message = bot.send_message(
                message.chat.id,
                "🚫 Du bist kein Administrator.",
                message_thread_id=message.message_thread_id
            )
            logging.warning(
                f"Non-admin user {message.from_user.id} tried to use admin command: {message.text}."
            )
            threading.Timer(
                temp_msg_duration,
                bot.delete_message,
                args=[sent_message.chat.id, sent_message.message_id]
            ).start()
        except Exception as e:
            logging.error(f"Could not send/delete non-admin warning: {e}", exc_info=True)
        return

    command = message.text.split()[0][1:]
    if command == "start_contest":
        send_daily_post()
        logging.info(f"Admin {message.from_user.id} manually started contest.")
    elif command == "announce_winner":
        determine_winner()
        logging.info(f"Admin {message.from_user.id} manually triggered winner announcement.")
    elif command == "end_duel":
        end_duel()
        logging.info(f"Admin {message.from_user.id} manually ended duel.")


@bot.message_handler(content_types=['photo'])
def handle_photo_submission(message):
    if message.chat.type != 'private':
        return

    bot_data = load_json(DATA_FILE)
    if not bot_data.get("contest_active", False):
        bot.send_message(
            message.chat.id,
            "Momentan läuft kein Wettbewerb oder die Einreichungsphase ist vorbei."
        )
        return

    user_id = str(message.from_user.id)
    username = message.from_user.username or message.from_user.first_name

    if user_id in bot_data.get("submissions", {}):
        bot.send_message(
            message.chat.id,
            "🚫 Du hast bereits ein Bild für diesen Wettbewerb hochgeladen."
        )
        return

    cfg = get_config()
    chat_id = cfg.get("CHAT_ID")
    topic_id = get_topic_id(cfg)
    photo_id = message.photo[-1].file_id
    caption = f"Outfit von @{username}"
    markup = generate_markup(int(user_id))

    try:
        sent_message = bot.send_photo(
            chat_id,
            photo_id,
            caption=caption,
            reply_markup=markup,
            message_thread_id=topic_id
        )

        bot_data.setdefault("submissions", {})[user_id] = {
            "message_id": sent_message.message_id,
            "photo_id": photo_id,
            "username": username
        }
        bot_data.setdefault("votes", {})[str(sent_message.message_id)] = {}
        save_json(DATA_FILE, bot_data)

        bot.send_message(
            message.chat.id,
            "✅ Dein Outfit wurde erfolgreich in der Gruppe gepostet!"
        )
    except Exception as e:
        bot.send_message(
            message.chat.id,
            "😥 Fehler beim Posten. Ist der Bot Admin in der Gruppe?"
        )
        logging.error(f"Error posting photo: {e}", exc_info=True)


@bot.callback_query_handler(
    func=lambda call: call.data.startswith('vote_') or call.data.startswith('duel_vote_')
)
def handle_vote(call):
    voter_id = str(call.from_user.id)

    if call.data.startswith('duel_vote_'):
        handle_duel_vote(call)
        return

    message_id = str(call.message.message_id)
    try:
        _, vote_type, submitter_id_str = call.data.split('_')
        submitter_id = int(submitter_id_str)
    except ValueError:
        logging.error(f"Callback Parse Error: {call.data}")
        return

    bot_data = load_json(DATA_FILE)
    votes = bot_data.get("votes", {}).get(message_id, {})

    feedback = ''
    if votes.get(voter_id) == vote_type:
        del votes[voter_id]
        feedback = f'Stimme ({vote_type}) zurückgezogen.'
    else:
        votes[voter_id] = vote_type
        feedback = f'Du hast mit {vote_type} gestimmt.'

    bot_data["votes"][message_id] = votes
    save_json(DATA_FILE, bot_data)

    counts = count_votes(votes)
    new_markup = generate_markup(submitter_id, counts['like'], counts['love'], counts['fire'])

    try:
        bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=int(message_id),
            reply_markup=new_markup
        )
    except Exception as e:
        if "message is not modified" not in str(e).lower():
            logging.error(f"Error updating buttons for Message {message_id}: {e}", exc_info=True)

    bot.answer_callback_query(call.id, feedback)


def handle_duel_vote(call):
    voter_id = str(call.from_user.id)
    voted_for_id = call.data.split('_')[2]

    bot_data = load_json(DATA_FILE)
    duel_data = bot_data.get("current_duel")
    if not duel_data:
        bot.answer_callback_query(call.id, "Diese Duell-Abstimmung ist bereits beendet.")
        return

    contestants = duel_data["contestants"]
    voters = duel_data["voters"]

    previous_vote = voters.get(voter_id)

    if previous_vote == voted_for_id:
        contestants[voted_for_id]['votes'] -= 1
        del voters[voter_id]
        feedback = "Stimme zurückgezogen."
    elif previous_vote:
        contestants[previous_vote]['votes'] -= 1
        contestants[voted_for_id]['votes'] += 1
        voters[voter_id] = voted_for_id
        feedback = "Stimme geändert."
    else:
        contestants[voted_for_id]['votes'] += 1
        voters[voter_id] = voted_for_id
        feedback = "Stimme abgegeben."

    bot_data["current_duel"] = duel_data
    save_json(DATA_FILE, bot_data)

    c1_id, c2_id = list(contestants.keys())
    c1, c2 = contestants[c1_id], contestants[c2_id]

    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton(f"👍 für @{c1['username']} ({c1['votes']})", callback_data=f"duel_vote_{c1_id}"),
        types.InlineKeyboardButton(f"👍 für @{c2['username']} ({c2['votes']})", callback_data=f"duel_vote_{c2_id}")
    )

    try:
        bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=duel_data["poll_message_id"],
            reply_markup=markup
        )
    except Exception as e:
        logging.warning(f"Could not update duel poll markup: {e}")

    bot.answer_callback_query(call.id, feedback)


# --- UNKNOWN COMMAND HANDLER ---
@bot.message_handler(
    func=lambda message: message.text and message.text.startswith('/'),
    content_types=['text']
)
def handle_unknown_command(message):
    logging.info(
        f"Unknown command received in chat {message.chat.id} from user "
        f"{message.from_user.id}: {message.text}"
    )
    try:
        bot.delete_message(message.chat.id, message.message_id)
        logging.info(f"Unknown command message deleted: {message.text} from {message.from_user.id}")

        cfg = get_config()
        temp_msg_duration = cfg.get("TEMPORARY_MESSAGE_DURATION_SECONDS", 30)
        sent_message = bot.send_message(
            message.chat.id,
            "❓ Unbekannter Befehl. Bitte überprüfe die Schreibweise.",
            message_thread_id=message.message_thread_id
        )
        threading.Timer(
            temp_msg_duration,
            bot.delete_message,
            args=[sent_message.chat.id, sent_message.message_id]
        ).start()
    except Exception as e:
        logging.error(f"Error handling unknown command: {e}", exc_info=True)


# --- SCHEDULING & COMMANDS ---
def run_scheduler():
    load_schedules()
    schedule.every(30).minutes.do(load_schedules)
    while True:
        schedule.run_pending()
        time.sleep(1)


def load_schedules():
    schedule.clear("daily")
    cfg = get_config()
    if cfg.get("AUTO_POST_ENABLED"):
        post_time = cfg.get("POST_TIME", "18:00")
        winner_time = cfg.get("WINNER_TIME", "22:00")
        schedule.every().day.at(post_time).do(send_daily_post).tag("daily")
        schedule.every().day.at(winner_time).do(determine_winner).tag("daily")


def command_listener():
    logging.info("Command listener started.")
    while True:
        try:
            if os.path.exists("command_start_contest.tmp"):
                logging.info("command_start_contest.tmp found – starting contest.")
                send_daily_post()
                os.remove("command_start_contest.tmp")

            if os.path.exists("command_announce_winner.tmp"):
                logging.info("command_announce_winner.tmp found – announcing winner.")
                determine_winner()
                os.remove("command_announce_winner.tmp")

            if os.path.exists("command_end_duel.tmp"):
                logging.info("command_end_duel.tmp found – ending duel via dashboard.")
                end_duel()
                os.remove("command_end_duel.tmp")
        except Exception as e:
            logging.error(f"Error in command listener: {e}", exc_info=True)
        time.sleep(2)


def main_polling_loop():
    while True:
        try:
            cfg = get_config()
            token = cfg.get("BOT_TOKEN")
            if token and token != "DUMMY" and token != bot.token:
                bot.token = token
                logging.info("Bot token has been updated.")

            if bot.token and bot.token != "0:dummy":
                logging.info("Outfit-Bot polling started.")
                bot.polling(none_stop=True, skip_pending=True)
                logging.info("Outfit-Bot polling stopped gracefully.")
            else:
                logging.warning("Bot token ist nicht konfiguriert. Polling ist pausiert.")
                time.sleep(10)
        except Exception as e:
            logging.error(f"Polling crash: {e}", exc_info=True)
            time.sleep(15)


if __name__ == "__main__":
    logging.info("Outfit-Bot script started.")
    threading.Thread(target=command_listener, daemon=True).start()
    threading.Thread(target=run_scheduler, daemon=True).start()
    main_polling_loop()
    logging.info("Outfit-Bot script has shut down.")
