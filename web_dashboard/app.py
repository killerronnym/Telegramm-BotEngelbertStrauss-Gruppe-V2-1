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

# ✅ Pfad-Fix für Module im gleichen Verzeichnis
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# ✅ Telegram Proxy Cache
import hashlib
import mimetypes
import urllib.parse
import urllib.request
import urllib.error

# ✅ Updater Integration
from updater import Updater

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

# --- Pfade ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
BOTS_DIR = os.path.join(PROJECT_ROOT, "bots")
VERSION_FILE = os.path.join(PROJECT_ROOT, "version.json")
DASHBOARD_CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
USERS_FILE = os.path.join(BASE_DIR, "users.json")
ADMINS_FILE = os.path.join(BASE_DIR, "admins.json")
TOPIC_REGISTRY_FILE = os.path.join(DATA_DIR, "topic_registry.json")
ACTIVITY_LOG_FILE = os.path.join(DATA_DIR, "activity_log.jsonl")
USER_MESSAGE_DIR = os.path.join(DATA_DIR, "user_messages")
ID_FINDER_CONFIG_FILE = os.path.join(BOTS_DIR, "id_finder_bot", "id_finder_config.json")
MODERATION_CONFIG_FILE = os.path.join(DATA_DIR, "moderation_config.json")
MODERATION_DATA_FILE = os.path.join(DATA_DIR, "moderation_data.json") 
PENDING_DELETIONS_FILE = os.path.join(DATA_DIR, "pending_deletions.json")
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

# --- Helpers ---
def load_json(path, default=None):
    if not os.path.exists(path): return default if default is not None else {}
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except: return default if default is not None else {}

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f: json.dump(data, f, indent=4, ensure_ascii=False)

# --- SETUP CHECK ---
def is_setup_done():
    return os.path.exists(USERS_FILE) and os.path.exists(DASHBOARD_CONFIG_FILE)

@app.before_request
def check_for_setup():
    if request.path.startswith('/static') or request.path == '/setup':
        return
    if not is_setup_done():
        return redirect(url_for('setup_wizard'))

@app.route("/setup", methods=["GET", "POST"])
def setup_wizard():
    if is_setup_done():
        return redirect(url_for('index'))
    if request.method == "POST":
        admin_user = request.form.get("admin_user")
        admin_pass = request.form.get("admin_pass")
        repo_path = request.form.get("repo_path", "killerronnym/Bot-EngelbertStrauss-Gruppe-ffentlich")
        bot_token = request.form.get("bot_token")
        
        users = {admin_user: {"password": generate_password_hash(admin_pass), "role": "admin"}}
        save_json(USERS_FILE, users)
        
        repo_parts = repo_path.split("/")
        owner = repo_parts[0] if len(repo_parts) > 0 else "killerronnym"
        repo = repo_parts[1] if len(repo_parts) > 1 else "Bot-EngelbertStrauss-Gruppe-ffentlich"
        
        config = {
            "github_token": "",
            "github_owner": owner,
            "github_repo": repo,
            "secret_key": str(uuid.uuid4()),
            "quiz": {"token": bot_token, "channel_id": "", "topic_id": ""},
            "umfrage": {"token": bot_token, "channel_id": "", "topic_id": ""}
        }
        save_json(DASHBOARD_CONFIG_FILE, config)
        if not os.path.exists(VERSION_FILE):
            save_json(VERSION_FILE, {"version": "3.0.0", "release_date": datetime.now().isoformat()})
        flash("Installation erfolgreich! Bitte logge dich ein.", "success")
        return redirect(url_for("login"))
    return render_template("setup.html")

# --- Updater Initialisierung ---
def get_updater():
    if not is_setup_done(): return None
    cfg = load_json(DASHBOARD_CONFIG_FILE)
    return Updater(
        repo_owner=cfg.get("github_owner", "killerronnym"),
        repo_name=cfg.get("github_repo", "Bot-EngelbertStrauss-Gruppe-ffentlich"),
        current_version_file=VERSION_FILE,
        project_root=PROJECT_ROOT
    )

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

VENV_PYTHON = os.path.join(PROJECT_ROOT, ".venv", "bin", "python3")
if not os.path.exists(VENV_PYTHON): VENV_PYTHON = sys.executable

MATCH_CONFIG = {
    "quiz": {"pattern": "quiz_bot.py", "script": os.path.join(BOTS_DIR, "quiz_bot", "quiz_bot.py"), "log": os.path.join(BOTS_DIR, "quiz_bot", "quiz_bot.log")},
    "umfrage": {"pattern": "umfrage_bot.py", "script": os.path.join(BOTS_DIR, "umfrage_bot", "umfrage_bot.py"), "log": os.path.join(BOTS_DIR, "umfrage_bot", "umfrage_bot.log")},
    "outfit": {"pattern": "outfit_bot.py", "script": os.path.join(BOTS_DIR, "outfit_bot", "outfit_bot.py"), "log": os.path.join(BOTS_DIR, "outfit_bot", "outfit_bot.log")},
    "invite": {"pattern": "invite_bot.py", "script": os.path.join(BOTS_DIR, "invite_bot", "invite_bot.py"), "log": os.path.join(BOTS_DIR, "invite_bot", "invite_bot.log")},
    "id_finder": {"pattern": "id_finder_bot.py", "script": os.path.join(BOTS_DIR, "id_finder_bot", "id_finder_bot.py"), "log": os.path.join(BOTS_DIR, "id_finder_bot", "id_finder_bot.log")},
    "minecraft": {"pattern": "minecraft_bridge.py", "script": os.path.join(BOTS_DIR, "id_finder_bot", "minecraft_bridge.py"), "log": os.path.join(BOTS_DIR, "id_finder_bot", "minecraft_bridge.log")},
}

def get_bot_status():
    try:
        output = subprocess.run(["ps", "aux"], stdout=subprocess.PIPE, text=True, check=False).stdout
        return {k: {"running": cfg["pattern"] in output} for k, cfg in MATCH_CONFIG.items()}
    except: return {k: {"running": False} for k in MATCH_CONFIG}

@app.context_processor
def inject_globals():
    return {"bot_status": get_bot_status()}

def tg_api_call(method, params):
    cfg = load_json(ID_FINDER_CONFIG_FILE)
    token = cfg.get("bot_token") or load_json(DASHBOARD_CONFIG_FILE).get("quiz", {}).get("token")
    if not token: return None
    try:
        url = f"https://api.telegram.org/bot{token}/{method}"
        data = urllib.parse.urlencode(params).encode("utf-8")
        with urllib.request.urlopen(urllib.request.Request(url, data=data)) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        log.error(f"TG API Error: {e}")
        return None

# --- AUTH ---
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session: return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        users = load_json(USERS_FILE, {})
        if username in users and check_password_hash(users[username]["password"], password):
            session["user"], session["role"] = username, users[username].get("role", "admin")
            return redirect(url_for("index"))
        flash("Ungültige Zugangsdaten.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

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
    u = get_updater()
    local_ver = u.get_local_version() if u else {"version": "3.0.0"}
    return render_template("index.html", version=local_ver)

@app.route("/api/update/check")
@login_required
def update_check():
    u = get_updater()
    if not u: return jsonify({"update_available": False})
    return jsonify(u.check_for_update())

@app.route("/api/update/install", methods=["POST"])
@login_required
def update_install():
    u = get_updater()
    if not u: return jsonify({"error": "Updater not ready"}), 500
    data = request.json
    u.install_update(data.get("zipball_url"), data.get("latest_version"), data.get("published_at"))
    return jsonify({"status": "started"})

@app.route("/api/update/status")
@login_required
def update_status():
    u = get_updater()
    return jsonify(u.get_status() if u else {"status": "idle"})

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
                if custom_topic: chat_data["topics"][topic_id] = f"{custom_topic['emoji']} {custom_topic['name']}"
    mod_config = load_json(MODERATION_CONFIG_FILE, {'max_warnings': 3, 'warning_text': 'Hallo {user}...', 'public_delete_notice_text': '...', 'public_delete_notice_duration': 60})
    selected_chat_id, selected_topic_id = request.args.get("chat_id"), request.args.get("topic_id")
    messages = []
    if os.path.exists(ACTIVITY_LOG_FILE):
        with open(ACTIVITY_LOG_FILE, "r", encoding="utf-8") as f:
            lines = deque(f, maxlen=500)
            for line in lines:
                try:
                    m = json.loads(line)
                    if selected_chat_id and str(m.get("chat_id")) != str(selected_chat_id): continue
                    if selected_topic_id and selected_topic_id != "all" and str(m.get("thread_id")) != str(selected_topic_id): continue
                    if f"{m.get('chat_id')}_{m.get('message_id')}" in deleted_message_ids: m['is_deleted'] = True
                    messages.append(m)
                except: continue
    messages.reverse()
    return render_template('live_moderation.html', topics=topics_data, messages=messages, selected_chat_id=selected_chat_id, selected_topic_id=selected_topic_id, mod_config=mod_config)

@app.route('/live_moderation/config', methods=['POST'])
@login_required
def live_moderation_config():
    save_json(MODERATION_CONFIG_FILE, {'max_warnings': int(request.form.get('max_warnings', 3)), 'warning_text': request.form.get('warning_text'), 'public_delete_notice_text': request.form.get('public_delete_notice_text'), 'public_delete_notice_duration': int(request.form.get('public_delete_notice_duration', 60))})
    flash('Die Moderations-Einstellungen wurden gespeichert.', 'success')
    return redirect(url_for('live_moderation'))

@app.route('/live_moderation/delete', methods=['POST'])
@login_required
def live_moderation_delete():
    user_id_str, chat_id, message_id, topic_id, action, user_name, chat_name = request.form.get("user_id"), request.form.get("chat_id"), request.form.get("message_id"), request.form.get("topic_id"), request.form.get("action"), request.form.get("user_name"), request.form.get("chat_name")
    reason = request.form.get("reason_custom") if request.form.get("reason_preset") == 'other' else request.form.get("reason_preset", "Kein Grund")
    mod_data = load_json(MODERATION_DATA_FILE, {})
    deleted_ids = mod_data.setdefault("deleted_messages", [])
    if f"{chat_id}_{message_id}" not in deleted_ids: deleted_ids.append(f"{chat_id}_{message_id}")
    save_json(MODERATION_DATA_FILE, mod_data)
    tg_api_call("deleteMessage", {"chat_id": chat_id, "message_id": message_id})
    mod_config = load_json(MODERATION_CONFIG_FILE)
    public_text = mod_config.get("public_delete_notice_text", "...").format(user=user_name, group=chat_name, reason=reason)
    send_params = {"chat_id": chat_id, "text": public_text}
    if topic_id: send_params["message_thread_id"] = topic_id
    resp = tg_api_call("sendMessage", send_params)
    if resp and resp.get("ok"):
        duration = int(mod_config.get("public_delete_notice_duration", 60))
        if duration > 0: delete_message_after_delay(chat_id, resp["result"]["message_id"], duration)
    if action == "warn":
        user_warnings = mod_data.setdefault("users", {}).setdefault(user_id_str, {"warnings": []})
        user_warnings["warnings"].append({"reason": reason, "timestamp": datetime.now().isoformat(), "chat_id": chat_id, "chat_name": chat_name, "message_id": message_id})
        save_json(MODERATION_DATA_FILE, mod_data)
        max_w = mod_config.get("max_warnings", 3)
        if len(user_warnings["warnings"]) >= max_w:
            tg_api_call("banChatMember", {"chat_id": chat_id, "user_id": user_id_str})
            flash(f"Nutzer {user_name} wurde gebannt.", "danger")
        else:
            w_text = mod_config.get("warning_text").format(user=user_name, group=chat_name, reason=reason, warn_count=len(user_warnings["warnings"]), max_warnings=max_w)
            tg_api_call("sendMessage", {"chat_id": user_id_str, "text": w_text})
            flash(f"Nutzer {user_name} verwarnt.", "success")
    return redirect(request.referrer or url_for("live_moderation"))

@app.route('/user/<user_id>')
@login_required
def user_detail(user_id):
    mod_data, user_reg = load_json(MODERATION_DATA_FILE, {"users": {}}), load_json(USER_REGISTRY_FILE, {})
    user_info = user_reg.get(str(user_id), {})
    return render_template('id_finder_user_detail.html', user={'user_id': user_id, 'full_name': user_info.get('full_name', 'Unbekannt'), 'username': user_info.get('username', '')}, warnings=mod_data.get("users", {}).get(str(user_id), {}).get("warnings", []))

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
    token = load_json(ID_FINDER_CONFIG_FILE).get("bot_token") or load_json(DASHBOARD_CONFIG_FILE).get("quiz", {}).get("token")
    if not token: return abort(500)
    try:
        url = f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}"
        with urllib.request.urlopen(url) as r:
            info = json.loads(r.read().decode())
            if not info.get("ok"): return abort(500)
            file_url = f"https://api.telegram.org/file/bot{token}/{info['result']['file_path']}"
            with urllib.request.urlopen(file_url) as fr:
                return send_file(io.BytesIO(fr.read()), mimetype=fr.info().get_content_type())
    except: return abort(500)

@app.route("/id-finder")
@login_required
def id_finder_dashboard(): return render_template("id_finder_dashboard.html", config=load_json(ID_FINDER_CONFIG_FILE))

@app.route("/broadcast")
@login_required
def broadcast_manager(): return render_template("broadcast_manager.html", broadcasts=load_json(BROADCAST_DATA_FILE, []), known_topics=load_json(TOPIC_REGISTRY_FILE, {}))

@app.route("/bot-settings")
@login_required
def bot_settings(): return render_template("bot_settings.html", config=load_json(INVITE_BOT_CONFIG_FILE))

@app.route("/quiz-settings", methods=["GET", "POST"])
@login_required
def quiz_settings():
    Q_FILE, A_FILE = os.path.join(DATA_DIR, "quizfragen.json"), os.path.join(BOTS_DIR, "quiz_bot", "quizfragen_gestellt.json")
    if request.method == "POST":
        action, cfg = request.form.get("action"), load_json(QUIZ_BOT_CONFIG_FILE)
        if action == "save_settings":
            cfg.update({"bot_token": request.form.get("token"), "channel_id": request.form.get("channel_id"), "topic_id": request.form.get("topic_id")})
            save_json(QUIZ_BOT_CONFIG_FILE, cfg)
        elif action == "save_schedule":
            sch = cfg.setdefault("schedule", {})
            sch.update({"enabled": "schedule_enabled" in request.form, "time": request.form.get("schedule_time"), "days": [int(x) for x in request.form.getlist("schedule_days")]})
            save_json(QUIZ_BOT_CONFIG_FILE, cfg)
        elif action == "save_questions": save_json(Q_FILE, json.loads(request.form.get("questions_json")))
        flash("Gespeichert.", "success")
        return redirect(url_for("quiz_settings"))
    config, qs, asked = load_json(QUIZ_BOT_CONFIG_FILE), load_json(Q_FILE, []), load_json(A_FILE, [])
    logs = open(MATCH_CONFIG["quiz"]["log"]).readlines()[-50:] if os.path.exists(MATCH_CONFIG["quiz"]["log"]) else []
    return render_template("quiz_settings.html", config=config, schedule=config.get("schedule", {}), stats={"total": len(qs)+len(asked), "asked": len(asked), "remaining": len(qs)}, questions_json=json.dumps(qs, indent=4, ensure_ascii=False), asked_questions_json=json.dumps(asked, indent=4, ensure_ascii=False), logs=logs)

@app.route("/umfrage-settings", methods=["GET", "POST"])
@login_required
def umfrage_settings():
    U_FILE, A_FILE = os.path.join(DATA_DIR, "umfragen.json"), os.path.join(BOTS_DIR, "umfrage_bot", "umfragen_gestellt.json")
    if request.method == "POST":
        action, cfg = request.form.get("action"), load_json(UMFRAGE_BOT_CONFIG_FILE)
        if action == "save_settings":
            cfg.update({"bot_token": request.form.get("token"), "channel_id": request.form.get("channel_id"), "topic_id": request.form.get("topic_id")})
            save_json(UMFRAGE_BOT_CONFIG_FILE, cfg)
        elif action == "save_schedule":
            sch = cfg.setdefault("schedule", {})
            sch.update({"enabled": "schedule_enabled" in request.form, "time": request.form.get("schedule_time"), "days": [int(x) for x in request.form.getlist("schedule_days")]})
            save_json(UMFRAGE_BOT_CONFIG_FILE, cfg)
        elif action == "save_umfragen": save_json(U_FILE, json.loads(request.form.get("umfragen_json")))
        flash("Gespeichert.", "success")
        return redirect(url_for("umfrage_settings"))
    config, us, asked = load_json(UMFRAGE_BOT_CONFIG_FILE), load_json(U_FILE, []), load_json(A_FILE, [])
    logs = open(MATCH_CONFIG["umfrage"]["log"]).readlines()[-50:] if os.path.exists(MATCH_CONFIG["umfrage"]["log"]) else []
    return render_template("umfrage_settings.html", config=config, schedule=config.get("schedule", {}), stats={"total": len(us)+len(asked), "asked": len(asked), "remaining": len(us)}, umfragen_json=json.dumps(us, indent=4, ensure_ascii=False), asked_umfragen_json=json.dumps(asked, indent=4, ensure_ascii=False), logs=logs)

@app.route("/minecraft")
@login_required
def minecraft_status_page():
    cfg, status = load_json(MINECRAFT_STATUS_CONFIG_FILE), load_json(MINECRAFT_STATUS_CACHE_FILE)
    log_tail = open(MATCH_CONFIG["minecraft"]["log"]).read()[-2000:] if os.path.exists(MATCH_CONFIG["minecraft"]["log"]) else ""
    return render_template("minecraft.html", cfg=cfg, status=status, is_running=get_bot_status().get("minecraft", {}).get("running"), server_online=status.get("online") is True, pi={"cpu_percent":0,"ram_used_mb":0,"temp_c":0,"disk_percent":0}, log_tail=log_tail)

@app.route("/minecraft-status/save", methods=["POST"])
@login_required
def minecraft_status_save():
    cfg = load_json(MINECRAFT_STATUS_CONFIG_FILE)
    cfg.update({"mc_host": request.form.get("mc_host"), "mc_port": int(request.form.get("mc_port", 25565)), "display_host": request.form.get("display_host"), "display_port": int(request.form.get("display_port", 25565)), "chat_id": request.form.get("chat_id"), "topic_id": request.form.get("topic_id")})
    save_json(MINECRAFT_STATUS_CONFIG_FILE, cfg)
    flash("Gespeichert.", "success")
    return redirect(url_for("minecraft_status_page"))

@app.route("/outfit-bot/dashboard")
@login_required
def outfit_bot_dashboard():
    cfg, data = load_json(OUTFIT_BOT_CONFIG_FILE), load_json(OUTFIT_BOT_DATA_FILE)
    logs = open(OUTFIT_BOT_LOG_FILE).readlines()[-100:] if os.path.exists(OUTFIT_BOT_LOG_FILE) else []
    duel = {"active": True, "contestants": " vs ".join([f"@{c['username']}" for c in data["current_duel"]["contestants"].values()])} if data.get("current_duel") else {"active": False, "contestants": ""}
    return render_template("outfit_bot_dashboard.html", config=cfg, is_running=get_bot_status().get("outfit", {}).get("running"), logs=logs, duel_status=duel)

@app.route("/critical-errors")
@login_required
def critical_errors():
    logs = open(CRITICAL_ERRORS_LOG_FILE).readlines() if os.path.exists(CRITICAL_ERRORS_LOG_FILE) else []
    return render_template("critical_errors.html", critical_logs=logs)

@app.route("/admin/users")
@login_required
def manage_users(): return render_template("manage_users.html", users=load_json(USERS_FILE, {}))

@app.route("/id-finder/admin-panel")
@login_required
def id_finder_admin_panel(): return render_template("id_finder_admin_panel.html", admins=load_json(ADMINS_FILE, {}))

@app.route("/id-finder/commands")
@login_required
def id_finder_commands(): return render_template("id_finder_commands.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9002, debug=True)
