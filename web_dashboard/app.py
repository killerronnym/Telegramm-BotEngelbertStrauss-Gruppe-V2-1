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
PENDING_DELETIONS_FILE = os.path.join(DATA_DIR, "pending_deletions.json")
ADMINS_FILE = os.path.join(BASE_DIR, "admins.json")
USERS_FILE = os.path.join(BASE_DIR, "users.json")
BROADCAST_DATA_FILE = os.path.join(DATA_DIR, "scheduled_broadcasts.json")
USER_REGISTRY_FILE = os.path.join(DATA_DIR, "user_registry.json")
MINECRAFT_STATUS_CONFIG_FILE = os.path.join(DATA_DIR, "minecraft_status_config.json")
MINECRAFT_STATUS_CACHE_FILE = os.path.join(DATA_DIR, "minecraft_status_cache.json")
QUIZ_BOT_CONFIG_FILE = os.path.join(BOTS_DIR, "quiz_bot", "quiz_bot_config.json")
UMFRAGE_BOT_CONFIG_FILE = os.path.join(BOTS_DIR, "umfrage_bot", "umfrage_bot_config.json")
INVITE_BOT_CONFIG_FILE = os.path.join(BOTS_DIR, "invite_bot", "invite_bot_config.json")
OUTFIT_BOT_CONFIG_FILE = os.path.join(BOTS_DIR, "outfit_bot", "outfit_bot_config.json")

MATCH_CONFIG = {
    "quiz": {"pattern": "quiz_bot.py", "script": os.path.join(BOTS_DIR, "quiz_bot", "quiz_bot.py"), "log": os.path.join(BOTS_DIR, "quiz_bot", "quiz_bot.log")},
    "umfrage": {"pattern": "umfrage_bot.py", "script": os.path.join(BOTS_DIR, "umfrage_bot", "umfrage_bot.py"), "log": os.path.join(BOTS_DIR, "umfrage_bot", "umfrage_bot.log")},
    "outfit": {"pattern": "outfit_bot.py", "script": os.path.join(BOTS_DIR, "outfit_bot", "outfit_bot.py"), "log": os.path.join(BOTS_DIR, "outfit_bot", "outfit_bot.log")},
    "invite": {"pattern": "invite_bot.py", "script": os.path.join(BOTS_DIR, "invite_bot", "invite_bot.py"), "log": os.path.join(BOTS_DIR, "invite_bot", "invite_bot.log")},
    "id_finder": {"pattern": "id_finder_bot.py", "script": os.path.join(BOTS_DIR, "id_finder_bot", "id_finder_bot.py"), "log": os.path.join(BOTS_DIR, "id_finder_bot", "id_finder_bot.log")},
}

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

# --- Background Task for Auto-Deletion ---
def auto_delete_task():
    while True:
        try:
            deletions = load_json(PENDING_DELETIONS_FILE, [])
            if deletions:
                now = datetime.now().timestamp()
                remaining = []
                changed = False
                for item in deletions:
                    if now >= item["delete_at"]:
                        tg_api_call("deleteMessage", {"chat_id": item["chat_id"], "message_id": item["message_id"]})
                        changed = True
                    else:
                        remaining.append(item)
                if changed:
                    save_json(PENDING_DELETIONS_FILE, remaining)
        except Exception as e:
            log.error(f"Error in auto_delete_task: {e}")
        time.sleep(30)

threading.Thread(target=auto_delete_task, daemon=True).start()

# --- ROUTES ---

@app.route("/")
@login_required
def index():
    return render_template("index.html", bot_status={k: {"running": "pattern" in str(subprocess.run(["ps", "aux"], stdout=subprocess.PIPE, text=True).stdout)} for k in MATCH_CONFIG})

@app.route('/live_moderation')
@login_required
def live_moderation():
    topics_data = load_json(TOPIC_REGISTRY_FILE)
    mod_cfg = load_json(MODERATION_CONFIG_FILE)
    selected_chat_id = request.args.get("chat_id")
    selected_topic_id = request.args.get("topic_id")
    messages = []
    if os.path.exists(ACTIVITY_LOG_FILE):
        with open(ACTIVITY_LOG_FILE, "r", encoding="utf-8") as f:
            lines = deque(f, maxlen=150)
            for line in lines:
                try:
                    m = json.loads(line)
                    if selected_chat_id and str(m.get("chat_id")) != str(selected_chat_id): continue
                    if selected_topic_id:
                        if str(m.get("topic_id") or "default") != str(selected_topic_id): continue
                    messages.append(m)
                except: continue
    messages.reverse()
    return render_template('live_moderation.html', topics=topics_data, messages=messages, 
                           selected_chat_id=selected_chat_id, selected_topic_id=selected_topic_id, mod_cfg=mod_cfg)

@app.route("/id-finder/save-mod-config", methods=["POST"])
@login_required
def save_mod_config():
    cfg = {
        "default_reason": request.form.get("default_reason"),
        "dm_template": request.form.get("dm_template"),
        "public_template": request.form.get("public_template"),
        "public_delete_delay_minutes": int(request.form.get("public_delete_delay_minutes", 120))
    }
    save_json(MODERATION_CONFIG_FILE, cfg)
    flash("Einstellungen gespeichert.", "success")
    return redirect(url_for("live_moderation"))

@app.route("/id-finder/moderate", methods=["POST"])
@login_required
def moderate_message():
    user_id = request.form.get("user_id")
    chat_id = request.form.get("chat_id")
    message_id = request.form.get("message_id")
    topic_id = request.form.get("topic_id") # Telegram message_thread_id
    action = request.form.get("action")
    reason = request.form.get("reason", "Kein Grund angegeben")
    user_name = request.form.get("user_name", user_id)
    chat_name = request.form.get("chat_name", "der Gruppe")
    
    mod_cfg = load_json(MODERATION_CONFIG_FILE)
    
    # 1. Ursprungsnachricht löschen
    tg_api_call("deleteMessage", {"chat_id": chat_id, "message_id": message_id})
    
    if action == "warn":
        # 2. Private Nachricht (DM)
        dm_text = mod_cfg.get("dm_template", "").replace("{user}", user_name).replace("{reason}", reason).replace("{group}", chat_name)
        tg_api_call("sendMessage", {"chat_id": user_id, "text": dm_text})
        
        # 3. Öffentliche Nachricht (Im gleichen Topic!)
        time_str = f"{mod_cfg.get('public_delete_delay_minutes')} Minuten"
        pub_text = mod_cfg.get("public_template", "").replace("{user}", user_name).replace("{reason}", reason).replace("{time}", time_str)
        
        params = {"chat_id": chat_id, "text": pub_text}
        if topic_id and topic_id != "None" and str(topic_id).isdigit():
            params["message_thread_id"] = topic_id
            
        res = tg_api_call("sendMessage", params)
        
        # 4. Automatisches Löschen planen
        if res and res.get("ok"):
            new_msg_id = res["result"]["message_id"]
            deletions = load_json(PENDING_DELETIONS_FILE, [])
            delay = int(mod_cfg.get("public_delete_delay_minutes", 120)) * 60
            deletions.append({
                "chat_id": chat_id,
                "message_id": new_msg_id,
                "delete_at": datetime.now().timestamp() + delay
            })
            save_json(PENDING_DELETIONS_FILE, deletions)
        
        flash("Nachricht gelöscht und verwarnt (Auto-Löschung aktiv).", "success")
    else:
        flash("Nachricht gelöscht.", "info")

    _remove_message_from_logs(user_id, message_id)
    return redirect(request.referrer or url_for("live_moderation"))

def _remove_message_from_logs(user_id, message_id):
    paths = [os.path.join(USER_MESSAGE_DIR, f"{user_id}.jsonl"), ACTIVITY_LOG_FILE]
    for p in paths:
        if not os.path.exists(p): continue
        lines = []
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                    if str(d.get("message_id") or d.get("msg_id")) != str(message_id): lines.append(line)
                except: lines.append(line)
        with open(p, "w", encoding="utf-8") as f: f.writelines(lines)

# --- Standard-Routen ---
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
    try:
        url = f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}"
        with urllib.request.urlopen(url) as r:
            path = json.loads(r.read().decode())['result']['file_path']
        with urllib.request.urlopen(f"https://api.telegram.org/file/bot{token}/{path}") as r:
            return send_file(io.BytesIO(r.read()), mimetype=r.info().get_content_type())
    except: return abort(500)

@app.route("/logout")
def logout(): session.clear(); return redirect(url_for("index"))

# (Weitere Standard-Routen)
@app.route("/id-finder") @login_required
def id_finder_dashboard(): return render_template("id_finder_dashboard.html", config=load_json(ID_FINDER_CONFIG_FILE), is_running=False, bot_status={})
@app.route("/broadcast") @login_required
def broadcast_manager(): return render_template("broadcast_manager.html", broadcasts=[], bot_status={}, known_topics={})
@app.route("/bot-settings") @login_required
def bot_settings(): return render_template("bot_settings.html", config={}, bot_status={})
@app.route("/quiz-settings") @login_required
def quiz_settings(): return render_template("quiz_settings.html", config={}, bot_status={})
@app.route("/umfrage-settings") @login_required
def umfrage_settings(): return render_template("umfrage_settings.html", config={}, bot_status={})
@app.route("/admin/users") @login_required
def manage_users(): return render_template("manage_users.html", users={})
@app.route("/minecraft") @login_required
def minecraft_status_page(): return render_template("minecraft.html", cfg={}, status={}, bot_status={})
@app.route("/outfit-bot/dashboard") @login_required
def outfit_bot_dashboard(): return render_template("outfit_bot_dashboard.html", config={}, bot_status={})
@app.route("/critical-errors") @login_required
def critical_errors(): return render_template("critical_errors.html", critical_logs=[], bot_status={})
@app.route("/id-finder/admin-panel") @login_required
def id_finder_admin_panel(): return render_template("id_finder_admin_panel.html", admins={}, bot_status={})
@app.route("/id-finder/commands") @login_required
def id_finder_commands(): return render_template("id_finder_commands.html", bot_status={})

if __name__ == "__main__": app.run(host="0.0.0.0", port=9002, debug=True)