import os
import json
import logging
from logging.handlers import RotatingFileHandler
import atexit
import subprocess
import sys
import shutil
import signal
import re
import threading
import time
import socket
from datetime import datetime, timedelta
from collections import defaultdict, deque
import io

# ✅ Telegram Proxy Cache
import hashlib
import mimetypes
import urllib.parse
import urllib.request
import urllib.error

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

from flask import (
    Flask, render_template, request, flash, redirect, url_for, jsonify, render_template_string, send_file, abort, session
)
from jinja2 import TemplateNotFound
from werkzeug.security import generate_password_hash, check_password_hash
import uuid

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s", handlers=[RotatingFileHandler("app.log", maxBytes=10240, backupCount=5), logging.StreamHandler(sys.stdout)], force=True)
log = logging.getLogger(__name__)

CRITICAL_ERRORS_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "critical_errors.log")
critical_errors_handler = RotatingFileHandler(CRITICAL_ERRORS_LOG_FILE, maxBytes=10240, backupCount=2)
critical_errors_handler.setLevel(logging.ERROR)
critical_errors_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"))
logging.getLogger().addHandler(critical_errors_handler)

app = Flask(__name__, template_folder="src")
app.secret_key = "b13f172933b9a1274adb024d47fc7552d2e85864693cb9a2"
app.config["TEMPLATES_AUTO_RELOAD"] = True

# --- Format Filter ---
def format_datetime(value, format="%d.%m.%Y %H:%M:%S"):
    if value is None: return ""
    if isinstance(value, str):
        if not value.strip(): return ""
        try: dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except: return value
    else: dt = value
    if ZoneInfo: dt = dt.astimezone(ZoneInfo("Europe/Berlin"))
    return dt.strftime(format)
app.jinja_env.filters['datetimeformat'] = format_datetime

# --- Pfade ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
BOTS_DIR = os.path.join(PROJECT_ROOT, "bots")

VENV_PYTHON = os.path.join(PROJECT_ROOT, ".venv", "bin", "python3")
if not os.path.exists(VENV_PYTHON): VENV_PYTHON = sys.executable

TOPIC_REGISTRY_FILE = os.path.join(DATA_DIR, "topic_registry.json")
ACTIVITY_LOG_FILE = os.path.join(DATA_DIR, "activity_log.jsonl")
USER_MESSAGE_DIR = os.path.join(DATA_DIR, "user_messages")
ID_FINDER_CONFIG_FILE = os.path.join(BOTS_DIR, "id_finder_bot", "id_finder_config.json")
MODERATION_CONFIG_FILE = os.path.join(DATA_DIR, "moderation_config.json")
MODERATION_DATA_FILE = os.path.join(DATA_DIR, "moderation_data.json") # For warnings
PENDING_DELETIONS_FILE = os.path.join(DATA_DIR, "pending_deletions.json")
ADMINS_FILE = os.path.join(BASE_DIR, "admins.json")
USERS_FILE = os.path.join(BASE_DIR, "users.json")
BROADCAST_DATA_FILE = os.path.join(DATA_DIR, "scheduled_broadcasts.json")
USER_REGISTRY_FILE = os.path.join(DATA_DIR, "user_registry.json")
TOPIC_CONFIG_FILE = os.path.join(BASE_DIR, "topic_config.json")
MINECRAFT_STATUS_CONFIG_FILE = os.path.join(DATA_DIR, "minecraft_status_config.json")
MINECRAFT_STATUS_CACHE_FILE = os.path.join(DATA_DIR, "minecraft_status_cache.json")
QUIZ_BOT_CONFIG_FILE = os.path.join(BOTS_DIR, "quiz_bot", "quiz_bot_config.json")
UMFRAGE_BOT_CONFIG_FILE = os.path.join(BOTS_DIR, "umfrage_bot", "umfrage_bot_config.json")
INVITE_BOT_CONFIG_FILE = os.path.join(BOTS_DIR, "invite_bot", "invite_bot_config.json")
OUTFIT_BOT_CONFIG_FILE = os.path.join(BOTS_DIR, "outfit_bot", "outfit_bot_config.json")
OUTFIT_BOT_DATA_FILE = os.path.join(BOTS_DIR, "outfit_bot", "outfit_bot_data.json")
OUTFIT_BOT_LOG_FILE = os.path.join(BOTS_DIR, "outfit_bot", "outfit_bot.log")

MATCH_CONFIG = {
    "quiz": {"pattern": "quiz_bot.py", "script": os.path.join(BOTS_DIR, "quiz_bot", "quiz_bot.py"), "log": os.path.join(BOTS_DIR, "quiz_bot", "quiz_bot.log")},
    "umfrage": {"pattern": "umfrage_bot.py", "script": os.path.join(BOTS_DIR, "umfrage_bot", "umfrage_bot.py"), "log": os.path.join(BOTS_DIR, "umfrage_bot", "umfrage_bot.log")},
    "outfit": {"pattern": "outfit_bot.py", "script": os.path.join(BOTS_DIR, "outfit_bot", "outfit_bot.py"), "log": os.path.join(BOTS_DIR, "outfit_bot", "outfit_bot.log")},
    "invite": {"pattern": "invite_bot.py", "script": os.path.join(BOTS_DIR, "invite_bot", "invite_bot.py"), "log": os.path.join(BOTS_DIR, "invite_bot", "invite_bot.log")},
    "id_finder": {"pattern": "id_finder_bot.py", "script": os.path.join(BOTS_DIR, "id_finder_bot", "id_finder_bot.py"), "log": os.path.join(BOTS_DIR, "id_finder_bot", "id_finder_bot.log")},
    "minecraft": {"pattern": "minecraft_bridge.py", "script": os.path.join(BOTS_DIR, "id_finder_bot", "minecraft_bridge.py"), "log": os.path.join(BOTS_DIR, "id_finder_bot", "minecraft_bridge.log")},
}

def get_bot_status():
    output = subprocess.run(["ps", "aux"], stdout=subprocess.PIPE, text=True, check=False).stdout
    return {k: {"running": cfg["pattern"] in output} for k, cfg in MATCH_CONFIG.items()}

@app.context_processor
def inject_globals():
    return {"bot_status": get_bot_status()}

# --- Helpers ---
def load_json(path, default=None):
    if not os.path.exists(path): return default if default is not None else {}
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except: return default if default is not None else {}

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f: json.dump(data, f, indent=4, ensure_ascii=False)

def tg_api_call(method, params):
    cfg = load_json(ID_FINDER_CONFIG_FILE)
    token = cfg.get("bot_token")
    if not token: return None
    try:
        url = f"https://api.telegram.org/bot{token}/{method}"
        data = urllib.parse.urlencode(params).encode("utf-8")
        with urllib.request.urlopen(urllib.request.Request(url, data=data)) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        log.error(f"TG API Error: {e}")
        return None

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session: session["user"], session["role"] = "admin", "admin"
        return f(*args, **kwargs)
    return decorated_function

# --- Delayed Message Deletion ---
def delete_message_after_delay(chat_id, message_id, delay):
    if delay <= 0: return
    def _delayed_delete():
        time.sleep(delay)
        tg_api_call("deleteMessage", {"chat_id": chat_id, "message_id": message_id})
    threading.Thread(target=_delayed_delete, daemon=True).start()

# --- ROUTES ---

@app.route("/")
@login_required
def index():
    return render_template("index.html")

@app.route('/live_moderation')
@login_required
def live_moderation():
    topic_config = load_json(TOPIC_CONFIG_FILE, {}).get("topics", {})
    topics_data = load_json(TOPIC_REGISTRY_FILE)
    mod_data = load_json(MODERATION_DATA_FILE, {})
    deleted_message_ids = set(mod_data.get("deleted_messages", []))

    for chat_id, chat_data in topics_data.items():
        if "topics" in chat_data:
            for topic_id, topic_name in chat_data["topics"].items():
                custom_topic = topic_config.get(topic_id)
                if custom_topic:
                    chat_data["topics"][topic_id] = f"{custom_topic['emoji']} {custom_topic['name']}"

    mod_config = load_json(MODERATION_CONFIG_FILE, {
        'max_warnings': 3, 
        'warning_text': 'Hallo {user}, deine Nachricht in der Gruppe {group} wurde entfernt. Grund: {reason}. Dies ist deine {warn_count} von {max_warnings} Verwarnungen.',
        'public_delete_notice_text': 'Die Nachricht von {user} wurde gelöscht. Grund: {reason}',
        'public_delete_notice_duration': 60
    })
    selected_chat_id = request.args.get("chat_id")
    selected_topic_id = request.args.get("topic_id")
    messages = []
    if os.path.exists(ACTIVITY_LOG_FILE):
        with open(ACTIVITY_LOG_FILE, "r", encoding="utf-8") as f:
            lines = deque(f, maxlen=500)
            for line in lines:
                try:
                    m = json.loads(line)
                    if selected_chat_id and str(m.get("chat_id")) != str(selected_chat_id): continue
                    if selected_topic_id and selected_topic_id != "all" and str(m.get("thread_id")) != str(selected_topic_id): continue
                    
                    # Mark message as deleted
                    msg_uid = f"{m.get('chat_id')}_{m.get('message_id')}"
                    if msg_uid in deleted_message_ids:
                        m['is_deleted'] = True

                    messages.append(m)
                except: continue
    messages.reverse()
    return render_template('live_moderation.html', 
                           topics=topics_data, 
                           messages=messages, 
                           selected_chat_id=selected_chat_id, 
                           selected_topic_id=selected_topic_id, 
                           mod_config=mod_config)

@app.route('/live_moderation/config', methods=['POST'])
@login_required
def live_moderation_config():
    mod_config = {
        'max_warnings': int(request.form.get('max_warnings', 3)),
        'warning_text': request.form.get('warning_text', 'Hallo {user}, deine Nachricht in der Gruppe {group} wurde entfernt. Grund: {reason}. Dies ist deine {warn_count} von {max_warnings} Verwarnungen.'),
        'public_delete_notice_text': request.form.get('public_delete_notice_text', 'Die Nachricht von {user} wurde gelöscht. Grund: {reason}'),
        'public_delete_notice_duration': int(request.form.get('public_delete_notice_duration', 60))
    }
    save_json(MODERATION_CONFIG_FILE, mod_config)
    flash('Die Moderations-Einstellungen wurden gespeichert.', 'success')
    return redirect(url_for('live_moderation'))

@app.route('/live_moderation/delete', methods=['POST'])
@login_required
def live_moderation_delete():
    user_id_str = request.form.get("user_id")
    chat_id = request.form.get("chat_id")
    message_id = request.form.get("message_id")
    topic_id = request.form.get("topic_id")
    action = request.form.get("action")
    user_name = request.form.get("user_name")
    chat_name = request.form.get("chat_name")

    # Get reason
    reason_preset = request.form.get("reason_preset")
    if reason_preset == 'other':
        reason = request.form.get("reason_custom", "Kein Grund angegeben.")
    else:
        reason = reason_preset or "Kein Grund angegeben."

    # Log deletion
    mod_data = load_json(MODERATION_DATA_FILE, {})
    deleted_ids = mod_data.get("deleted_messages", [])
    msg_uid = f"{chat_id}_{message_id}"
    if msg_uid not in deleted_ids:
        deleted_ids.append(msg_uid)
    mod_data["deleted_messages"] = deleted_ids
    save_json(MODERATION_DATA_FILE, mod_data)

    # 1. Delete original message
    tg_api_call("deleteMessage", {"chat_id": chat_id, "message_id": message_id})

    mod_config = load_json(MODERATION_CONFIG_FILE)
    
    # 2. Public Notice in Topic
    public_text_template = mod_config.get("public_delete_notice_text", "Die Nachricht von {user} wurde gelöscht. Grund: {reason}")
    public_text = public_text_template.format(user=user_name, group=chat_name, reason=reason)
    
    send_params = {"chat_id": chat_id, "text": public_text}
    if topic_id: send_params["message_thread_id"] = topic_id
    
    resp = tg_api_call("sendMessage", send_params)
    if resp and resp.get("ok"):
        new_msg_id = resp["result"]["message_id"]
        duration = int(mod_config.get("public_delete_notice_duration", 60))
        if duration > 0:
            delete_message_after_delay(chat_id, new_msg_id, duration)

    if action == "warn":
        user_warnings = mod_data.get("users", {}).get(user_id_str, {"warnings": []})
        warning_entry = {
            "reason": reason, "timestamp": datetime.now().isoformat(), "chat_id": chat_id,
            "chat_name": chat_name, "message_id": message_id
        }
        user_warnings["warnings"].append(warning_entry)
        if "users" not in mod_data: mod_data["users"] = {}
        mod_data["users"][user_id_str] = user_warnings
        save_json(MODERATION_DATA_FILE, mod_data)

        max_warnings = mod_config.get("max_warnings", 3)
        warn_count = len(user_warnings["warnings"])

        if warn_count >= max_warnings:
            tg_api_call("banChatMember", {"chat_id": chat_id, "user_id": user_id_str})
            flash(f"Nutzer {user_name} hat die maximale Anzahl an Verwarnungen erreicht und wurde gebannt.", "danger")
        else:
            warning_text_template = mod_config.get("warning_text")
            warning_text = warning_text_template.format(user=user_name, group=chat_name, reason=reason, warn_count=warn_count, max_warnings=max_warnings)
            tg_api_call("sendMessage", {"chat_id": user_id_str, "text": warning_text})
            flash(f"Nachricht gelöscht und Nutzer {user_name} verwarnt ({warn_count}/{max_warnings}).", "success")
    else:
        flash("Nachricht gelöscht.", "info")

    return redirect(request.referrer or url_for("live_moderation"))

@app.route('/user/<user_id>')
@login_required
def user_detail(user_id):
    mod_data = load_json(MODERATION_DATA_FILE, {"users": {}})
    user_registry = load_json(USER_REGISTRY_FILE, {})
    user_info = user_registry.get(str(user_id), {})
    user_warnings = mod_data.get("users", {}).get(str(user_id), {}).get("warnings", [])
    user_details = {
        'user_id': user_id,
        'full_name': user_info.get('full_name', 'Unbekannt'),
        'username': user_info.get('username', ''),
    }
    return render_template('id_finder_user_detail.html', user=user_details, warnings=user_warnings)
    
@app.route("/bot-action/<bot_name>/<action>", methods=["POST"])
@login_required
def bot_action_route(bot_name, action):
    cfg = MATCH_CONFIG[bot_name]
    if action == "start":
        log_f = open(cfg["log"], "a", encoding="utf-8")
        subprocess.Popen([VENV_PYTHON, cfg["script"]], cwd=os.path.dirname(cfg["script"]), stdout=log_f, stderr=subprocess.STDOUT, text=True, bufsize=1)
        flash("Bot gestartet.", "success")
    elif action == "stop":
        subprocess.run(["pkill", "-f", cfg["pattern"]])
        flash("Bot gestoppt.", "info")
    return redirect(request.referrer or url_for("index"))

@app.route("/tg/avatar/<user_id>")
def tg_avatar_proxy(user_id):
    for f in ["avatars", "tg_cache/avatars"]:
        p = os.path.join(DATA_DIR, f, f"{user_id}.jpg")
        if os.path.exists(p): return send_file(p)
    return abort(404)

@app.route('/tg/media/<file_id>')
def tg_media_proxy(file_id):
    token = load_json(ID_FINDER_CONFIG_FILE).get("bot_token")
    if not token: return abort(500, "Bot-Token nicht konfiguriert.")
    try:
        get_file_url = f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}"
        with urllib.request.urlopen(get_file_url) as r:
            if r.status != 200:
                log.error(f"Telegram getFile API Fehler: Status {r.status}")
                return abort(500)
            file_info = json.loads(r.read().decode())
            if not file_info.get("ok"):
                log.error(f"Telegram getFile API Fehler: {file_info.get('description')}")
                return abort(500)
            file_path = file_info['result']['file_path']
        file_download_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
        with urllib.request.urlopen(file_download_url) as r:
            if r.status != 200:
                log.error(f"Telegram file download Fehler: Status {r.status}")
                return abort(500)
            file_bytes = r.read()
            mimetype = r.info().get_content_type()
            return send_file(io.BytesIO(file_bytes), mimetype=mimetype)
    except urllib.error.URLError as e:
        log.error(f"URL-Fehler beim Abrufen von Telegram-Medien: {e}")
        return abort(502)
    except Exception as e:
        log.error(f"Allgemeiner Fehler beim Proxying von Telegram-Medien: {e}")
        return abort(500)

@app.route("/id-finder")
@login_required
def id_finder_dashboard():
    return render_template("id_finder_dashboard.html", config=load_json(ID_FINDER_CONFIG_FILE))

@app.route("/broadcast")
@login_required
def broadcast_manager():
    return render_template("broadcast_manager.html", broadcasts=load_json(BROADCAST_DATA_FILE, []), known_topics=load_json(TOPIC_REGISTRY_FILE, {}))

@app.route("/bot-settings")
@login_required
def bot_settings():
    return render_template("bot_settings.html", config=load_json(INVITE_BOT_CONFIG_FILE))

@app.route("/quiz-settings", methods=["GET", "POST"])
@login_required
def quiz_settings():
    QUIZ_QUESTIONS_FILE = os.path.join(DATA_DIR, "quizfragen.json")
    QUIZ_ASKED_FILE = os.path.join(BOTS_DIR, "quiz_bot", "quizfragen_gestellt.json")
    
    if request.method == "POST":
        action = request.form.get("action")
        if action == "save_settings":
            cfg = load_json(QUIZ_BOT_CONFIG_FILE)
            cfg["bot_token"] = request.form.get("token")
            cfg["channel_id"] = request.form.get("channel_id")
            cfg["topic_id"] = request.form.get("topic_id")
            save_json(QUIZ_BOT_CONFIG_FILE, cfg)
            flash("Quiz-Konfiguration gespeichert.", "success")
        elif action == "save_schedule":
            cfg = load_json(QUIZ_BOT_CONFIG_FILE)
            sch = cfg.setdefault("schedule", {})
            sch["enabled"] = "schedule_enabled" in request.form
            sch["time"] = request.form.get("schedule_time")
            sch["days"] = [int(x) for x in request.form.getlist("schedule_days")]
            save_json(QUIZ_BOT_CONFIG_FILE, cfg)
            flash("Zeitplan gespeichert.", "success")
        elif action == "save_questions":
            try:
                data = json.loads(request.form.get("questions_json"))
                save_json(QUIZ_QUESTIONS_FILE, data)
                flash("Fragen gespeichert.", "success")
            except Exception as e: flash(f"Fehler beim Speichern der Fragen: {e}", "danger")
        elif action == "save_asked_questions":
            try:
                data = json.loads(request.form.get("asked_questions_json"))
                save_json(QUIZ_ASKED_FILE, data)
                flash("Protokoll gespeichert.", "success")
            except Exception as e: flash(f"Fehler beim Speichern des Protokolls: {e}", "danger")
        return redirect(url_for("quiz_settings"))

    config = load_json(QUIZ_BOT_CONFIG_FILE)
    questions = load_json(QUIZ_QUESTIONS_FILE, [])
    asked = load_json(QUIZ_ASKED_FILE, [])
    logs = []
    if os.path.exists(MATCH_CONFIG["quiz"]["log"]):
        with open(MATCH_CONFIG["quiz"]["log"], "r", encoding="utf-8") as f: logs = f.readlines()[-50:]
        
    return render_template("quiz_settings.html", 
                           config=config, 
                           schedule=config.get("schedule", {}),
                           stats={"total": len(questions) + len(asked), "asked": len(asked), "remaining": len(questions)},
                           questions_json=json.dumps(questions, indent=4, ensure_ascii=False),
                           asked_questions_json=json.dumps(asked, indent=4, ensure_ascii=False),
                           logs=logs)

@app.route("/umfrage-settings", methods=["GET", "POST"])
@login_required
def umfrage_settings():
    UMFRAGE_DATA_FILE = os.path.join(DATA_DIR, "umfragen.json")
    UMFRAGE_ASKED_FILE = os.path.join(BOTS_DIR, "umfrage_bot", "umfragen_gestellt.json")
    
    if request.method == "POST":
        action = request.form.get("action")
        if action == "save_settings":
            cfg = load_json(UMFRAGE_BOT_CONFIG_FILE)
            cfg["bot_token"] = request.form.get("token")
            cfg["channel_id"] = request.form.get("channel_id")
            cfg["topic_id"] = request.form.get("topic_id")
            save_json(UMFRAGE_BOT_CONFIG_FILE, cfg)
            flash("Umfrage-Konfiguration gespeichert.", "success")
        elif action == "save_schedule":
            cfg = load_json(UMFRAGE_BOT_CONFIG_FILE)
            sch = cfg.setdefault("schedule", {})
            sch["enabled"] = "schedule_enabled" in request.form
            sch["time"] = request.form.get("schedule_time")
            sch["days"] = [int(x) for x in request.form.getlist("schedule_days")]
            save_json(UMFRAGE_BOT_CONFIG_FILE, cfg)
            flash("Zeitplan gespeichert.", "success")
        elif action == "save_umfragen":
            try:
                data = json.loads(request.form.get("umfragen_json"))
                save_json(UMFRAGE_DATA_FILE, data)
                flash("Umfragen gespeichert.", "success")
            except Exception as e: flash(f"Fehler beim Speichern der Umfragen: {e}", "danger")
        elif action == "save_asked_umfragen":
            try:
                data = json.loads(request.form.get("asked_umfragen_json"))
                save_json(UMFRAGE_ASKED_FILE, data)
                flash("Protokoll gespeichert.", "success")
            except Exception as e: flash(f"Fehler beim Speichern des Protokolls: {e}", "danger")
        return redirect(url_for("umfrage_settings"))

    config = load_json(UMFRAGE_BOT_CONFIG_FILE)
    umfragen = load_json(UMFRAGE_DATA_FILE, [])
    asked = load_json(UMFRAGE_ASKED_FILE, [])
    logs = []
    if os.path.exists(MATCH_CONFIG["umfrage"]["log"]):
        with open(MATCH_CONFIG["umfrage"]["log"], "r", encoding="utf-8") as f: logs = f.readlines()[-50:]
        
    return render_template("umfrage_settings.html", 
                           config=config, 
                           schedule=config.get("schedule", {}),
                           stats={"total": len(umfragen) + len(asked), "asked": len(asked), "remaining": len(umfragen)},
                           umfragen_json=json.dumps(umfragen, indent=4, ensure_ascii=False),
                           asked_umfragen_json=json.dumps(asked, indent=4, ensure_ascii=False),
                           logs=logs)

@app.route("/quiz/send-random", methods=["POST"])
@login_required
def quiz_send_random():
    with open(os.path.join(BOTS_DIR, "quiz_bot", "command_send_random.tmp"), "w") as f: f.write("1")
    flash("Befehl zum Senden einer Quizfrage gesendet.", "info")
    return redirect(request.referrer or url_for("index"))

@app.route("/umfrage/send-random", methods=["POST"])
@login_required
def umfrage_send_random():
    with open(os.path.join(BOTS_DIR, "umfrage_bot", "command_send_random.tmp"), "w") as f: f.write("1")
    flash("Befehl zum Senden einer Umfrage gesendet.", "info")
    return redirect(request.referrer or url_for("index"))

@app.route("/admin/users")
@login_required
def manage_users():
    return render_template("manage_users.html", users=load_json(USERS_FILE, {}))

@app.route("/minecraft")
@login_required
def minecraft_status_page():
    cfg = load_json(MINECRAFT_STATUS_CONFIG_FILE)
    status = load_json(MINECRAFT_STATUS_CACHE_FILE)
    
    # Get bot status
    bot_stats = get_bot_status()
    is_running = bot_stats.get("minecraft", {}).get("running", False)
    
    # Logic for online status
    server_online = False
    if status.get("online") is True:
        server_online = True
        
    # Pi metrik dummy / placeholder
    pi = {
        "cpu_percent": 0,
        "ram_used_mb": 0,
        "temp_c": 0,
        "disk_percent": 0
    }
    
    log_tail = ""
    if os.path.exists(MATCH_CONFIG["minecraft"]["log"]):
        with open(MATCH_CONFIG["minecraft"]["log"], "r", encoding="utf-8") as f:
            log_tail = f.read()[-2000:]

    return render_template("minecraft.html", 
                           cfg=cfg, 
                           status=status, 
                           is_running=is_running,
                           server_online=server_online,
                           pi=pi,
                           log_tail=log_tail)

@app.route("/minecraft-status/start", methods=["POST"])
@login_required
def minecraft_status_start():
    cfg = MATCH_CONFIG["minecraft"]
    log_f = open(cfg["log"], "a", encoding="utf-8")
    subprocess.Popen([VENV_PYTHON, cfg["script"]], cwd=os.path.dirname(cfg["script"]), stdout=log_f, stderr=subprocess.STDOUT, text=True, bufsize=1)
    flash("Minecraft Status Bot gestartet.", "success")
    return redirect(url_for("minecraft_status_page"))

@app.route("/minecraft-status/stop", methods=["POST"])
@login_required
def minecraft_status_stop():
    subprocess.run(["pkill", "-f", MATCH_CONFIG["minecraft"]["pattern"]])
    flash("Minecraft Status Bot gestoppt.", "info")
    return redirect(url_for("minecraft_status_page"))

@app.route("/minecraft-status/save", methods=["POST"])
@login_required
def minecraft_status_save():
    cfg = load_json(MINECRAFT_STATUS_CONFIG_FILE)
    cfg["mc_host"] = request.form.get("mc_host")
    cfg["mc_port"] = int(request.form.get("mc_port", 25565))
    cfg["display_host"] = request.form.get("display_host")
    cfg["display_port"] = int(request.form.get("display_port", 25565))
    cfg["chat_id"] = request.form.get("chat_id")
    cfg["topic_id"] = request.form.get("topic_id")
    save_json(MINECRAFT_STATUS_CONFIG_FILE, cfg)
    flash("Minecraft Konfiguration gespeichert.", "success")
    return redirect(url_for("minecraft_status_page"))

@app.route("/minecraft-status/reset-message", methods=["POST"])
@login_required
def minecraft_status_reset_message():
    cfg = load_json(MINECRAFT_STATUS_CONFIG_FILE)
    if "message_id" in cfg:
        del cfg["message_id"]
        save_json(MINECRAFT_STATUS_CONFIG_FILE, cfg)
    flash("Message-ID zurückgesetzt.", "info")
    return redirect(url_for("minecraft_status_page"))

@app.route("/outfit-bot/dashboard")
@login_required
def outfit_bot_dashboard():
    config = load_json(OUTFIT_BOT_CONFIG_FILE)
    bot_data = load_json(OUTFIT_BOT_DATA_FILE)
    logs = []
    if os.path.exists(OUTFIT_BOT_LOG_FILE):
        with open(OUTFIT_BOT_LOG_FILE, "r", encoding="utf-8") as f:
            logs = f.readlines()[-100:]
    
    status = get_bot_status()
    is_running = status.get("outfit", {}).get("running", False)
    
    duel_status = {"active": False, "contestants": ""}
    if bot_data.get("current_duel"):
        duel_status["active"] = True
        c_list = [f"@{c['username']}" for c in bot_data["current_duel"]["contestants"].values()]
        duel_status["contestants"] = " vs ".join(c_list)

    return render_template("outfit_bot_dashboard.html", 
                           config=config, 
                           is_running=is_running, 
                           logs=logs,
                           duel_status=duel_status)

@app.route("/outfit-bot/action/<action>", methods=["POST"])
@login_required
def outfit_bot_actions(action):
    if action == "save_config":
        new_cfg = load_json(OUTFIT_BOT_CONFIG_FILE)
        new_cfg["BOT_TOKEN"] = request.form.get("BOT_TOKEN")
        new_cfg["CHAT_ID"] = request.form.get("CHAT_ID")
        new_cfg["TOPIC_ID"] = request.form.get("TOPIC_ID")
        new_cfg["AUTO_POST_ENABLED"] = "AUTO_POST_ENABLED" in request.form
        new_cfg["POST_TIME"] = request.form.get("POST_TIME")
        new_cfg["WINNER_TIME"] = request.form.get("WINNER_TIME")
        new_cfg["DUEL_MODE"] = "DUEL_MODE" in request.form
        new_cfg["DUEL_TYPE"] = request.form.get("DUEL_TYPE")
        new_cfg["DUEL_DURATION_MINUTES"] = int(request.form.get("DUEL_DURATION_MINUTES", 60))
        
        admins = [x.strip() for x in request.form.get("ADMIN_USER_IDS", "").split(",") if x.strip()]
        new_cfg["ADMIN_USER_IDS"] = admins
        
        save_json(OUTFIT_BOT_CONFIG_FILE, new_cfg)
        flash("Konfiguration gespeichert. Bitte Bot neu starten.", "success")
    
    elif action == "start_contest":
        with open(os.path.join(BOTS_DIR, "outfit_bot", "command_start_contest.tmp"), "w") as f: f.write("1")
        flash("Befehl zum Starten des Wettbewerbs gesendet.", "info")
        
    elif action == "announce_winner":
        with open(os.path.join(BOTS_DIR, "outfit_bot", "command_announce_winner.tmp"), "w") as f: f.write("1")
        flash("Befehl zum Auslosen des Gewinners gesendet.", "info")

    elif action == "end_duel":
        with open(os.path.join(BOTS_DIR, "outfit_bot", "command_end_duel.tmp"), "w") as f: f.write("1")
        flash("Befehl zum Beenden des Duells gesendet.", "info")
        
    elif action == "clear_logs":
        if os.path.exists(OUTFIT_BOT_LOG_FILE):
            with open(OUTFIT_BOT_LOG_FILE, "w") as f: f.write("")
        flash("Logs gelöscht.", "info")

    return redirect(url_for("outfit_bot_dashboard"))

@app.route("/critical-errors")
@login_required
def critical_errors():
    logs = []
    if os.path.exists(CRITICAL_ERRORS_LOG_FILE):
        with open(CRITICAL_ERRORS_LOG_FILE, "r", encoding="utf-8") as f:
            logs = f.readlines()
    return render_template("critical_errors.html", critical_logs=logs)

@app.route("/critical-errors/clear", methods=["POST"])
@login_required
def clear_critical_errors():
    if os.path.exists(CRITICAL_ERRORS_LOG_FILE):
        with open(CRITICAL_ERRORS_LOG_FILE, "w") as f: f.write("")
    flash("Kritische Logs gelöscht.", "info")
    return redirect(url_for("critical_errors"))

@app.route("/id-finder/admin-panel")
@login_required
def id_finder_admin_panel():
    return render_template("id_finder_admin_panel.html", admins=load_json(ADMINS_FILE, {}))

@app.route("/id-finder/commands")
@login_required
def id_finder_commands():
    return render_template("id_finder_commands.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# Add missing dummy routes to prevent BuildError
@app.route("/broadcast/save", methods=["POST"])
@login_required
def save_broadcast(): return redirect(url_for("broadcast_manager"))

@app.route("/broadcast/topic-mapping/save", methods=["POST"])
@login_required
def save_topic_mapping(): return redirect(url_for("broadcast_manager"))

@app.route("/broadcast/topic-mapping/delete/<topic_id>", methods=["POST"])
@login_required
def delete_topic_mapping(topic_id): return redirect(url_for("broadcast_manager"))

@app.route("/broadcast/delete/<broadcast_id>", methods=["POST"])
@login_required
def delete_broadcast(broadcast_id): return redirect(url_for("broadcast_manager"))

@app.route("/admin/users/add", methods=["POST"])
@login_required
def add_user(): return redirect(url_for("manage_users"))

@app.route("/admin/users/delete/<username>", methods=["POST"])
@login_required
def delete_user(username): return redirect(url_for("manage_users"))

@app.route("/admin/users/edit/<username>", methods=["POST"])
@login_required
def edit_user(username): return redirect(url_for("manage_users"))

@app.route("/id-finder/admin/delete", methods=["POST"])
@login_required
def id_finder_delete_admin(): return redirect(url_for("id_finder_admin_panel"))

@app.route("/id-finder/admin/add", methods=["POST"])
@login_required
def id_finder_add_admin(): return redirect(url_for("id_finder_admin_panel"))

@app.route("/id-finder/admin/update-permissions", methods=["POST"])
@login_required
def id_finder_update_admin_permissions(): return redirect(url_for("id_finder_admin_panel"))

@app.route("/id-finder/analytics")
@login_required
def id_finder_analytics(): return render_template("id_finder_analytics.html")

@app.route("/id-finder/user/delete/<user_id>", methods=["POST"])
@login_required
def id_finder_delete_user(user_id): return redirect(url_for("id_finder_dashboard"))

@app.route("/invite-bot/move-field/<field_id>/<direction>")
@login_required
def invite_bot_move_field(field_id, direction): return redirect(url_for("bot_settings"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9002, debug=True)
