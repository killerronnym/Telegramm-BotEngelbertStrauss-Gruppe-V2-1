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

CONFIG_FILE = os.path.join(BASE_DIR, "umfrage_bot_config.json")
TRIGGER_FILE = os.path.join(BASE_DIR, "command_send_random.tmp")

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
POLL_FILE_A = os.path.join(DATA_DIR, "umfragen.json")            # alt
POLL_FILE_B = os.path.join(BASE_DIR, "umfragen.json")            # neu (im Bot-Ordner)
USED_FILE = os.path.join(BASE_DIR, "umfragen_gestellt.json")     # neu: gestellte Umfragen

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s"
)
log = logging.getLogger("umfrage_bot")


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


def pick_poll_file():
    if os.path.exists(POLL_FILE_B):
        return POLL_FILE_B
    return POLL_FILE_A


def normalize_polls(raw):
    """
    Unterstützt:
      - Liste: [ {frage, optionen}, ... ]
      - Dict: { "polls": [ ... ] } oder { "umfragen": [ ... ] }
    """
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        if isinstance(raw.get("polls"), list):
            return raw.get("polls", [])
        if isinstance(raw.get("umfragen"), list):
            return raw.get("umfragen", [])
    return []


def poll_fingerprint(p: dict) -> str:
    frage = str(p.get("frage", "")).strip()
    optionen = p.get("optionen", [])
    if not isinstance(optionen, list):
        optionen = []
    payload = frage + "||" + "||".join([str(x).strip() for x in optionen])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def safe_int(x, fallback=None):
    try:
        return int(x)
    except Exception:
        return fallback


# ----------------- Core -----------------
async def send_poll_once():
    cfg = load_json(CONFIG_FILE, {})
    token = (cfg.get("token") or "").strip()
    chat_id = (cfg.get("channel_id") or "").strip()
    topic_id = cfg.get("topic_id")

    if not token or not chat_id:
        return False, "Config fehlt: token oder channel_id"

    poll_file = pick_poll_file()
    raw = load_json(poll_file, [])
    polls = normalize_polls(raw)

    if not polls:
        return False, f"Keine Umfragen gefunden in: {poll_file}"

    used = load_json(USED_FILE, {"used": [], "updated_at": None})
    used_set = set(used.get("used", [])) if isinstance(used, dict) else set()

    available = []
    for p in polls:
        if not isinstance(p, dict):
            continue
        fp = poll_fingerprint(p)
        if fp not in used_set:
            available.append((fp, p))

    if not available:
        return False, "Alle Umfragen wurden bereits gestellt (kein Reset gewünscht)."

    fp, p = random.choice(available)

    frage = str(p.get("frage", "")).strip()
    optionen = p.get("optionen", [])
    if not isinstance(optionen, list):
        optionen = []

    if not frage or len(optionen) < 2:
        used_set.add(fp)
        save_json(USED_FILE, {"used": sorted(list(used_set)), "updated_at": datetime.utcnow().isoformat()})
        return False, "Ungültige Umfrage (leer oder <2 Optionen). Markiert als gestellt."

    bot = Bot(token=token)
    message_thread_id = safe_int(topic_id, None) if str(topic_id).isdigit() else None

    await bot.send_poll(
        chat_id=chat_id,
        question=frage,
        options=[str(o) for o in optionen],
        is_anonymous=False,
        allows_multiple_answers=False,
        message_thread_id=message_thread_id,
    )

    used_set.add(fp)
    save_json(USED_FILE, {"used": sorted(list(used_set)), "updated_at": datetime.utcnow().isoformat()})

    return True, "Umfrage erfolgreich gesendet."


def handle_trigger():
    if not os.path.exists(TRIGGER_FILE):
        return

    try:
        os.remove(TRIGGER_FILE)
    except Exception:
        pass

    try:
        ok, msg = asyncio.run(send_poll_once())
        if ok:
            log.info(msg)
        else:
            log.warning(msg)
    except Exception as e:
        log.error(f"Unerwarteter Fehler beim Senden: {e}")


def main():
    log.info("Umfrage-Bot gestartet.")
    while True:
        handle_trigger()
        time.sleep(1)


if __name__ == "__main__":
    main()
