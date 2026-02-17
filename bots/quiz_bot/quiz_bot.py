import os
import json
import time
import random
import asyncio
import logging
import hashlib
from datetime import datetime, time as dt_time
from telegram import Bot

# ----------------- Setup -----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR)) # Navigate up to the project root

CONFIG_FILE = os.path.join(BASE_DIR, "quiz_bot_config.json")
TRIGGER_FILE = os.path.join(BASE_DIR, "send_now.tmp") # Corrected trigger file name

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
QUIZ_FILE = os.path.join(DATA_DIR, "quizfragen.json")
USED_FILE = os.path.join(BASE_DIR, "quizfragen_gestellt.json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(BASE_DIR, "quiz_bot.log")),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("quiz_bot")


# ----------------- Helpers -----------------
def load_json(path, default):
    try:
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.error(f"Error loading JSON from {path}: {e}")
        return default

def save_json(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log.error(f"Error saving JSON to {path}: {e}")

def question_fingerprint(q: dict) -> str:
    frage = str(q.get("frage", "")).strip()
    optionen = q.get("optionen", [])
    if not isinstance(optionen, list):
        optionen = []
    payload = frage + "||" + "||".join([str(x).strip() for x in sorted(optionen)])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()

# ----------------- Core Logic -----------------
async def send_quiz():
    cfg = load_json(CONFIG_FILE, {})
    token = cfg.get("bot_token", "").strip()
    chat_id = cfg.get("channel_id", "").strip()
    topic_id = cfg.get("topic_id", "").strip()

    if not token or not chat_id:
        log.warning("Bot token or channel_id is not configured.")
        return False, "Konfiguration (Token/Channel ID) fehlt."

    questions = load_json(QUIZ_FILE, [])
    if not questions:
        return False, "Keine Quizfragen in 'data/quizfragen.json' gefunden."

    used_hashes = set(load_json(USED_FILE, []))
    available_questions = [q for q in questions if question_fingerprint(q) not in used_hashes]

    if not available_questions:
        log.info("All quiz questions have been sent. Resetting the list.")
        # Optional: Reset used questions if all have been sent
        # used_hashes = set()
        # save_json(USED_FILE, [])
        # available_questions = questions
        return False, "Alle Quizfragen wurden bereits gestellt."

    question_data = random.choice(available_questions)
    
    frage = question_data.get("frage", "").strip()
    optionen = question_data.get("optionen", [])
    antwort = question_data.get("antwort", 0)

    if not frage or len(optionen) < 2:
        log.warning(f"Skipping invalid question: {question_data}")
        return False, "Ungültige Frage übersprungen."

    try:
        bot = Bot(token=token)
        message_thread_id = int(topic_id) if topic_id and topic_id.isdigit() else None
        
        await bot.send_poll(
            chat_id=chat_id,
            question=frage,
            options=optionen,
            is_anonymous=False,
            type='quiz',
            correct_option_id=antwort,
            message_thread_id=message_thread_id
        )
        log.info(f"Successfully sent quiz: {frage}")
        
        # Mark as used
        used_hashes.add(question_fingerprint(question_data))
        save_json(USED_FILE, list(used_hashes))
        
        return True, "Quiz erfolgreich gesendet."
    except Exception as e:
        log.error(f"Failed to send quiz: {e}")
        return False, f"Fehler beim Senden: {e}"

# ----------------- Scheduler and Trigger -----------------
def check_triggers():
    if os.path.exists(TRIGGER_FILE):
        log.info("'send_now.tmp' trigger detected.")
        try:
            os.remove(TRIGGER_FILE)
            asyncio.run(send_quiz())
        except Exception as e:
            log.error(f"Error processing trigger file: {e}")

def check_schedule(last_sent_date):
    cfg = load_json(CONFIG_FILE, {})
    schedule = cfg.get("schedule", {})
    
    if not schedule.get("enabled"):
        return False

    now = datetime.now()
    today = now.date()
    
    # Avoid sending more than once a day
    if last_sent_date == today:
        return False

    scheduled_time_str = schedule.get("time")
    if not scheduled_time_str:
        return False

    try:
        scheduled_time = dt_time.fromisoformat(scheduled_time_str)
    except ValueError:
        log.error(f"Invalid time format in schedule: {scheduled_time_str}")
        return False

    scheduled_days = schedule.get("days", [])
    
    # Check if today is a scheduled day and the time is right
    if now.weekday() in scheduled_days and now.time() >= scheduled_time:
        log.info(f"Scheduled time reached for today. Sending quiz.")
        asyncio.run(send_quiz())
        return True # Indicates that a quiz was sent

    return False

# ----------------- Main Loop -----------------
def main():
    log.info("Quiz Bot started.")
    last_sent_date = None
    
    while True:
        check_triggers()
        
        if check_schedule(last_sent_date):
            last_sent_date = datetime.now().date()

        time.sleep(10) # Check every 10 seconds

if __name__ == "__main__":
    main()
