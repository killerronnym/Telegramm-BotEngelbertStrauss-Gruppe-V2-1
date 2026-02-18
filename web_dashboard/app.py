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

BOTS_DIR = os.path.join(PROJECT_ROOT, "bots")
OUTFIT_BOT_DIR = os.path.join(BOTS_DIR, "outfit_bot")
ID_FINDER_BOT_DIR = os.path.join(BOTS_DIR, "id_finder_bot")
INVITE_BOT_DIR = os.path.join(BOTS_DIR, "invite_bot")
QUIZ_BOT_DIR = os.path.join(BOTS_DIR, "quiz_bot")
UMFRAGE_BOT_DIR = os.path.join(BOTS_DIR, "umfrage_bot")

# Config Files
OUTFIT_BOT_CONFIG_FILE = os.path.join(OUTFIT_BOT_DIR, "outfit_bot_config.json")
ID_FINDER_CONFIG_FILE = os.path.join(ID_FINDER_BOT_DIR, "id_finder_config.json")
INVITE_BOT_CONFIG_FILE = os.path.join(INVITE_BOT_DIR, "invite_bot_config.json")
QUIZ_BOT_CONFIG_FILE = os.path.join(QUIZ_BOT_DIR, "quiz_bot_config.json")
UMFRAGE_BOT_CONFIG_FILE = os.path.join(UMFRAGE_BOT_DIR, "umfrage_bot_config.json")

USERS_FILE = os.path.join(BASE_DIR, "users.json")
ADMINS_FILE = os.path.join(BASE_DIR, "admins.json")

TOPIC_REGISTRY_FILE = os.path.join(DATA_DIR, "topic_registry.json")
BROADCAST_DATA_FILE = os.path.join(DATA_DIR, "scheduled_broadcasts.json")
USER_REGISTRY_FILE = os.path.join(DATA_DIR, "user_registry.json")
ACTIVITY_LOG_FILE = os.path.join(DATA_DIR, "activity_log.jsonl")
MINECRAFT_STATUS_CONFIG_FILE = os.path.join(DATA_DIR, "minecraft_status_config.json")
MINECRAFT_STATUS_CACHE_FILE = os.path.join(DATA_DIR, "minecraft_status_cache.json")
USER_MESSAGE_DIR = os.path.join(DATA_DIR, "user_messages")

# Data files for Quiz and Umfrage bots
QUIZ_FRAGEN_FILE = os.path.join(PROJECT_ROOT, "data", "quizfragen.json")
QUIZ_FRAGEN_GESTELLT_FILE = os.path.join(QUIZ_BOT_DIR, "quizfragen_gestellt.json")
UMFRAGEN_FILE = os.path.join(PROJECT_ROOT, "data", "umfragen.json")
UMFRAGEN_GESTELLT_FILE = os.path.join(UMFRAGE_BOT_DIR, "umfragen_gestellt.json")

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

# --- Helpers ---
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session: session["user"], session["role"] = "admin", "admin"
        return f(*args, **kwargs)
    return decorated_function

def load_json(path, default=None):
    if default is None: default = {}
    if not os.path.exists(path): return default
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except: return default

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f: json.dump(data, f, indent=4, ensure_ascii=False)

def get_running_processes():
    """Fetch all running python processes to avoid multiple ps calls."""
    try:
        r = subprocess.run(["ps", "auxww"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        processes = []
        for line in r.stdout.splitlines():
            # Check for python processes
            if "python" in line:
                parts = line.split()
                if len(parts) > 10 and parts[1].isdigit():
                    cmd = " ".join(parts[10:])
                    processes.append(cmd)
        return processes
    except Exception as e:
        log.error(f"Error fetching processes: {e}")
        return []

def is_bot_running(name, processes=None) -> bool:
    if processes is None:
        processes = get_running_processes()
    pattern = MATCH_CONFIG[name]["pattern"]
    return any(pattern in cmd and "grep" not in cmd for cmd in processes)

def start_bot_process(name):
    if is_bot_running(name):
        return False, f"{name.capitalize()} Bot läuft bereits."

    cfg = MATCH_CONFIG[name]
    try:
        cwd = os.path.dirname(cfg["script"])
        # Ensure log directory exists
        os.makedirs(os.path.dirname(cfg["log"]), exist_ok=True)
        
        log_f = open(cfg["log"], "a", encoding="utf-8")
        
        # Start the process
        proc = subprocess.Popen([sys.executable, cfg["script"]], cwd=cwd, stdout=log_f, stderr=subprocess.STDOUT, text=True, bufsize=1)
        
        # Wait a bit to check if it crashes immediately
        time.sleep(2.0)
        
        if proc.poll() is not None:
            # Process exited immediately
            return False, f"Start fehlgeschlagen (Exit Code: {proc.returncode}). Bitte Logs prüfen."
        
        # Double check process list
        if not is_bot_running(name):
             return False, "Start initialisiert, aber Prozess scheint nicht zu laufen."

        return True, "Gestartet."
    except Exception as e: return False, str(e)

def stop_bot_process_by_name(name):
    try:
        subprocess.run(["pkill", "-9", "-f", MATCH_CONFIG[name]["pattern"]])
        return True, f"{name.capitalize()} Bot gestoppt."
    except: return False, "Fehler beim Stoppen."

def build_bot_status():
    processes = get_running_processes()
    return {k: {"running": is_bot_running(k, processes)} for k in MATCH_CONFIG}

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
def build_group_activity(days=None, month=None, year=None):
    now = datetime.now(ZoneInfo("Europe/Berlin") if ZoneInfo else None)
    messages = []
    if os.path.exists(ACTIVITY_LOG_FILE):
        with open(ACTIVITY_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    m = json.loads(line); ts = _parse_dt(m["ts"])
                    if not ts: continue
                    if days and str(days).isdigit():
                        if ts < now - timedelta(days=int(days)): continue
                    if month and int(month) != 0:
                        if ts.month != int(month): continue
                    if year and int(year) != 0:
                        if ts.year != int(year): continue
                    messages.append(m)
                except: continue
    
    timeline = defaultdict(int); hours = [0]*24; weekdays = [0]*7
    user_stats = defaultdict(lambda: {"msgs": 0, "media": 0, "reacts": 0, "name": "", "uid": "", "last": ""})
    chat_activity = defaultdict(int); media_count = 0; total_reactions = 0
    
    for m in messages:
        ts = _parse_dt(m["ts"])
        if not ts: continue
        timeline[ts.date().isoformat()] += 1; hours[ts.hour] += 1; weekdays[ts.weekday()] += 1
        uid = str(m["user_id"])
        user_stats[uid]["msgs"] += 1; user_stats[uid]["uid"] = uid
        user_stats[uid]["name"] = m.get("full_name") or m.get("username") or uid
        user_stats[uid]["last"] = m["ts"]
        if m.get("has_media"): user_stats[uid]["media"] += 1; media_count += 1
        reacts = m.get("reactions", 0); user_stats[uid]["reacts"] += reacts; total_reactions += reacts
        chat_activity[str(m.get("chat_id", "Unknown"))] += 1
        
    leaderboard = sorted(user_stats.values(), key=lambda x: x["msgs"], reverse=True)
    labels = sorted(timeline.keys())
    days_names = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    busiest_day_idx = weekdays.index(max(weekdays)) if max(weekdays) > 0 else 0
    
    return {
        "kpis": {
            "total_messages": len(messages), "active_users": len(user_stats), 
            "top_contributor": leaderboard[0]["name"] if leaderboard else "—",
            "media_shared": media_count, "total_reactions": total_reactions,
            "busiest_day": days_names[busiest_day_idx] if len(messages) > 0 else "—",
            "most_liked_user": sorted(user_stats.values(), key=lambda x: x["reacts"], reverse=True)[0]["name"] if leaderboard else "—",
            "top_chat": sorted(chat_activity.items(), key=lambda x: x[1], reverse=True)[0][0] if chat_activity else "—"
        },
        "timeline": {"labels": labels, "total": [timeline[k] for k in labels]},
        "leaderboard": leaderboard[:100], "recent_users": sorted(user_stats.values(), key=lambda x: x["last"], reverse=True)[:50],
        "busiest_hours": hours, "busiest_days": weekdays
    }

def get_all_user_msg_counts():
    counts = defaultdict(int)
    if os.path.exists(ACTIVITY_LOG_FILE):
        with open(ACTIVITY_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    m = json.loads(line); counts[str(m["user_id"])] += 1
                except: continue
    return counts

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
    msg_counts = get_all_user_msg_counts()
    users = []
    for uid, udata in reg.get("users", {}).items():
        udata["id"] = uid
        udata["msg_count"] = msg_counts.get(str(uid), 0)
        users.append(udata)
    return render_template("id_finder_dashboard.html", config=load_json(ID_FINDER_CONFIG_FILE), is_running=is_bot_running("id_finder"), user_registry=sorted(users, key=lambda x: x.get("last_seen", ""), reverse=True), system_logs=get_bot_logs(ID_FINDER_BOT_LOG), bot_status=build_bot_status())

@app.route("/id-finder/save-config", methods=["POST"])
@login_required
def id_finder_save_config():
    cfg = load_json(ID_FINDER_CONFIG_FILE)
    cfg.update({
        "bot_token": request.form.get("bot_token"), 
        "main_group_id": int(request.form.get("main_group_id", 0)) if request.form.get("main_group_id") else 0,
        "admin_group_id": int(request.form.get("admin_group_id", 0)) if request.form.get("admin_group_id") else 0,
        "admin_log_topic_id": int(request.form.get("admin_log_topic_id", 0)) if request.form.get("admin_log_topic_id") else None,
        "delete_commands": "delete_commands" in request.form,
        "bot_message_cleanup_seconds": int(request.form.get("bot_message_cleanup_seconds", 10)),
        "message_logging_enabled": "message_logging_enabled" in request.form,
        "message_logging_ignore_commands": "message_logging_ignore_commands" in request.form,
        "message_logging_groups_only": "message_logging_groups_only" in request.form
    })
    save_json(ID_FINDER_CONFIG_FILE, cfg); flash("Konfiguration gespeichert.", "success")
    return redirect(url_for("id_finder_dashboard"))

@app.route("/id-finder/delete-user/<user_id>", methods=["POST"])
@login_required
def id_finder_delete_user(user_id):
    reg = load_json(USER_REGISTRY_FILE, {"users": {}})
    if str(user_id) in reg.get("users", {}):
        del reg["users"][str(user_id)]; save_json(USER_REGISTRY_FILE, reg)
        flash(f"User {user_id} gelöscht.", "info")
    return redirect(url_for("id_finder_dashboard"))

@app.route("/id-finder/analytics")
@login_required
def id_finder_analytics():
    reg = load_json(USER_REGISTRY_FILE, {"users": {}})
    users = []; unique_chats = set(); latest_user = None
    for uid, udata in reg.get("users", {}).items():
        udata["id"] = uid; users.append(udata)
        for c in (udata.get("chat_ids") or udata.get("groups_seen") or []): unique_chats.add(c)
        if not latest_user or udata.get("last_seen", "") > latest_user.get("last_seen", ""): latest_user = udata
    chat_counts = defaultdict(int)
    for u in users:
        for c in (u.get("chat_ids") or u.get("groups_seen") or []): chat_counts[str(c)] += 1
    stats = {"total_users": len(users), "unique_chats": len(unique_chats), "most_recent_user": latest_user, "top_chats": sorted(chat_counts.items(), key=lambda x: x[1], reverse=True)[:10]}
    activity_data = build_group_activity(days=request.args.get("days"), month=request.args.get("month"), year=request.args.get("year"))
    return render_template("id_finder_analytics.html", activity=activity_data, stats=stats, user_registry=sorted(users, key=lambda x: x.get("last_seen", ""), reverse=True), bot_status=build_bot_status())

@app.route("/api/id-finder/user-activity/<user_id>")
@login_required
def api_id_finder_user_activity(user_id):
    days = request.args.get("days"); month = request.args.get("month"); year = request.args.get("year")
    activity = build_group_activity(days, month, year)
    user_timeline = {label: 0 for label in activity["timeline"]["labels"]}
    user_hours = [0]*24; user_weekdays = [0]*7
    if os.path.exists(ACTIVITY_LOG_FILE):
        with open(ACTIVITY_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    m = json.loads(line); ts = _parse_dt(m["ts"])
                    if ts and str(m["user_id"]) == str(user_id):
                        date_str = ts.date().isoformat()
                        if date_str in user_timeline:
                            user_timeline[date_str] += 1; user_hours[ts.hour] += 1; user_weekdays[ts.weekday()] += 1
                except: continue
    return jsonify({"timeline": [user_timeline[label] for label in activity["timeline"]["labels"]], "hours": user_hours, "weekdays": user_weekdays})

@app.route("/id-finder/user/<user_id>")
@login_required
def id_finder_user_detail(user_id):
    reg = load_json(USER_REGISTRY_FILE, {"users": {}})
    user = reg.get("users", {}).get(str(user_id))
    if not user: return redirect(url_for("id_finder_dashboard"))
    user["id"] = user_id; messages = []
    log_file = os.path.join(USER_MESSAGE_DIR, f"{user_id}.jsonl")
    if os.path.exists(log_file):
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                try: messages.append(json.loads(line))
                except: continue
    return render_template("id_finder_user_detail.html", user=user, messages=list(reversed(messages[-200:])), bot_status=build_bot_status())

@app.route("/id-finder/commands")
@login_required
def id_finder_commands(): return render_template("id_finder_commands.html", bot_status=build_bot_status())

@app.route("/id-finder/admin-panel")
@login_required
def id_finder_admin_panel(): 
    return render_template("id_finder_admin_panel.html", admins=load_json(ADMINS_FILE), available_permissions=AVAILABLE_PERMISSIONS, bot_status=build_bot_status())

@app.route("/id-finder/add-admin", methods=["POST"])
@login_required
def id_finder_add_admin():
    admins = load_json(ADMINS_FILE); uid = request.form.get("admin_id").strip()
    if uid:
        admins[uid] = {"name": request.form.get("admin_name"), "permissions": {k: True for k in AVAILABLE_PERMISSIONS}}
        save_json(ADMINS_FILE, admins)
        flash("Admin hinzugefügt.", "success")
    return redirect(url_for("id_finder_admin_panel"))

@app.route("/id-finder/delete-admin", methods=["POST"])
@login_required
def id_finder_delete_admin():
    admins = load_json(ADMINS_FILE); uid = request.form.get("admin_id")
    if uid in admins:
        del admins[uid]
        save_json(ADMINS_FILE, admins)
        flash("Admin gelöscht.", "info")
    return redirect(url_for("id_finder_admin_panel"))

@app.route("/id-finder/update-admin-permissions", methods=["POST"])
@login_required
def id_finder_update_admin_permissions():
    admins = load_json(ADMINS_FILE); uid = request.form.get("admin_id")
    if uid in admins:
        admins[uid]["permissions"] = {p: (p in request.form) for p in AVAILABLE_PERMISSIONS}
        save_json(ADMINS_FILE, admins)
        flash("Rechte aktualisiert.", "success")
    return redirect(url_for("id_finder_admin_panel"))

# --- 👋 EINLADUNGS-BOT ---
@app.route("/bot-settings", methods=["GET", "POST"])
@login_required
def bot_settings(): 
    if request.method == "POST":
        action = request.form.get("action")
        if action == "start_invite_bot":
            success, msg = start_bot_process("invite"); flash(msg, "success" if success else "danger")
        elif action == "stop_invite_bot":
            success, msg = stop_bot_process_by_name("invite"); flash(msg, "info")
        elif action == "save_base_config":
            cfg = load_json(INVITE_BOT_CONFIG_FILE)
            cfg.update({
                "bot_token": request.form.get("bot_token"),
                "main_chat_id": request.form.get("main_chat_id"),
                "topic_id": request.form.get("topic_id"),
                "link_ttl_minutes": int(request.form.get("link_ttl_minutes", 15)),
                "is_enabled": "is_enabled" in request.form
            })
            save_json(INVITE_BOT_CONFIG_FILE, cfg)
            flash("Konfiguration gespeichert.", "success")
        return redirect(url_for("bot_settings"))
    return render_template("bot_settings.html", config=load_json(INVITE_BOT_CONFIG_FILE), is_invite_running=is_bot_running("invite"), invite_bot_logs=get_bot_logs(INVITE_BOT_LOG), user_interaction_logs=get_bot_logs(INVITE_BOT_USER_LOG), bot_status=build_bot_status())

@app.route("/bot-settings/save-content", methods=["POST"])
@login_required
def save_invite_bot_content():
    cfg = load_json(INVITE_BOT_CONFIG_FILE); cfg.update({"start_message": request.form.get("start_message"), "rules_message": request.form.get("rules_message"), "privacy_policy": request.form.get("privacy_policy")}); save_json(INVITE_BOT_CONFIG_FILE, cfg); flash("Texte gespeichert.", "success")
    return redirect(url_for("bot_settings"))

@app.route("/bot-settings/add-field", methods=["POST"])
@login_required
def add_invite_bot_field():
    cfg = load_json(INVITE_BOT_CONFIG_FILE, {"form_fields": []})
    min_age = None
    if request.form.get("min_age"):
        try: min_age = int(request.form.get("min_age"))
        except: pass
        
    cfg["form_fields"].append({
        "id": request.form.get("field_id"), 
        "label": request.form.get("label"), 
        "emoji": request.form.get("emoji"), 
        "display_name": request.form.get("display_name"), 
        "type": request.form.get("type"), 
        "required": "required" in request.form, 
        "enabled": True,
        "min_age": min_age,
        "min_age_error_msg": request.form.get("min_age_error_msg")
    })
    save_json(INVITE_BOT_CONFIG_FILE, cfg); flash("Feld hinzugefügt.", "success")
    return redirect(url_for("bot_settings"))

@app.route("/bot-settings/edit-field", methods=["POST"])
@login_required
def edit_invite_bot_field():
    cfg = load_json(INVITE_BOT_CONFIG_FILE, {"form_fields": []}); fid = request.form.get("field_id")
    for f in cfg["form_fields"]:
        if f["id"] == fid:
            min_age = None
            if request.form.get("min_age"):
                try: min_age = int(request.form.get("min_age"))
                except: pass
                
            f.update({
                "label": request.form.get("label"), 
                "emoji": request.form.get("emoji"), 
                "display_name": request.form.get("display_name"), 
                "type": request.form.get("type"), 
                "required": "required" in request.form, 
                "enabled": "enabled" in request.form,
                "min_age": min_age,
                "min_age_error_msg": request.form.get("min_age_error_msg")
            })
            break
    save_json(INVITE_BOT_CONFIG_FILE, cfg); flash("Feld aktualisiert.", "success")
    return redirect(url_for("bot_settings"))

@app.route("/bot-settings/delete-field", methods=["POST"])
@login_required
def delete_invite_bot_field():
    cfg = load_json(INVITE_BOT_CONFIG_FILE, {"form_fields": []}); fid = request.form.get("field_id")
    cfg["form_fields"] = [f for f in cfg["form_fields"] if f["id"] != fid]
    save_json(INVITE_BOT_CONFIG_FILE, cfg); flash("Feld gelöscht.", "info")
    return redirect(url_for("bot_settings"))

@app.route("/invite-bot-move-field/<field_id>/<direction>")
@login_required
def invite_bot_move_field(field_id, direction):
    cfg = load_json(INVITE_BOT_CONFIG_FILE, {"form_fields": []}); f = cfg["form_fields"]; i = next((idx for idx, x in enumerate(f) if x["id"] == field_id), -1)
    if direction == "up" and i > 0: f[i], f[i-1] = f[i-1], f[i]
    elif direction == "down" and i < len(f)-1: f[i], f[i+1] = f[i+1], f[i]
    save_json(INVITE_BOT_CONFIG_FILE, cfg); return redirect(url_for("bot_settings"))

@app.route("/bot-settings/clear-logs/<log_type>", methods=["POST"])
@login_required
def clear_invite_bot_logs(log_type):
    if log_type == "user":
        with open(INVITE_BOT_USER_LOG, "w") as f: f.write("")
        flash("User Logs gelöscht.", "info")
    elif log_type == "system":
        with open(INVITE_BOT_LOG, "w") as f: f.write("")
        flash("System Logs gelöscht.", "info")
    return redirect(url_for("bot_settings"))

# --- 📢 NACHRICHT PLANER ---
@app.route("/broadcast")
@login_required
def broadcast_manager(): return render_template("broadcast_manager.html", broadcasts=load_json(BROADCAST_DATA_FILE, []), bot_status=build_bot_status(), known_topics=load_json(TOPIC_REGISTRY_FILE, {}))

@app.route("/broadcast/save", methods=["POST"])
@login_required
def save_broadcast():
    b_list = load_json(BROADCAST_DATA_FILE, [])
    text = request.form.get("text")
    topic_id = request.form.get("topic_id")
    send_mode = request.form.get("send_mode", "standard")
    scheduled_at = request.form.get("scheduled_at")
    pin_message = "pin_message" in request.form
    silent_send = "silent_send" in request.form
    action = request.form.get("action")
    media_file = request.files.get("media")
    media_name = None
    if media_file and media_file.filename:
        upload_dir = os.path.join(DATA_DIR, "broadcast_uploads")
        os.makedirs(upload_dir, exist_ok=True)
        media_name = f"{uuid.uuid4()[:8]}_{media_file.filename}"
        media_file.save(os.path.join(upload_dir, media_name))
    new_b = {"id": str(uuid.uuid4())[:8], "text": text, "topic_id": topic_id, "send_mode": send_mode, "media_name": media_name, "scheduled_at": scheduled_at if action == "schedule" else None, "pin_message": pin_message, "silent_send": silent_send, "status": "pending", "created_at": datetime.now().isoformat()}
    b_list.append(new_b); save_json(BROADCAST_DATA_FILE, b_list); flash("Broadcast gespeichert.", "success")
    return redirect(url_for("broadcast_manager"))

@app.route("/broadcast/topics/save", methods=["POST"])
@login_required
def save_topic_mapping():
    t = load_json(TOPIC_REGISTRY_FILE, {}); t[request.form.get("topic_id")] = request.form.get("topic_name"); save_json(TOPIC_REGISTRY_FILE, t)
    return redirect(url_for("broadcast_manager"))

@app.route("/broadcast/delete/<broadcast_id>", methods=["POST"])
@login_required
def delete_broadcast(broadcast_id):
    b = [x for x in load_json(BROADCAST_DATA_FILE, []) if x.get("id") != broadcast_id]; save_json(BROADCAST_DATA_FILE, b); flash("Eintrag gelöscht.", "info")
    return redirect(url_for("broadcast_manager"))

@app.route("/broadcast/topics/delete/<topic_id>", methods=["POST"])
@login_required
def delete_topic_mapping(topic_id):
    t = load_json(TOPIC_REGISTRY_FILE, {}); 
    if topic_id in t: del t[topic_id]
    save_json(TOPIC_REGISTRY_FILE, t); flash("Topic gelöscht.", "info")
    return redirect(url_for("broadcast_manager"))

# --- 👗 OUTFIT BOT ---
@app.route("/outfit-bot/dashboard")
@login_required
def outfit_bot_dashboard(): return render_template("outfit_bot_dashboard.html", config=load_json(OUTFIT_BOT_CONFIG_FILE), is_running=is_bot_running("outfit"), logs=get_bot_logs(OUTFIT_BOT_LOG), bot_status=build_bot_status(), duel_status={"active": False})

@app.route("/outfit-bot/save-config", methods=["POST"])
@login_required
def outfit_bot_save_config():
    cfg = load_json(OUTFIT_BOT_CONFIG_FILE); cfg.update({"BOT_TOKEN": request.form.get("BOT_TOKEN"), "CHAT_ID": request.form.get("CHAT_ID"), "AUTO_POST_ENABLED": "AUTO_POST_ENABLED" in request.form}); save_json(OUTFIT_BOT_CONFIG_FILE, cfg); flash("Outfit Konfiguration gespeichert.", "success")
    return redirect(url_for("outfit_bot_dashboard"))

@app.route("/outfit-bot/start-contest", methods=["POST"])
@login_required
def outfit_bot_start_contest():
    with open(os.path.join(OUTFIT_BOT_DIR, "command_start_contest.tmp"), "w") as f: f.write("1")
    flash("Befehl gesendet.", "info"); return redirect(url_for("outfit_bot_dashboard"))

@app.route("/outfit-bot/announce-winner", methods=["POST"])
@login_required
def outfit_bot_announce_winner():
    with open(os.path.join(OUTFIT_BOT_DIR, "command_announce_winner.tmp"), "w") as f: f.write("1")
    flash("Befehl gesendet.", "info"); return redirect(url_for("outfit_bot_dashboard"))

@app.route("/outfit-bot/end-duel", methods=["POST"])
@login_required
def outfit_bot_end_duel():
    with open(os.path.join(OUTFIT_BOT_DIR, "command_end_duel.tmp"), "w") as f: f.write("1")
    flash("Befehl gesendet.", "info"); return redirect(url_for("outfit_bot_dashboard"))

@app.route("/outfit-bot/clear-logs", methods=["POST"])
@login_required
def outfit_bot_clear_logs():
    with open(OUTFIT_BOT_LOG, "w") as f: f.write("")
    return redirect(url_for("outfit_bot_dashboard"))

# --- 👥 BENUTZERVERWALTUNG ---
@app.route("/admin/users")
@login_required
def manage_users(): return render_template("manage_users.html", users=load_json(USERS_FILE, {}))

@app.route("/admin/users/add", methods=["POST"])
@login_required
def add_user():
    u = load_json(USERS_FILE, {}); name = request.form.get("username").strip()
    if name: u[name] = {"password": generate_password_hash(request.form.get("password")), "role": request.form.get("role")}; save_json(USERS_FILE, u)
    return redirect(url_for("manage_users"))

@app.route("/admin/users/edit/<username>", methods=["POST"])
@login_required
def edit_user(username):
    u = load_json(USERS_FILE, {}); 
    if username in u:
        data = u.pop(username); new_name = request.form.get("new_username") or username; 
        if request.form.get("new_password"): data["password"] = generate_password_hash(request.form.get("new_password"))
        data["role"] = request.form.get("new_role"); u[new_name] = data; save_json(USERS_FILE, u)
    return redirect(url_for("manage_users"))

@app.route("/admin/users/delete/<username>", methods=["POST"])
@login_required
def delete_user(username):
    u = load_json(USERS_FILE, {}); 
    if username in u and username != session.get("user"): del u[username]; save_json(USERS_FILE, u)
    return redirect(url_for("manage_users"))

# --- ⛏️ MINECRAFT ---
@app.route("/minecraft")
@login_required
def minecraft_status_page():
    cache = load_json(MINECRAFT_STATUS_CACHE_FILE)
    return render_template("minecraft.html", cfg=load_json(MINECRAFT_STATUS_CONFIG_FILE), status=cache.get("status", {}), pi=cache.get("pi_metrics", {}), server_online=cache.get("status", {}).get("online", False), bot_status=build_bot_status(), is_running=is_bot_running("id_finder"))

@app.route("/minecraft/save", methods=["POST"])
@login_required
def minecraft_status_save():
    cfg = load_json(MINECRAFT_STATUS_CONFIG_FILE); cfg.update({"mc_host": request.form.get("mc_host"), "mc_port": int(request.form.get("mc_port", 25565))}); save_json(MINECRAFT_STATUS_CONFIG_FILE, cfg)
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

# --- QUIZ & UMFRAGE ---
def question_fingerprint(q: dict) -> str:
    frage = str(q.get("frage", "")).strip()
    optionen = q.get("optionen", [])
    if not isinstance(optionen, list):
        optionen = []
    payload = frage + "||" + "||".join([str(x).strip() for x in sorted(optionen)])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()

@app.route("/quiz-settings", methods=["GET", "POST"])
@login_required
def quiz_settings():
    cfg = load_json(QUIZ_BOT_CONFIG_FILE)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "save_settings":
            cfg.update({
                "bot_token": request.form.get("token"), 
                "channel_id": request.form.get("channel_id"),
                "topic_id": request.form.get("topic_id")
            })
            save_json(QUIZ_BOT_CONFIG_FILE, cfg)
            flash("Gespeichert.", "success")
        elif action == "save_schedule":
            cfg["schedule"] = {
                "time": request.form.get("schedule_time"),
                "enabled": "schedule_enabled" in request.form,
                "days": [int(d) for d in request.form.getlist("schedule_days")]
            }
            save_json(QUIZ_BOT_CONFIG_FILE, cfg)
            flash("Zeitplan gespeichert.", "success")
        elif action == "save_questions":
            questions_json = request.form.get("questions_json")
            try:
                json.loads(questions_json)
                with open(QUIZ_FRAGEN_FILE, "w", encoding="utf-8") as f:
                    f.write(questions_json)
                flash("Fragen gespeichert.", "success")
            except json.JSONDecodeError:
                flash("Fehler: Ungültiges JSON-Format.", "danger")
        elif action == "save_asked_questions":
            asked_questions_json = request.form.get("asked_questions_json")
            try:
                asked_questions_list = json.loads(asked_questions_json)
                asked_hashes = [question_fingerprint(q) for q in asked_questions_list]
                save_json(QUIZ_FRAGEN_GESTELLT_FILE, asked_hashes)
                flash("Liste der gestellten Fragen gespeichert.", "success")
            except json.JSONDecodeError:
                flash("Fehler: Ungültiges JSON-Format bei gestellten Fragen.", "danger")
        
        return redirect(url_for("quiz_settings"))

    all_questions = load_json(QUIZ_FRAGEN_FILE, [])
    asked_hashes = load_json(QUIZ_FRAGEN_GESTELLT_FILE, [])
    question_map = {question_fingerprint(q): q for q in all_questions}
    asked_questions_objects = [question_map[h] for h in asked_hashes if h in question_map]
    
    stats = {
        "total": len(all_questions),
        "asked": len(asked_questions_objects),
        "remaining": len(all_questions) - len(asked_questions_objects)
    }
    
    all_questions_json_str = json.dumps(all_questions, indent=4, ensure_ascii=False)
    asked_questions_json_str = json.dumps(asked_questions_objects, indent=4, ensure_ascii=False)

    return render_template(
        "quiz_settings.html",
        config={"quiz": cfg},
        is_running=is_bot_running("quiz"),
        logs=get_bot_logs(QUIZ_BOT_LOG),
        bot_status=build_bot_status(),
        schedule=cfg.get("schedule", {}),
        stats=stats,
        questions_json=all_questions_json_str,
        asked_questions_json=asked_questions_json_str
    )

@app.route("/umfrage-settings", methods=["GET", "POST"])
@login_required
def umfrage_settings():
    cfg = load_json(UMFRAGE_BOT_CONFIG_FILE)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "save_settings":
            cfg.update({
                "bot_token": request.form.get("token"), 
                "channel_id": request.form.get("channel_id"),
                "topic_id": request.form.get("topic_id")
            })
            save_json(UMFRAGE_BOT_CONFIG_FILE, cfg)
            flash("Gespeichert.", "success")
        elif action == "save_schedule":
            cfg["schedule"] = {
                "time": request.form.get("schedule_time"),
                "enabled": "schedule_enabled" in request.form,
                "days": [int(d) for d in request.form.getlist("schedule_days")]
            }
            save_json(UMFRAGE_BOT_CONFIG_FILE, cfg)
            flash("Zeitplan gespeichert.", "success")
        elif action == "save_questions":
            questions_json = request.form.get("questions_json")
            try:
                json.loads(questions_json)
                with open(UMFRAGEN_FILE, "w", encoding="utf-8") as f:
                    f.write(questions_json)
                flash("Umfragen gespeichert.", "success")
            except json.JSONDecodeError:
                flash("Fehler: Ungültiges JSON-Format.", "danger")
        elif action == "save_asked_questions":
            asked_questions_json = request.form.get("asked_questions_json")
            try:
                asked_questions_list = json.loads(asked_questions_json)
                asked_hashes = [question_fingerprint(q) for q in asked_questions_list]
                save_json(UMFRAGEN_GESTELLT_FILE, asked_hashes)
                flash("Liste der gestellten Umfragen gespeichert.", "success")
            except json.JSONDecodeError:
                flash("Fehler: Ungültiges JSON-Format bei gestellten Umfragen.", "danger")

        return redirect(url_for("umfrage_settings"))
    
    all_polls = load_json(UMFRAGEN_FILE, [])
    asked_hashes = load_json(UMFRAGEN_GESTELLT_FILE, [])
    poll_map = {question_fingerprint(p): p for p in all_polls}
    asked_polls_objects = [poll_map[h] for h in asked_hashes if h in poll_map]
    
    stats = {
        "total": len(all_polls),
        "asked": len(asked_polls_objects),
        "remaining": len(all_polls) - len(asked_polls_objects)
    }
    
    all_polls_json_str = json.dumps(all_polls, indent=4, ensure_ascii=False)
    asked_polls_json_str = json.dumps(asked_polls_objects, indent=4, ensure_ascii=False)

    return render_template(
        "umfrage_settings.html",
        config={"umfrage": cfg},
        is_running=is_bot_running("umfrage"),
        logs=get_bot_logs(UMFRAGE_BOT_LOG),
        bot_status=build_bot_status(),
        schedule=cfg.get("schedule", {}),
        stats=stats,
        questions_json=all_polls_json_str,
        asked_questions_json=asked_polls_json_str
    )

@app.route("/umfrage/send-random", methods=["POST"])
@login_required
def umfrage_send_random():
    with open(os.path.join(UMFRAGE_BOT_DIR, "send_now.tmp"), "w") as f:
        f.write("1")
    flash("Befehl zum Senden einer Umfrage gesendet.", "info")
    return redirect(url_for("umfrage_settings"))

@app.route("/quiz/send-random", methods=["POST"])
@login_required
def quiz_send_random():
    with open(os.path.join(QUIZ_BOT_DIR, "send_now.tmp"), "w") as f:
        f.write("1")
    flash("Befehl zum Senden einer Quizfrage gesendet.", "info")
    return redirect(url_for("quiz_settings"))

# Proxy für Avatare
@app.route("/tg/avatar/<user_id>")
@login_required
def tg_avatar_proxy(user_id):
    for folder in ["avatars", "tg_cache/avatars"]:
        path = os.path.join(DATA_DIR, folder, f"{user_id}.jpg")
        if os.path.exists(path): return send_file(path)
    return abort(404)

if __name__ == "__main__": app.run(host="0.0.0.0", port=9002, debug=False)
