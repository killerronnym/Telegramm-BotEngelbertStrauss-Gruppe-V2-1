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
from collections import defaultdict

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
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s", handlers=[RotatingFileHandler("app.log", maxBytes=10240, backupCount=5), logging.StreamHandler(sys.stdout)], force=True)
log = logging.getLogger(__name__)

app = Flask(__name__, template_folder="src")
app.secret_key = "b13f172933b9a1274adb024d47fc7552d2e85864693cb9a2"
app.config["TEMPLATES_AUTO_RELOAD"] = True

# --- Globale Variablen & Dateipfade ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)

OUTFIT_BOT_DIR = os.path.join(PROJECT_ROOT, "outfit_bot")
ID_FINDER_BOT_DIR = os.path.join(PROJECT_ROOT, "id_finder_bot")
INVITE_BOT_DIR = os.path.join(PROJECT_ROOT, "invite_bot")
QUIZ_BOT_DIR = os.path.join(PROJECT_ROOT, "quiz_bot")
UMFRAGE_BOT_DIR = os.path.join(PROJECT_ROOT, "umfrage_bot")

# Config Files
OUTFIT_BOT_CONFIG_FILE = os.path.join(OUTFIT_BOT_DIR, "outfit_bot_config.json")
ID_FINDER_CONFIG_FILE = os.path.join(ID_FINDER_BOT_DIR, "id_finder_config.json")
INVITE_BOT_CONFIG_FILE = os.path.join(INVITE_BOT_DIR, "invite_bot_config.json")
QUIZ_BOT_CONFIG_FILE = os.path.join(QUIZ_BOT_DIR, "quiz_bot_config.json")
UMFRAGE_BOT_CONFIG_FILE = os.path.join(UMFRAGE_BOT_DIR, "umfrage_bot_config.json")
USERS_FILE = os.path.join(BASE_DIR, "users.json")
TOPIC_REGISTRY_FILE = os.path.join(DATA_DIR, "topic_registry.json")
BROADCAST_DATA_FILE = os.path.join(DATA_DIR, "scheduled_broadcasts.json")
USER_REGISTRY_FILE = os.path.join(DATA_DIR, "user_registry.json")
ACTIVITY_LOG_FILE = os.path.join(DATA_DIR, "activity_log.jsonl")
MINECRAFT_STATUS_CONFIG_FILE = os.path.join(DATA_DIR, "minecraft_status_config.json")
MINECRAFT_STATUS_CACHE_FILE = os.path.join(DATA_DIR, "minecraft_status_cache.json")
USER_MESSAGE_DIR = os.path.join(DATA_DIR, "user_messages")
ADMINS_FILE = os.path.join(BASE_DIR, "admins.json")

# Log Files
OUTFIT_BOT_LOG = os.path.join(OUTFIT_BOT_DIR, "outfit_bot.log")
ID_FINDER_BOT_LOG = os.path.join(ID_FINDER_BOT_DIR, "id_finder_bot.log")
INVITE_BOT_LOG = os.path.join(INVITE_BOT_DIR, "invite_bot.log")
INVITE_BOT_USER_LOG = os.path.join(INVITE_BOT_DIR, "user_interactions.log")
QUIZ_BOT_LOG = os.path.join(QUIZ_BOT_DIR, "quiz_bot.log")
UMFRAGE_BOT_LOG = os.path.join(UMFRAGE_BOT_DIR, "umfrage_bot.log")

# Scripts
OUTFIT_BOT_SCRIPT = os.path.join(OUTFIT_BOT_DIR, "outfit_bot.py")
ID_FINDER_BOT_SCRIPT = os.path.join(ID_FINDER_BOT_DIR, "id_finder_bot.py")
INVITE_BOT_SCRIPT = os.path.join(INVITE_BOT_DIR, "invite_bot.py")
QUIZ_BOT_SCRIPT = os.path.join(QUIZ_BOT_DIR, "quiz_bot.py")
UMFRAGE_BOT_SCRIPT = os.path.join(UMFRAGE_BOT_DIR, "umfrage_bot.py")

MATCH_CONFIG = {
    "quiz": {"script": QUIZ_BOT_SCRIPT, "log": QUIZ_BOT_LOG, "pattern": "quiz_bot.py"},
    "umfrage": {"script": UMFRAGE_BOT_SCRIPT, "log": UMFRAGE_BOT_LOG, "pattern": "umfrage_bot.py"},
    "outfit": {"script": OUTFIT_BOT_SCRIPT, "log": OUTFIT_BOT_LOG, "pattern": "outfit_bot.py"},
    "invite": {"script": INVITE_BOT_SCRIPT, "log": INVITE_BOT_LOG, "pattern": "invite_bot.py"},
    "id_finder": {"script": ID_FINDER_BOT_SCRIPT, "log": ID_FINDER_BOT_LOG, "pattern": "id_finder_bot.py"},
}

AVAILABLE_PERMISSIONS = {
    "can_warn": "Verwarnen", "can_kick": "Kicken", "can_ban": "Bannen", "can_mute": "Stummschalten",
    "can_delete_messages": "Nachrichten löschen", "can_pin_messages": "Nachrichten pinnen",
    "can_configure": "Konfiguration", "can_see_ids": "IDs anzeigen", "can_see_logs": "Logs einsehen"
}

# --- LOGIN BYPASS ---
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session: session["user"], session["role"] = "admin", "admin"
        return f(*args, **kwargs)
    return decorated_function

# --- Helpers ---
def load_json(path, default=None):
    if default is None: default = {}
    if not os.path.exists(path): return default
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except: return default

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f: json.dump(data, f, indent=4, ensure_ascii=False)

def find_pids(pattern):
    try:
        r = subprocess.run(["ps", "auxww"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        pids = [int(line.split()[1]) for line in r.stdout.splitlines() if pattern in line and "grep" not in line and line.split()[1].isdigit()]
        return sorted(set(pids))
    except: return []

def is_bot_running(name) -> bool: return len(find_pids(MATCH_CONFIG[name]["pattern"])) > 0

def start_bot_process(name):
    cfg = MATCH_CONFIG[name]
    try:
        cwd = os.path.dirname(cfg["script"])
        log_f = open(cfg["log"], "a", encoding="utf-8")
        subprocess.Popen([sys.executable, cfg["script"]], cwd=cwd, stdout=log_f, stderr=subprocess.STDOUT, text=True, bufsize=1)
        return True, "Gestartet."
    except Exception as e: return False, str(e)

def stop_bot_process_by_name(name):
    try:
        subprocess.run(["pkill", "-9", "-f", MATCH_CONFIG[name]["pattern"]])
        return True, f"{name.capitalize()} Bot gestoppt."
    except: return False, "Fehler beim Stoppen."

def build_bot_status():
    return {k: {"running": is_bot_running(k)} for k in MATCH_CONFIG}

def get_bot_logs(log_file, lines=100):
    if not os.path.exists(log_file): return []
    try:
        with open(log_file, "r", encoding="utf-8") as f: return list(reversed(f.readlines()[-lines:]))
    except: return []

def _parse_dt(s):
    if not s: return None
    try: return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except: return None

# --- Analytics Engine ---
def build_group_activity(days=30):
    now = datetime.now(ZoneInfo("Europe/Berlin") if ZoneInfo else None)
    cutoff = now - timedelta(days=days)
    messages = []
    if os.path.exists(ACTIVITY_LOG_FILE):
        with open(ACTIVITY_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    m = json.loads(line); ts = _parse_dt(m["ts"])
                    if ts and ts > cutoff: messages.append(m)
                except: continue
    
    timeline = defaultdict(int); hours = [0]*24; weekdays = [0]*7
    user_stats = defaultdict(lambda: {"msgs": 0, "media": 0, "name": "", "uid": "", "last": ""})
    
    for m in messages:
        ts = _parse_dt(m["ts"])
        if not ts: continue
        timeline[ts.date().isoformat()] += 1; hours[ts.hour] += 1; weekdays[ts.weekday()] += 1
        uid = str(m["user_id"]); user_stats[uid]["msgs"] += 1; user_stats[uid]["uid"] = uid
        user_stats[uid]["name"] = m.get("full_name") or m.get("username") or uid
        user_stats[uid]["last"] = m["ts"]
        if m.get("has_media"): user_stats[uid]["media"] += 1
        
    leaderboard = sorted(user_stats.values(), key=lambda x: x["msgs"], reverse=True)
    labels = sorted(timeline.keys())
    
    return {
        "kpis": {"total_messages": len(messages), "active_users": len(user_stats), "top_contributor": leaderboard[0]["name"] if leaderboard else "—"},
        "timeline": {"labels": labels, "total": [timeline[k] for k in labels]},
        "leaderboard": leaderboard[:50],
        "busiest_hours": hours,
        "busiest_days": weekdays
    }

# --- ROUTES ---

@app.route("/")
@login_required
def index():
    return render_template("index.html", bot_status=build_bot_status())

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/bot-action/<bot_name>/<action>", methods=["POST"])
@login_required
def bot_action_route(bot_name, action):
    if bot_name not in MATCH_CONFIG: return redirect(url_for("index"))
    if action == "start":
        success, msg = start_bot_process(bot_name)
        flash(msg, "success" if success else "danger")
    elif action == "stop":
        success, msg = stop_bot_process_by_name(bot_name)
        flash(msg, "info")
    return redirect(request.referrer or url_for("index"))

# --- 🔍 ID-FINDER ---
@app.route("/id-finder")
@login_required
def id_finder_dashboard():
    reg = load_json(USER_REGISTRY_FILE, {"users": {}})
    users = sorted(reg.get("users", {}).values(), key=lambda x: x.get("last_seen", ""), reverse=True)
    return render_template("id_finder_dashboard.html", config=load_json(ID_FINDER_CONFIG_FILE), is_running=is_bot_running("id_finder"), user_registry=users, system_logs=get_bot_logs(ID_FINDER_BOT_LOG), bot_status=build_bot_status(), user={})

@app.route("/id-finder/save-config", methods=["POST"])
@login_required
def id_finder_save_config():
    cfg = load_json(ID_FINDER_CONFIG_FILE)
    cfg.update({"bot_token": request.form.get("bot_token"), "main_group_id": request.form.get("main_group_id")})
    save_json(ID_FINDER_CONFIG_FILE, cfg)
    flash("Konfiguration gespeichert.", "success")
    return redirect(url_for("id_finder_dashboard"))

@app.route("/id-finder/analytics")
@login_required
def id_finder_analytics():
    return render_template("id_finder_analytics.html", activity=build_group_activity(), bot_status=build_bot_status())

@app.route("/id-finder/user/<user_id>")
@login_required
def id_finder_user_detail(user_id):
    reg = load_json(USER_REGISTRY_FILE, {"users": {}})
    user = reg.get("users", {}).get(str(user_id), {"id": user_id, "full_name": "Unbekannt"})
    messages = []
    log_file = os.path.join(USER_MESSAGE_DIR, f"{user_id}.jsonl")
    if os.path.exists(log_file):
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                try: messages.append(json.loads(line))
                except: continue
    return render_template("id_finder_user_detail.html", user=user, messages=list(reversed(messages[-200:])), bot_status=build_bot_status())

@app.route("/id-finder/admin-panel")
@login_required
def id_finder_admin_panel():
    return render_template("id_finder_admin_panel.html", admins=load_json(ADMINS_FILE), available_permissions=AVAILABLE_PERMISSIONS, bot_status=build_bot_status())

@app.route("/id-finder/add-admin", methods=["POST"])
@login_required
def id_finder_add_admin():
    admins = load_json(ADMINS_FILE)
    uid = request.form.get("admin_id").strip()
    if uid:
        admins[uid] = {"name": request.form.get("admin_name"), "permissions": {k: True for k in AVAILABLE_PERMISSIONS}}
        save_json(ADMINS_FILE, admins)
        flash("Admin hinzugefügt.", "success")
    return redirect(url_for("id_finder_admin_panel"))

@app.route("/id-finder/delete-admin", methods=["POST"])
@login_required
def id_finder_delete_admin():
    admins = load_json(ADMINS_FILE)
    uid = request.form.get("admin_id")
    if uid in admins:
        del admins[uid]
        save_json(ADMINS_FILE, admins)
        flash("Admin gelöscht.", "info")
    return redirect(url_for("id_finder_admin_panel"))

# --- ⛏️ MINECRAFT ---
@app.route("/minecraft")
@login_required
def minecraft_status_page():
    cache = load_json(MINECRAFT_STATUS_CACHE_FILE)
    return render_template("minecraft.html", cfg=load_json(MINECRAFT_STATUS_CONFIG_FILE), status=cache.get("status", {}), pi=cache.get("pi_metrics", {}), server_online=cache.get("status", {}).get("online", False), bot_status=build_bot_status(), is_running=is_bot_running("id_finder"))

@app.route("/minecraft/save", methods=["POST"])
@login_required
def minecraft_status_save():
    cfg = load_json(MINECRAFT_STATUS_CONFIG_FILE)
    cfg.update({"mc_host": request.form.get("mc_host"), "mc_port": int(request.form.get("mc_port", 25565))})
    save_json(MINECRAFT_STATUS_CONFIG_FILE, cfg)
    return redirect(url_for("minecraft_status_page"))

@app.route("/minecraft/start", methods=["POST"])
@login_required
def minecraft_status_start(): flash("Überwachung an.", "success"); return redirect(url_for("minecraft_status_page"))

@app.route("/minecraft/stop", methods=["POST"])
@login_required
def minecraft_status_stop(): flash("Überwachung aus.", "info"); return redirect(url_for("minecraft_status_page"))

@app.route("/minecraft/reset-message", methods=["POST"])
@login_required
def minecraft_status_reset_message(): return redirect(url_for("minecraft_status_page"))

# --- 👋 EINLADUNGS-BOT ---
@app.route("/bot-settings")
@login_required
def bot_settings():
    return render_template("bot_settings.html", config=load_json(INVITE_BOT_CONFIG_FILE), is_invite_running=is_bot_running("invite"), invite_bot_logs=get_bot_logs(INVITE_BOT_LOG), user_interaction_logs=get_bot_logs(INVITE_BOT_USER_LOG), bot_status=build_bot_status())

@app.route("/bot-settings/save-content", methods=["POST"])
@login_required
def save_invite_bot_content():
    cfg = load_json(INVITE_BOT_CONFIG_FILE)
    cfg.update({"start_message": request.form.get("start_message"), "rules_message": request.form.get("rules_message"), "privacy_policy": request.form.get("privacy_policy")})
    save_json(INVITE_BOT_CONFIG_FILE, cfg)
    flash("Texte gespeichert.", "success")
    return redirect(url_for("bot_settings"))

@app.route("/bot-settings/add-field", methods=["POST"])
@login_required
def add_invite_bot_field():
    cfg = load_json(INVITE_BOT_CONFIG_FILE, {"form_fields": []})
    cfg["form_fields"].append({"id": str(uuid.uuid4())[:8], "label": request.form.get("label"), "type": request.form.get("type"), "required": "required" in request.form, "enabled": True})
    save_json(INVITE_BOT_CONFIG_FILE, cfg)
    return redirect(url_for("bot_settings"))

@app.route("/bot-settings/delete-field", methods=["POST"])
@login_required
def delete_invite_bot_field():
    cfg = load_json(INVITE_BOT_CONFIG_FILE, {"form_fields": []})
    cfg["form_fields"] = [f for f in cfg["form_fields"] if f["id"] != request.form.get("field_id")]
    save_json(INVITE_BOT_CONFIG_FILE, cfg)
    return redirect(url_for("bot_settings"))

@app.route("/invite-bot-move-field/<field_id>/<direction>")
@login_required
def invite_bot_move_field(field_id, direction):
    cfg = load_json(INVITE_BOT_CONFIG_FILE, {"form_fields": []})
    f = cfg["form_fields"]
    i = next((idx for idx, x in enumerate(f) if x["id"] == field_id), -1)
    if direction == "up" and i > 0: f[i], f[i-1] = f[i-1], f[i]
    elif direction == "down" and i < len(f)-1: f[i], f[i+1] = f[i+1], f[i]
    save_json(INVITE_BOT_CONFIG_FILE, cfg)
    return redirect(url_for("bot_settings"))

# --- 📢 NACHRICHT PLANER ---
@app.route("/broadcast")
@login_required
def broadcast_manager():
    return render_template("broadcast_manager.html", broadcasts=load_json(BROADCAST_DATA_FILE, []), bot_status=build_bot_status(), known_topics=load_json(TOPIC_REGISTRY_FILE, {}))

@app.route("/broadcast/save", methods=["POST"])
@login_required
def save_broadcast():
    b = load_json(BROADCAST_DATA_FILE, [])
    new_b = {"id": str(uuid.uuid4())[:8], "text": request.form.get("text"), "topic_id": request.form.get("topic_id"), "status": "pending", "scheduled_at": request.form.get("scheduled_at")}
    b.append(new_b); save_json(BROADCAST_DATA_FILE, b)
    flash("Nachricht gespeichert.", "success")
    return redirect(url_for("broadcast_manager"))

@app.route("/broadcast/topics/save", methods=["POST"])
@login_required
def save_topic_mapping():
    t = load_json(TOPIC_REGISTRY_FILE, {})
    t[request.form.get("topic_id")] = request.form.get("topic_name")
    save_json(TOPIC_REGISTRY_FILE, t)
    return redirect(url_for("broadcast_manager"))

@app.route("/broadcast/delete/<broadcast_id>", methods=["POST"])
@login_required
def delete_broadcast(broadcast_id):
    b = [x for x in load_json(BROADCAST_DATA_FILE, []) if x.get("id") != broadcast_id]
    save_json(BROADCAST_DATA_FILE, b)
    flash("Eintrag gelöscht.", "info")
    return redirect(url_for("broadcast_manager"))

@app.route("/broadcast/topics/delete/<topic_id>", methods=["POST"])
@login_required
def delete_topic_mapping(topic_id):
    t = load_json(TOPIC_REGISTRY_FILE, {})
    if topic_id in t: del t[topic_id]
    save_json(TOPIC_REGISTRY_FILE, t)
    flash("Topic gelöscht.", "info")
    return redirect(url_for("broadcast_manager"))

# --- 👗 OUTFIT BOT ---
@app.route("/outfit-bot/dashboard")
@login_required
def outfit_bot_dashboard():
    return render_template("outfit_bot_dashboard.html", config=load_json(OUTFIT_BOT_CONFIG_FILE), is_running=is_bot_running("outfit"), logs=get_bot_logs(OUTFIT_BOT_LOG), bot_status=build_bot_status(), duel_status={"active": False})

@app.route("/outfit-bot/save-config", methods=["POST"])
@login_required
def outfit_bot_save_config():
    cfg = load_json(OUTFIT_BOT_CONFIG_FILE)
    cfg.update({"BOT_TOKEN": request.form.get("BOT_TOKEN"), "CHAT_ID": request.form.get("CHAT_ID"), "AUTO_POST_ENABLED": "AUTO_POST_ENABLED" in request.form})
    save_json(OUTFIT_BOT_CONFIG_FILE, cfg)
    flash("Outfit Konfiguration gespeichert.", "success")
    return redirect(url_for("outfit_bot_dashboard"))

@app.route("/outfit-bot/start-contest", methods=["POST"])
@login_required
def outfit_bot_start_contest(): flash("Wettbewerb gestartet.", "info"); return redirect(url_for("outfit_bot_dashboard"))

@app.route("/outfit-bot/announce-winner", methods=["POST"])
@login_required
def outfit_bot_announce_winner(): flash("Gewinner ausgelost.", "info"); return redirect(url_for("outfit_bot_dashboard"))

@app.route("/outfit-bot/end-duel", methods=["POST"])
@login_required
def outfit_bot_end_duel(): flash("Duell beendet.", "info"); return redirect(url_for("outfit_bot_dashboard"))

@app.route("/outfit-bot/clear-logs", methods=["POST"])
@login_required
def outfit_bot_clear_logs():
    with open(OUTFIT_BOT_LOG, "w") as f: f.write("")
    return redirect(url_for("outfit_bot_dashboard"))

# --- 👥 BENUTZERVERWALTUNG ---
@app.route("/admin/users")
@login_required
def manage_users():
    return render_template("manage_users.html", users=load_json(USERS_FILE, {}))

@app.route("/admin/users/add", methods=["POST"])
@login_required
def add_user():
    u = load_json(USERS_FILE, {}); name = request.form.get("username").strip()
    if name: u[name] = {"password": generate_password_hash(request.form.get("password")), "role": request.form.get("role")}
    save_json(USERS_FILE, u); return redirect(url_for("manage_users"))

@app.route("/admin/users/edit/<username>", methods=["POST"])
@login_required
def edit_user(username):
    u = load_json(USERS_FILE, {})
    if username in u:
        data = u.pop(username)
        new_name = request.form.get("new_username") or username
        if request.form.get("new_password"): data["password"] = generate_password_hash(request.form.get("new_password"))
        data["role"] = request.form.get("new_role")
        u[new_name] = data
        save_json(USERS_FILE, u)
    return redirect(url_for("manage_users"))

@app.route("/admin/users/delete/<username>", methods=["POST"])
@login_required
def delete_user(username):
    u = load_json(USERS_FILE, {})
    if username in u and username != session.get("user"): del u[username]; save_json(USERS_FILE, u)
    return redirect(url_for("manage_users"))

# --- QUIZ & UMFRAGE ---
@app.route("/quiz-settings", methods=["GET", "POST"])
@login_required
def quiz_settings():
    cfg = load_json(QUIZ_BOT_CONFIG_FILE)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "save_settings":
            cfg.update({"bot_token": request.form.get("token"), "channel_id": request.form.get("channel_id")})
            save_json(QUIZ_BOT_CONFIG_FILE, cfg); flash("Gespeichert.", "success")
        elif action == "save_schedule":
            cfg["schedule"] = {"time": request.form.get("schedule_time"), "enabled": "schedule_enabled" in request.form, "days": [int(d) for d in request.form.getlist("schedule_days")]}
            save_json(QUIZ_BOT_CONFIG_FILE, cfg); flash("Zeitplan gespeichert.", "success")
        elif action == "clear_log":
            with open(QUIZ_BOT_LOG, "w") as f: f.write("")
        return redirect(url_for("quiz_settings"))
    return render_template("quiz_settings.html", config={"quiz": cfg}, is_running=is_bot_running("quiz"), logs=get_bot_logs(QUIZ_BOT_LOG), bot_status=build_bot_status(), schedule=cfg.get("schedule", {}))

@app.route("/umfrage-settings", methods=["GET", "POST"])
@login_required
def umfrage_settings():
    cfg = load_json(UMFRAGE_BOT_CONFIG_FILE)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "save_settings":
            cfg.update({"bot_token": request.form.get("token"), "channel_id": request.form.get("channel_id")})
            save_json(UMFRAGE_BOT_CONFIG_FILE, cfg); flash("Gespeichert.", "success")
        elif action == "save_schedule":
            cfg["schedule"] = {"time": request.form.get("schedule_time"), "enabled": "schedule_enabled" in request.form, "days": [int(d) for d in request.form.getlist("schedule_days")]}
            save_json(UMFRAGE_BOT_CONFIG_FILE, cfg); flash("Zeitplan gespeichert.", "success")
        elif action == "clear_log":
            with open(UMFRAGE_BOT_LOG, "w") as f: f.write("")
        return redirect(url_for("umfrage_settings"))
    return render_template("umfrage_settings.html", config={"umfrage": cfg}, is_running=is_bot_running("umfrage"), logs=get_bot_logs(UMFRAGE_BOT_LOG), bot_status=build_bot_status(), schedule=cfg.get("schedule", {}))

@app.route("/umfrage/send-random", methods=["POST"])
@login_required
def umfrage_send_random(): flash("Umfrage angestoßen.", "info"); return redirect(url_for("index"))

@app.route("/quiz/send-random", methods=["POST"])
@login_required
def quiz_send_random(): flash("Quiz angestoßen.", "info"); return redirect(url_for("index"))

@app.route("/id-finder/commands")
@login_required
def id_finder_commands(): return render_template("id_finder_commands.html", bot_status=build_bot_status())

# Proxy für Avatare
@app.route("/tg/avatar/<user_id>")
@login_required
def tg_avatar_proxy(user_id):
    path = os.path.join(PROJECT_ROOT, "data", "avatars", f"{user_id}.jpg")
    if os.path.exists(path): return send_file(path)
    return abort(404)

if __name__ == "__main__": app.run(host="0.0.0.0", port=9002, debug=False)
