import os
import json
import time
import random
import asyncio
import logging
import hashlib
from datetime import datetime
from telegram import Bot

# ----------------- Setup -----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

CONFIG_FILE = os.path.join(BASE_DIR, "quiz_bot_config.json")
TRIGGER_FILE = os.path.join(BASE_DIR, "command_send_random.tmp")

# Unterstütze beide Orte (falls du die Dateien verschoben hast)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
QUIZ_FILE_A = os.path.join(DATA_DIR, "quizfragen.json")          # alt
QUIZ_FILE_B = os.path.join(BASE_DIR, "quizfragen.json")          # neu (im Bot-Ordner)
USED_FILE = os.path.join(BASE_DIR, "quizfragen_gestellt.json")   # neu: gestellte Fragen

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s"
)
log = logging.getLogger("quiz_bot")


# ----------------- Helpers -----------------
def load_json(path, default):
    try:
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def pick_quiz_file():
    if os.path.exists(QUIZ_FILE_B):
        return QUIZ_FILE_B
    return QUIZ_FILE_A


def normalize_questions(raw):
    """
    Unterstützt:
      - Liste: [ {frage, optionen, antwort}, ... ]
      - Dict: { "questions": [ ... ] } oder { "fragen": [ ... ] }
    """
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        if isinstance(raw.get("questions"), list):
            return raw.get("questions", [])
        if isinstance(raw.get("fragen"), list):
            return raw.get("fragen", [])
    return []


def question_fingerprint(q: dict) -> str:
    # stabiler Hash, damit wir "gestellt" speichern können, auch ohne ID
    frage = str(q.get("frage", "")).strip()
    optionen = q.get("optionen", [])
    if not isinstance(optionen, list):
        optionen = []
    payload = frage + "||" + "||".join([str(x).strip() for x in optionen])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def safe_int(x, fallback=0):
    try:
        return int(x)
    except Exception:
        return fallback


# ----------------- Core -----------------
async def send_quiz_once():
    cfg = load_json(CONFIG_FILE, {})
    token = (cfg.get("token") or "").strip()
    chat_id = (cfg.get("channel_id") or "").strip()
    topic_id = cfg.get("topic_id")

    if not token or not chat_id:
        return False, "Config fehlt: token oder channel_id"

    quiz_file = pick_quiz_file()
    raw = load_json(quiz_file, [])
    questions = normalize_questions(raw)

    if not questions:
        return False, f"Keine Quizfragen gefunden in: {quiz_file}"

    used = load_json(USED_FILE, {"used": [], "updated_at": None})
    used_set = set(used.get("used", [])) if isinstance(used, dict) else set()

    # Filter: nur noch ungestellte Fragen
    available = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        fp = question_fingerprint(q)
        if fp not in used_set:
            available.append((fp, q))

    if not available:
        # NICHT von vorne anfangen!
        return False, "Alle Quizfragen wurden bereits gestellt (kein Reset gewünscht)."

    fp, q = random.choice(available)

    frage = str(q.get("frage", "")).strip()
    optionen = q.get("optionen", [])
    if not isinstance(optionen, list):
        optionen = []

    correct = safe_int(q.get("antwort", 0), 0)

    # Sicherheitschecks
    if not frage or len(optionen) < 2:
        # Markiere die kaputte Frage als "benutzt", damit er nicht immer wieder darauf stößt
        used_set.add(fp)
        save_json(USED_FILE, {"used": sorted(list(used_set)), "updated_at": datetime.utcnow().isoformat()})
        return False, "Ungültige Frage (leer oder <2 Optionen). Markiert als gestellt."

    if correct < 0 or correct >= len(optionen):
        correct = 0

    bot = Bot(token=token)

    message_thread_id = safe_int(topic_id, None) if str(topic_id).isdigit() else None

    await bot.send_poll(
        chat_id=chat_id,
        question=frage,
        options=[str(o) for o in optionen],
        type="quiz",
        correct_option_id=correct,
        is_anonymous=False,
        allows_multiple_answers=False,
        message_thread_id=message_thread_id,
    )

    # Als gestellt speichern
    used_set.add(fp)
    save_json(USED_FILE, {"used": sorted(list(used_set)), "updated_at": datetime.utcnow().isoformat()})

    return True, "Quiz erfolgreich gesendet."


def handle_trigger():
    if not os.path.exists(TRIGGER_FILE):
        return

    # Trigger sofort entfernen, damit Doppelklick nicht mehrfach sendet
    try:
        os.remove(TRIGGER_FILE)
    except Exception:
        pass

    try:
        ok, msg = asyncio.run(send_quiz_once())
        if ok:
            log.info(msg)
        else:
            log.warning(msg)
    except Exception as e:
        log.error(f"Unerwarteter Fehler beim Senden: {e}")


def main():
    log.info("Quiz-Bot gestartet.")
    while True:
        handle_trigger()
        time.sleep(1)


if __name__ == "__main__":
    main()
