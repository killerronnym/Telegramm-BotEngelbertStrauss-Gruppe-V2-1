import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')
import json
import time
import random
import asyncio
import logging
import hashlib
from datetime import datetime, time as dt_time, timedelta
from telegram import Bot
from telegram.error import TelegramError

# ----------------- Setup -----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))
TRIGGER_FILE = os.path.join(BASE_DIR, "send_now.tmp")
TRIGGER_FILE = os.path.join(BASE_DIR, "send_now.tmp")
STATE_FILE = os.path.join(PROJECT_ROOT, "instance", "quiz_bot_state.json")

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
QUIZ_FILE = os.path.join(DATA_DIR, "quizfragen.json")
QUIZ_FILE = os.path.join(DATA_DIR, "quizfragen.json")
USED_FILE = os.path.join(PROJECT_ROOT, "instance", "quizfragen_gestellt.json")

# Navigating to project root
sys.path.append(PROJECT_ROOT)
from shared_bot_utils import get_bot_config, is_bot_active

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(BASE_DIR, "quiz_bot.log"), encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("quiz_bot")

def load_config_from_db():
    return get_bot_config("quiz")


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

def get_last_sent_date():
    state = load_json(STATE_FILE, {})
    date_str = state.get("last_sent_date")
    if date_str:
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return None
    return None

def set_last_sent_date(date_obj):
    state = load_json(STATE_FILE, {})
    state["last_sent_date"] = date_obj.strftime("%Y-%m-%d")
    save_json(STATE_FILE, state)

def question_fingerprint(q: dict) -> str:
    frage = str(q.get("frage", "")).strip()
    optionen = q.get("optionen", [])
    if not isinstance(optionen, list):
        optionen = []
    payload = frage + "||" + "||".join([str(x).strip() for x in sorted(optionen)])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()

# ----------------- Core Logic -----------------
async def send_quiz(context=None):
    if not is_bot_active('quiz'):
        log.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Quiz Bot ist inaktiv. Abbruch.")
        return False
        
    log.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Attempting to send quiz...")
    cfg = load_config_from_db()
    token = cfg.get("bot_token", "").strip()
    chat_id = cfg.get("channel_id", "").strip() # Can be channel or group ID
    topic_id = cfg.get("topic_id", "")

    if not token or not chat_id:
        log.warning(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Bot token or channel_id is not configured.")
        return False

    all_questions = load_json(QUIZ_FILE, [])
    if not all_questions:
        log.error(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] No questions found in quizfragen.json")
        return False

    used_hashes = set(load_json(USED_FILE, []))
    available_questions = [q for q in all_questions if question_fingerprint(q) not in used_hashes]

    if not available_questions:
        log.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] All questions have been asked. Resetting history.")
        used_hashes = set()
        save_json(USED_FILE, [])
        available_questions = all_questions

    # Select random question
    question_data = random.choice(available_questions)
    
    frage = question_data.get("frage", "").strip()
    optionen = question_data.get("optionen", [])
    antwort_idx = int(question_data.get("antwort", 0))

    # --- Validation for Telegram API Limits ---
    if len(frage) > 300:
        log.warning(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Question too long ({len(frage)} chars). Skipping.")
        return False
    
    if len(optionen) < 2 or len(optionen) > 10:
        log.warning(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Invalid number of options ({len(optionen)}). Skipping.")
        return False
        
    for opt in optionen:
        if len(str(opt)) > 100:
             log.warning(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Option too long ({len(str(opt))} chars). Skipping.")
             return False

    if antwort_idx < 0 or antwort_idx >= len(optionen):
        log.warning(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Invalid correct option index {antwort_idx}. Skipping.")
        return False

    try:
        bot = Bot(token=token)
        
        # Handle Topic ID
        message_thread_id = None
        if topic_id and str(topic_id).strip().lower() != "null":
             if str(topic_id).isdigit():
                 message_thread_id = int(topic_id)
        
        log.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Sending quiz to {chat_id} (Topic: {message_thread_id}): {frage}")
        
        await bot.send_poll(
            chat_id=chat_id,
            question=frage,
            options=optionen,
            type='quiz',
            correct_option_id=antwort_idx,
            is_anonymous=False, # Quiz is usually not anonymous to show winners, but configurable? Standard: False
            message_thread_id=message_thread_id
        )
        
        # Mark as used
        used_hashes.add(question_fingerprint(question_data))
        save_json(USED_FILE, list(used_hashes))
        
        log.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Quiz sent successfully.")
        return True

    except TelegramError as e:
        log.error(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Telegram API Error: {e}")
        return False
    except Exception as e:
        log.error(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Unexpected error sending quiz: {e}")
        return False

# ----------------- Scheduler and Trigger -----------------
async def process_trigger(context=None):
    if not is_bot_active('quiz'): return
    if os.path.exists(TRIGGER_FILE):
        log.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Manual trigger detected.")
        try:
            os.remove(TRIGGER_FILE)
            await send_quiz()
        except Exception as e:
            log.error(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Error processing trigger: {e}")

async def check_schedule():
    cfg = load_config_from_db()
    schedule = cfg.get("schedule", {})
    
    if not schedule.get("enabled"):
        return

    time_str = schedule.get("time")
    if not time_str: return

    try:
        scheduled_time = datetime.strptime(time_str, "%H:%M").time()
    except ValueError:
        log.error(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Invalid schedule time format: {time_str}")
        return

    now = datetime.now()
    today_date = now.date()
    
    # Check if already sent today
    last_sent = get_last_sent_date()
    if last_sent == today_date:
        return

    # Check correct day of week
    allowed_days = schedule.get("days", [])
    if now.weekday() not in allowed_days:
        return

    # Check if time is reached (with 1 minute tolerance to avoid double send in same minute if loop is fast)
    # Actually, since we check last_sent_date, we just need to know if current time >= scheduled time
    if now.time() >= scheduled_time:
        log.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Scheduled time reached. Sending quiz...")
        success = await send_quiz()
        if success:
            set_last_sent_date(today_date)
            log.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Schedule marked as done for {today_date}")

async def check_schedule_job(context=None):
    if not is_bot_active('quiz'): return
    await check_schedule()

# ----------------- Master Bot Setup -----------------
def setup_jobs(job_queue):
    log.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Quiz Bot registriert Jobs...")
    # Trigger-Check alle 10 Sekunden
    job_queue.run_repeating(process_trigger, interval=10)
    # Schedule-Check minutlich
    job_queue.run_repeating(check_schedule_job, interval=60)

if __name__ == "__main__":
    print("Bitte starte den Bot über main_bot.py")
