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

# Setup a separate logger for critical errors
CRITICAL_ERRORS_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "critical_errors.log")
critical_errors_handler = RotatingFileHandler(CRITICAL_ERRORS_LOG_FILE, maxBytes=10240, backupCount=2)
critical_errors_handler.setLevel(logging.ERROR)
critical_errors_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"))

# Add this handler to the root logger so all errors from any logger go there
logging.getLogger().addHandler(critical_errors_handler)

app = Flask(__name__, template_folder="src")
app.secret_key = "b13f172933b9a1274adb024d47fc7552d2e85864693cb9a2"
app.config["TEMPLATES_AUTO_RELOAD"] = True

# --- Format Filter ---
def format_datetime(value, format="%d.%m.%Y %H:%M:%S"):
    if value is None: return ""
    if isinstance(value, str):
        if not value.strip(): return ""
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    else:
        dt = value
    
    # Convert to Berlin time
    if ZoneInfo:
        dt = dt.astimezone(ZoneInfo("Europe/Berlin"))
    else:
        # Fallback if ZoneInfo is not available (though it is imported)
        dt = dt + timedelta(hours=1) # Approximate if simple offset
    
    return dt.strftime(format)

app.jinja_env.filters['datetimeformat'] = format_datetime

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

# --- In-memory Cache for JSON files ---
FILE_CACHE = {}
CACHE_TTL_SECONDS = 60 # Cache lifetime of 60 seconds

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

    now = time.time()
    if path in FILE_CACHE:
        cached_data, timestamp = FILE_CACHE[path]
        if (now - timestamp) < CACHE_TTL_SECONDS:
            # log.debug(f"Returning cached data for {path}")
            return cached_data
        else:
            # log.debug(f"Cache expired for {path}")
            pass # Cache expired, reload from disk

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            FILE_CACHE[path] = (data, now) # Update cache with new data and timestamp
            return data
    except FileNotFoundError:
        log.warning(f"JSON file not found: {path}")
        return default
    except json.JSONDecodeError as e:
        log.error(f"Error decoding JSON from {path}: {e}")
        return default
    except Exception as e:
        log.error(f"An unexpected error occurred while loading JSON from {path}: {e}")
        return default

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f: json.dump(data, f, indent=4, ensure_ascii=False)
        if path in FILE_CACHE:
            del FILE_CACHE[path] # Invalidate cache for this file
            # log.debug(f"Invalidated cache for {path} after save.")
    except IOError as e:
        log.error(f"Error writing JSON to {path}: {e}")
    except Exception as e:
        log.error(f"An unexpected error occurred while saving JSON to {path}: {e}")

def get_running_processes():
    """Fetch all running python processes to avoid multiple ps calls."""
    try:
        r = subprocess.run(["ps", "auxww"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=True)
        processes = []
        for line in r.stdout.splitlines():
            # Check for python processes
            if "python" in line:
                parts = line.split()
                if len(parts) > 10 and parts[1].isdigit():
                    cmd = " ".join(parts[10:])
                    processes.append(cmd)
        return processes
    except subprocess.CalledProcessError as e:
        log.error(f"Error running ps command: {e}")
        return []
    except FileNotFoundError:
        log.error("The 'ps' command was not found. Is it installed and in the PATH?")
        return []
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
    except FileNotFoundError:
        log.error(f"Python interpreter or bot script not found for {name}.")
        return False, f"Start fehlgeschlagen: Python oder Skript nicht gefunden."
    except Exception as e: 
        log.error(f"Error starting bot {name}: {e}")
        return False, str(e)

def stop_bot_process_by_name(name):
    try:
        subprocess.run(["pkill", "-9", "-f", MATCH_CONFIG[name]["pattern"]], check=True)
        return True, f"{name.capitalize()} Bot gestoppt."
    except subprocess.CalledProcessError as e:
        log.error(f"Error stopping bot {name}: {e}")
        return False, "Fehler beim Stoppen (Prozess existiert möglicherweise nicht oder pkill fehlgeschlagen)."
    except FileNotFoundError:
        log.error("The 'pkill' command was not found. Is it installed and in the PATH?")
        return False, "Fehler beim Stoppen ('pkill' Befehl nicht gefunden)."
    except Exception as e: 
        log.error(f"An unexpected error occurred while stopping bot {name}: {e}")
        return False, "Fehler beim Stoppen."

def _handle_bot_start_stop_action(bot_name, action_type):
    """Handles starting or stopping a bot process and flashes a message."""
    if action_type == "start":
        success, msg = start_bot_process(bot_name)
        flash(msg, "success" if success else "danger")
    elif action_type == "stop":
        success, msg = stop_bot_process_by_name(bot_name)
        flash(msg, "info")

def build_bot_status():
    processes = get_running_processes()
    return {k: {"running": is_bot_running(k, processes)} for k in MATCH_CONFIG}

CRITICAL_LOG_FILE = os.path.join(BASE_DIR, "critical_errors.log")

def get_bot_logs(log_file, lines=100):
    if not os.path.exists(log_file): return []
    try:
        # Use a deque to efficiently store the last 'lines' lines
        # This avoids reading the entire file into memory for large files
        with open(log_file, "r", encoding="utf-8") as f:
            # Using deque with a maxlen automatically discards older entries
            last_lines = deque(f, maxlen=lines)
        return list(reversed(last_lines)) # Reverse to get most recent at top
    except FileNotFoundError:
        log.warning(f"Log file not found: {log_file}")
        return []
    except IOError as e:
        log.error(f"Error reading log file {log_file}: {e}")
        return []
    except Exception as e:
        log.error(f"An unexpected error occurred while reading log file {log_file}: {e}")
        return []

def _parse_dt(s):
    if not s: return None
    try: return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError as e:
        log.warning(f"Could not parse datetime string '{s}': {e}")
        return None
    except Exception as e:
        log.error(f"An unexpected error occurred while parsing datetime '{s}': {e}")
        return None

# --- Analytics Engine ---
# Data Redundancy Note:
# Messages are currently read from `ACTIVITY_LOG_FILE` (global chronological log).
# User-specific messages are read from `USER_MESSAGE_DIR/{uid}.jsonl` for individual user detail pages.
# This creates data redundancy but allows for efficient retrieval of a user's recent messages
# without scanning the entire global activity log, which is beneficial for dashboard performance.
# A more normalized approach would typically involve a database (as suggested in TODO.md).
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
                except json.JSONDecodeError as e:
                    log.error(f"Error decoding JSON from activity log line: {line.strip()}. Error: {e}")
                    continue
                except Exception as e:
                    log.error(f"An unexpected error occurred while processing activity log line: {line.strip()}. Error: {e}")
                    continue
    
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
                except json.JSONDecodeError as e:
                    log.error(f"Error decoding JSON from activity log line: {line.strip()}. Error: {e}")
                    continue
                except Exception as e:
                    log.error(f"An unexpected error occurred while processing activity log line: {line.strip()}. Error: {e}")
                    continue
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
    if bot_name not in MATCH_CONFIG: 
        log.warning(f"Attempted action on unknown bot: {bot_name}")
        flash(f"Unbekannter Bot: {bot_name}.", "danger")
        return redirect(url_for("index"))
    
    # Use the new helper function
    _handle_bot_start_stop_action(bot_name, action)
    
    if action not in ["start", "stop"]:
        log.warning(f"Unknown action '{action}' for bot '{bot_name}'")
        flash(f"Unbekannte Aktion: {action}.", "danger")

    return redirect(request.referrer or url_for("index"))

# New route for critical errors
@app.route("/critical-errors")
@login_required
def critical_errors():
    try:
        critical_logs = get_bot_logs(CRITICAL_LOG_FILE)
        return render_template("critical_errors.html", critical_logs=critical_logs, bot_status=build_bot_status())
    except Exception as e:
        log.error(f"Error loading critical errors page: {e}")
        flash(f"Fehler beim Laden der kritischen Fehler: {e}", "danger")
        return redirect(url_for("index"))

@app.route("/critical-errors/clear", methods=["POST"])
@login_required
def clear_critical_errors():
    try:
        with open(CRITICAL_ERRORS_LOG_FILE, "w") as f:
            f.write("")
        flash("Kritische Fehlerprotokolle wurden gelöscht.", "success")
        log.info("Critical errors log file has been cleared by user.")
    except IOError as e:
        log.error(f"Error clearing critical errors log file: {e}")
        flash(f"Fehler beim Löschen der Protokolle: {e}", "danger")
    except Exception as e:
        log.error(f"An unexpected error occurred while clearing critical logs: {e}")
        flash(f"Ein unerwarteter Fehler ist aufgetreten: {e}", "danger")
    return redirect(url_for("critical_errors"))

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
    try:
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
    except ValueError as e:
        log.error(f"Invalid integer value in ID Finder config form: {e}")
        flash(f"Fehler beim Speichern der Konfiguration: Ungültige Zahleneingabe. {e}", "danger")
    except Exception as e:
        log.error(f"Error saving ID Finder configuration: {e}")
        flash(f"Fehler beim Speichern der Konfiguration: {e}", "danger")
    return redirect(url_for("id_finder_dashboard"))

@app.route("/id-finder/delete-user/<user_id>", methods=["POST"])
@login_required
def id_finder_delete_user(user_id):
    try:
        reg = load_json(USER_REGISTRY_FILE, {"users": {}})
        if str(user_id) in reg.get("users", {}):
            del reg["users"][str(user_id)]; save_json(USER_REGISTRY_FILE, reg)
            flash(f"User {user_id} gelöscht.", "info")
        else:
            flash(f"User {user_id} nicht gefunden.", "warning")
    except Exception as e:
        log.error(f"Error deleting user {user_id} from ID Finder: {e}")
        flash(f"Fehler beim Löschen des Users: {e}", "danger")
    return redirect(url_for("id_finder_dashboard"))

@app.route("/id-finder/analytics")
@login_required
def id_finder_analytics():
    try:
        reg = load_json(USER_REGISTRY_FILE, {"users": {}})
        msg_counts = get_all_user_msg_counts()
        users = []; unique_chats = set(); latest_user = None
        for uid, udata in reg.get("users", {}).items():
            udata["id"] = uid
            udata["msg_count"] = msg_counts.get(str(uid), 0)
            users.append(udata)
        chat_counts = defaultdict(int)
        for u in users:
            for c in (u.get("chat_ids") or u.get("groups_seen") or []): chat_counts[str(c)] += 1
        stats = {"total_users": len(users), "unique_chats": len(unique_chats), "most_recent_user": latest_user, "top_chats": sorted(chat_counts.items(), key=lambda x: x[1], reverse=True)[:10]}
        activity_data = build_group_activity(days=request.args.get("days"), month=request.args.get("month"), year=request.args.get("year"))
        return render_template("id_finder_analytics.html", activity=activity_data, stats=stats, user_registry=sorted(users, key=lambda x: x.get("last_seen", ""), reverse=True), bot_status=build_bot_status())
    except Exception as e:
        log.error(f"Error in ID Finder analytics page: {e}")
        flash(f"Fehler beim Laden der Analysedaten: {e}", "danger")
        return redirect(url_for("id_finder_dashboard"))

@app.route("/api/id-finder/user-activity/<user_id>")
@login_required
def api_id_finder_user_activity(user_id):
    try:
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
                    except json.JSONDecodeError as e:
                        log.error(f"Error decoding JSON for user activity from activity log line: {line.strip()}. Error: {e}")
                        continue
                    except Exception as e:
                        log.error(f"An unexpected error occurred while processing user activity log line: {line.strip()}. Error: {e}")
                        continue
        return jsonify({"timeline": [user_timeline[label] for label in activity["timeline"]["labels"]], "hours": user_hours, "weekdays": user_weekdays})
    except Exception as e:
        log.error(f"Error in API for ID Finder user activity for user {user_id}: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/id-finder/user/<user_id>")
@login_required
def id_finder_user_detail(user_id):
    try:
        reg = load_json(USER_REGISTRY_FILE, {"users": {}})
        user = reg.get("users", {}).get(str(user_id))
        if not user: 
            flash(f"User {user_id} nicht gefunden.", "warning")
            return redirect(url_for("id_finder_dashboard"))
        user["id"] = user_id; messages = []
        log_file = os.path.join(USER_MESSAGE_DIR, f"{user_id}.jsonl")
        if os.path.exists(log_file):
            # Use deque for efficient reading of last N messages
            with open(log_file, "r", encoding="utf-8") as f:
                last_messages_raw = deque(f, maxlen=200)
            for line in last_messages_raw:
                try: messages.append(json.loads(line))
                except json.JSONDecodeError as e:
                    log.error(f"Error decoding JSON from user message log line: {line.strip()}. Error: {e}")
                    continue
                except Exception as e:
                    log.error(f"An unexpected error occurred while processing user message log line: {line.strip()}. Error: {e}")
                    continue
        return render_template("id_finder_user_detail.html", user=user, messages=list(reversed(messages)), bot_status=build_bot_status())
    except Exception as e:
        log.error(f"Error in ID Finder user detail page for user {user_id}: {e}")
        flash(f"Fehler beim Laden der User-Details: {e}", "danger")
        return redirect(url_for("id_finder_dashboard"))

@app.route("/id-finder/commands")
@login_required
def id_finder_commands(): 
    try:
        return render_template("id_finder_commands.html", bot_status=build_bot_status())
    except Exception as e:
        log.error(f"Error loading ID Finder commands page: {e}")
        flash(f"Fehler beim Laden der Befehlsseite: {e}", "danger")
        return redirect(url_for("index"))

@app.route("/id-finder/admin-panel")
@login_required
def id_finder_admin_panel(): 
    try:
        return render_template("id_finder_admin_panel.html", admins=load_json(ADMINS_FILE), available_permissions=AVAILABLE_PERMISSIONS, bot_status=build_bot_status())
    except Exception as e:
        log.error(f"Error loading ID Finder admin panel page: {e}")
        flash(f"Fehler beim Laden des Admin-Panels: {e}", "danger")
        return redirect(url_for("index"))

@app.route("/id-finder/add-admin", methods=["POST"])
@login_required
def id_finder_add_admin():
    try:
        admins = load_json(ADMINS_FILE); uid = request.form.get("admin_id").strip()
        if uid:
            admins[uid] = {"name": request.form.get("admin_name"), "permissions": {k: True for k in AVAILABLE_PERMISSIONS}}
            save_json(ADMINS_FILE, admins)
            flash("Admin hinzugefügt.", "success")
        else:
            flash("Admin ID darf nicht leer sein.", "warning")
    except Exception as e:
        log.error(f"Error adding admin: {e}")
        flash(f"Fehler beim Hinzufügen des Admins: {e}", "danger")
    return redirect(url_for("id_finder_admin_panel"))

@app.route("/id-finder/delete-admin", methods=["POST"])
@login_required
def id_finder_delete_admin():
    try:
        admins = load_json(ADMINS_FILE); uid = request.form.get("admin_id")
        if uid in admins:
            del admins[uid]
            save_json(ADMINS_FILE, admins)
            flash("Admin gelöscht.", "info")
        else:
            flash("Admin nicht gefunden.", "warning")
    except Exception as e:
        log.error(f"Error deleting admin {uid}: {e}")
        flash(f"Fehler beim Löschen des Admins: {e}", "danger")
    return redirect(url_for("id_finder_admin_panel"))

@app.route("/id-finder/update-admin-permissions", methods=["POST"])
@login_required
def id_finder_update_admin_permissions():
    try:
        admins = load_json(ADMINS_FILE); uid = request.form.get("admin_id")
        if uid in admins:
            admins[uid]["permissions"] = {p: (p in request.form) for p in AVAILABLE_PERMISSIONS}
            save_json(ADMINS_FILE, admins)
            flash("Rechte aktualisiert.", "success")
        else:
            flash("Admin nicht gefunden.", "warning")
    except Exception as e:
        log.error(f"Error updating permissions for admin {uid}: {e}")
        flash(f"Fehler beim Aktualisieren der Rechte: {e}", "danger")
    return redirect(url_for("id_finder_admin_panel"))

# --- 👋 EINLADUNGS-BOT ---
@app.route("/bot-settings", methods=["GET", "POST"])
@login_required
def bot_settings(): 
    try:
        if request.method == "POST":
            action = request.form.get("action")
            if action == "start_invite_bot":
                _handle_bot_start_stop_action("invite", "start")
            elif action == "stop_invite_bot":
                _handle_bot_start_stop_action("invite", "stop")
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
            else:
                log.warning(f"Unknown action '{action}' in bot settings (POST)")
                flash(f"Unbekannte Aktion: {action}.", "danger")
            return redirect(url_for("bot_settings"))
        return render_template("bot_settings.html", config=load_json(INVITE_BOT_CONFIG_FILE), is_invite_running=is_bot_running("invite"), invite_bot_logs=get_bot_logs(INVITE_BOT_LOG), user_interaction_logs=get_bot_logs(INVITE_BOT_USER_LOG), bot_status=build_bot_status())
    except ValueError as e:
        log.error(f"Invalid integer value in Invite Bot config form: {e}")
        flash(f"Fehler beim Speichern der Konfiguration: Ungültige Zahleneingabe. {e}", "danger")
        return redirect(url_for("bot_settings"))
    except Exception as e:
        log.error(f"Error in bot settings page: {e}")
        flash(f"Fehler beim Laden oder Speichern der Bot-Einstellungen: {e}", "danger")
        return redirect(url_for("index"))

@app.route("/bot-settings/save-content", methods=["POST"])
@login_required
def save_invite_bot_content():
    try:
        cfg = load_json(INVITE_BOT_CONFIG_FILE)
        cfg.update({
            "start_message": request.form.get("start_message"),
            "rules_message": request.form.get("rules_message"),
            "blocked_message": request.form.get("blocked_message"),
            "privacy_policy": request.form.get("privacy_policy")
        })
        save_json(INVITE_BOT_CONFIG_FILE, cfg)
        flash("Texte gespeichert.", "success")
    except Exception as e:
        log.error(f"Error saving Invite Bot content: {e}")
        flash(f"Fehler beim Speichern der Texte: {e}", "danger")
    return redirect(url_for("bot_settings"))

@app.route("/bot-settings/add-field", methods=["POST"])
@login_required
def add_invite_bot_field():
    try:
        cfg = load_json(INVITE_BOT_CONFIG_FILE, {"form_fields": []})
        min_age = None
        if request.form.get("min_age"):
            try: min_age = int(request.form.get("min_age"))
            except ValueError:
                flash("Ungültiges Alter eingegeben.", "danger")
                return redirect(url_for("bot_settings"))
            
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
    except Exception as e:
        log.error(f"Error adding Invite Bot field: {e}")
        flash(f"Fehler beim Hinzufügen des Feldes: {e}", "danger")
    return redirect(url_for("bot_settings"))

@app.route("/bot-settings/edit-field", methods=["POST"])
@login_required
def edit_invite_bot_field():
    try:
        cfg = load_json(INVITE_BOT_CONFIG_FILE, {"form_fields": []}); fid = request.form.get("field_id")
        found = False
        for f in cfg["form_fields"]:
            if f["id"] == fid:
                found = True
                min_age = None
                if request.form.get("min_age"):
                    try: min_age = int(request.form.get("min_age"))
                    except ValueError:
                        flash("Ungültiges Alter eingegeben.", "danger")
                        return redirect(url_for("bot_settings"))
                    
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
        if found:
            save_json(INVITE_BOT_CONFIG_FILE, cfg); flash("Feld aktualisiert.", "success")
        else:
            flash("Feld nicht gefunden.", "warning")
    except Exception as e:
        log.error(f"Error editing Invite Bot field {fid}: {e}")
        flash(f"Fehler beim Aktualisieren des Feldes: {e}", "danger")
    return redirect(url_for("bot_settings"))

@app.route("/bot-settings/delete-field", methods=["POST"])
@login_required
def delete_invite_bot_field():
    try:
        cfg = load_json(INVITE_BOT_CONFIG_FILE, {"form_fields": []}); fid = request.form.get("field_id")
        initial_len = len(cfg["form_fields"])
        cfg["form_fields"] = [f for f in cfg["form_fields"] if f["id"] != fid]
        if len(cfg["form_fields"]) < initial_len:
            save_json(INVITE_BOT_CONFIG_FILE, cfg); flash("Feld gelöscht.", "info")
        else:
            flash("Feld nicht gefunden.", "warning")
    except Exception as e:
        log.error(f"Error deleting Invite Bot field {fid}: {e}")
        flash(f"Fehler beim Löschen des Feldes: {e}", "danger")
    return redirect(url_for("bot_settings"))

@app.route("/invite-bot-move-field/<field_id>/<direction>")
@login_required
def invite_bot_move_field(field_id, direction):
    try:
        cfg = load_json(INVITE_BOT_CONFIG_FILE, {"form_fields": []}); f = cfg["form_fields"]; i = next((idx for idx, x in enumerate(f) if x["id"] == field_id), -1)
        if i != -1:
            if direction == "up" and i > 0: f[i], f[i-1] = f[i-1], f[i]
            elif direction == "down" and i < len(f)-1: f[i], f[i+1] = f[i+1], f[i]
            save_json(INVITE_BOT_CONFIG_FILE, cfg); flash("Feld verschoben.", "success")
        else:
            flash("Feld nicht gefunden.", "warning")
    except Exception as e:
        log.error(f"Error moving Invite Bot field {field_id} {direction}: {e}")
        flash(f"Fehler beim Verschieben des Feldes: {e}", "danger")
    return redirect(url_for("bot_settings"))

@app.route("/bot-settings/clear-logs/<log_type>", methods=["POST"])
@login_required
def clear_invite_bot_logs(log_type):
    try:
        if log_type == "user":
            with open(INVITE_BOT_USER_LOG, "w") as f: f.write("")
            flash("User Logs gelöscht.", "info")
        elif log_type == "system":
            with open(INVITE_BOT_LOG, "w") as f: f.write("")
            flash("System Logs gelöscht.", "info")
        else:
            flash("Unbekannter Log-Typ.", "warning")
            log.warning(f"Attempted to clear unknown log type: {log_type}")
    except IOError as e:
        log.error(f"Error clearing {log_type} logs: {e}")
        flash(f"Fehler beim Löschen der Logs: {e}", "danger")
    except Exception as e:
        log.error(f"An unexpected error occurred while clearing {log_type} logs: {e}")
        flash(f"Fehler beim Löschen der Logs: {e}", "danger")
    return redirect(url_for("bot_settings"))

# --- 📢 NACHRICHT PLANER ---
@app.route("/broadcast")
@login_required
def broadcast_manager(): 
    try:
        return render_template("broadcast_manager.html", broadcasts=load_json(BROADCAST_DATA_FILE, []), bot_status=build_bot_status(), known_topics=load_json(TOPIC_REGISTRY_FILE, {}))
    except Exception as e:
        log.error(f"Error loading broadcast manager page: {e}")
        flash(f"Fehler beim Laden des Broadcast Managers: {e}", "danger")
        return redirect(url_for("index"))

@app.route("/broadcast/save", methods=["POST"])
@login_required
def save_broadcast():
    try:
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
            media_name = f"{uuid.uuid4().hex[:8]}_{media_file.filename}"
            media_file.save(os.path.join(upload_dir, media_name))

        new_b = {"id": str(uuid.uuid4().hex[:8]), "text": text, "topic_id": topic_id, "send_mode": send_mode, "media_name": media_name, "scheduled_at": scheduled_at if action == "schedule" else None, "pin_message": pin_message, "silent_send": silent_send, "status": "pending", "created_at": datetime.now().isoformat()}
        b_list.append(new_b); save_json(BROADCAST_DATA_FILE, b_list); flash("Broadcast gespeichert.", "success")
    except Exception as e:
        log.error(f"Error saving broadcast: {e}")
        flash(f"Fehler beim Speichern des Broadcasts: {e}", "danger")
    return redirect(url_for("broadcast_manager"))

@app.route("/broadcast/topics/save", methods=["POST"])
@login_required
def save_topic_mapping():
    try:
        t = load_json(TOPIC_REGISTRY_FILE, {}); t[request.form.get("topic_id")] = request.form.get("topic_name"); save_json(TOPIC_REGISTRY_FILE, t)
        flash("Topic gespeichert.", "success")
    except Exception as e:
        log.error(f"Error saving topic mapping: {e}")
        flash(f"Fehler beim Speichern des Topics: {e}", "danger")
    return redirect(url_for("broadcast_manager"))

@app.route("/broadcast/delete/<broadcast_id>", methods=["POST"])
@login_required
def delete_broadcast(broadcast_id):
    try:
        b = [x for x in load_json(BROADCAST_DATA_FILE, []) if x.get("id") != broadcast_id]; save_json(BROADCAST_DATA_FILE, b); flash("Eintrag gelöscht.", "info")
    except Exception as e:
        log.error(f"Error deleting broadcast {broadcast_id}: {e}")
        flash(f"Fehler beim Löschen des Eintrags: {e}", "danger")
    return redirect(url_for("broadcast_manager"))

@app.route("/broadcast/topics/delete/<topic_id>", methods=["POST"])
@login_required
def delete_topic_mapping(topic_id):
    try:
        t = load_json(TOPIC_REGISTRY_FILE, {}); 
        if topic_id in t: del t[topic_id]
        save_json(TOPIC_REGISTRY_FILE, t); flash("Topic gelöscht.", "info")
    except Exception as e:
        log.error(f"Error deleting topic mapping {topic_id}: {e}")
        flash(f"Fehler beim Löschen des Topics: {e}", "danger")
    return redirect(url_for("broadcast_manager"))

# --- 👗 OUTFIT BOT ---
@app.route("/outfit-bot/dashboard")
@login_required
def outfit_bot_dashboard(): 
    try:
        return render_template("outfit_bot_dashboard.html", config=load_json(OUTFIT_BOT_CONFIG_FILE), is_running=is_bot_running("outfit"), logs=get_bot_logs(OUTFIT_BOT_LOG), bot_status=build_bot_status(), duel_status={"active": False})
    except Exception as e:
        log.error(f"Error loading Outfit Bot dashboard: {e}")
        flash(f"Fehler beim Laden des Outfit Bot Dashboards: {e}", "danger")
        return redirect(url_for("index"))

@app.route("/outfit-bot/save-config", methods=["POST"])
@login_required
def outfit_bot_save_config():
    try:
        cfg = load_json(OUTFIT_BOT_CONFIG_FILE); cfg.update({"BOT_TOKEN": request.form.get("BOT_TOKEN"), "CHAT_ID": request.form.get("CHAT_ID"), "AUTO_POST_ENABLED": "AUTO_POST_ENABLED" in request.form}); save_json(OUTFIT_BOT_CONFIG_FILE, cfg); flash("Outfit Konfiguration gespeichert.", "success")
    except Exception as e:
        log.error(f"Error saving Outfit Bot config: {e}")
        flash(f"Fehler beim Speichern der Outfit Konfiguration: {e}", "danger")
    return redirect(url_for("outfit_bot_dashboard"))

@app.route("/outfit-bot/start-contest", methods=["POST"])
@login_required
def outfit_bot_start_contest():
    try:
        with open(os.path.join(OUTFIT_BOT_DIR, "command_start_contest.tmp"), "w") as f: f.write("1")
        flash("Befehl gesendet.", "info")
    except IOError as e:
        log.error(f"Error writing start contest command file: {e}")
        flash(f"Fehler beim Senden des Befehls: {e}", "danger")
    except Exception as e:
        log.error(f"An unexpected error occurred while starting contest: {e}")
        flash(f"Fehler beim Senden des Befehls: {e}", "danger")
    return redirect(url_for("outfit_bot_dashboard"))

@app.route("/outfit-bot/announce-winner", methods=["POST"])
@login_required
def outfit_bot_announce_winner():
    try:
        with open(os.path.join(OUTFIT_BOT_DIR, "command_announce_winner.tmp"), "w") as f: f.write("1")
        flash("Befehl gesendet.", "info")
    except IOError as e:
        log.error(f"Error writing announce winner command file: {e}")
        flash(f"Fehler beim Senden des Befehls: {e}", "danger")
    except Exception as e:
        log.error(f"An unexpected error occurred while announcing winner: {e}")
        flash(f"Fehler beim Senden des Befehls: {e}", "danger")
    return redirect(url_for("outfit_bot_dashboard"))

@app.route("/outfit-bot/end-duel", methods=["POST"])
@login_required
def outfit_bot_end_duel():
    try:
        with open(os.path.join(OUTFIT_BOT_DIR, "command_end_duel.tmp"), "w") as f: f.write("1")
        flash("Befehl gesendet.", "info")
    except IOError as e:
        log.error(f"Error writing end duel command file: {e}")
        flash(f"Fehler beim Senden des Befehls: {e}", "danger")
    except Exception as e:
        log.error(f"An unexpected error occurred while ending duel: {e}")
        flash(f"Fehler beim Senden des Befehls: {e}", "danger")
    return redirect(url_for("outfit_bot_dashboard"))

@app.route("/outfit-bot/clear-logs", methods=["POST"])
@login_required
def outfit_bot_clear_logs():
    try:
        with open(OUTFIT_BOT_LOG, "w") as f: f.write("")
        flash("Logs gelöscht.", "info")
    except IOError as e:
        log.error(f"Error clearing Outfit Bot logs: {e}")
        flash(f"Fehler beim Löschen der Logs: {e}", "danger")
    except Exception as e:
        log.error(f"An unexpected error occurred while clearing Outfit Bot logs: {e}")
        flash(f"Fehler beim Löschen der Logs: {e}", "danger")
    return redirect(url_for("outfit_bot_dashboard"))

# --- 👥 BENUTZERVERWALTUNG ---
@app.route("/admin/users")
@login_required
def manage_users(): 
    try:
        return render_template("manage_users.html", users=load_json(USERS_FILE, {}))
    except Exception as e:
        log.error(f"Error loading manage users page: {e}")
        flash(f"Fehler beim Laden der Benutzerverwaltung: {e}", "danger")
        return redirect(url_for("index"))

@app.route("/admin/users/add", methods=["POST"])
@login_required
def add_user():
    try:
        u = load_json(USERS_FILE, {}); name = request.form.get("username").strip()
        password = request.form.get("password")
        role = request.form.get("role")
        if not name or not password or not role:
            flash("Alle Felder müssen ausgefüllt werden.", "warning")
            return redirect(url_for("manage_users"))
        if name in u:
            flash("Benutzername existiert bereits.", "warning")
            return redirect(url_for("manage_users"))
        u[name] = {"password": generate_password_hash(password), "role": role}
        save_json(USERS_FILE, u)
        flash("Benutzer hinzugefügt.", "success")
    except Exception as e:
        log.error(f"Error adding user: {e}")
        flash(f"Fehler beim Hinzufügen des Benutzers: {e}", "danger")
    return redirect(url_for("manage_users"))

@app.route("/admin/users/edit/<username>", methods=["POST"])
@login_required
def edit_user(username):
    try:
        u = load_json(USERS_FILE, {}); 
        if username not in u:
            flash("Benutzer nicht gefunden.", "warning")
            return redirect(url_for("manage_users"))
        data = u.pop(username); new_name = request.form.get("new_username") or username; 
        if request.form.get("new_password"): data["password"] = generate_password_hash(request.form.get("new_password"))
        data["role"] = request.form.get("new_role"); u[new_name] = data; save_json(USERS_FILE, u)
        flash("Benutzer aktualisiert.", "success")
    except Exception as e:
        log.error(f"Error editing user {username}: {e}")
        flash(f"Fehler beim Aktualisieren des Benutzers: {e}", "danger")
    return redirect(url_for("manage_users"))

@app.route("/admin/users/delete/<username>", methods=["POST"])
@login_required
def delete_user(username):
    try:
        u = load_json(USERS_FILE, {}); 
        if username not in u:
            flash("Benutzer nicht gefunden.", "warning")
            return redirect(url_for("manage_users"))
        if username in u and username != session.get("user"): 
            del u[username]; save_json(USERS_FILE, u)
            flash("Benutzer gelöscht.", "info")
        elif username == session.get("user"):
            flash("Sie können sich nicht selbst löschen.", "warning")
    except Exception as e:
        log.error(f"Error deleting user {username}: {e}")
        flash(f"Fehler beim Löschen des Benutzers: {e}", "danger")
    return redirect(url_for("manage_users"))

# --- ⛏️ MINECRAFT ---
@app.route("/minecraft")
@login_required
def minecraft_status_page():
    try:
        cache = load_json(MINECRAFT_STATUS_CACHE_FILE)
        return render_template("minecraft.html", cfg=load_json(MINECRAFT_STATUS_CONFIG_FILE), status=cache.get("status", {}), pi=cache.get("pi_metrics", {}), server_online=cache.get("status", {}).get("online", False), bot_status=build_bot_status(), is_running=is_bot_running("id_finder"))
    except Exception as e:
        log.error(f"Error loading Minecraft status page: {e}")
        flash(f"Fehler beim Laden der Minecraft Statusseite: {e}", "danger")
        return redirect(url_for("index"))

@app.route("/minecraft/save", methods=["POST"])
@login_required
def minecraft_status_save():
    try:
        cfg = load_json(MINECRAFT_STATUS_CONFIG_FILE); cfg.update({"mc_host": request.form.get("mc_host"), "mc_port": int(request.form.get("mc_port", 25565))}); save_json(MINECRAFT_STATUS_CONFIG_FILE, cfg)
        flash("Minecraft Konfiguration gespeichert.", "success")
    except ValueError as e:
        log.error(f"Invalid port value in Minecraft config form: {e}")
        flash(f"Fehler beim Speichern der Minecraft Konfiguration: Ungültiger Port. {e}", "danger")
    except Exception as e:
        log.error(f"Error saving Minecraft status config: {e}")
        flash(f"Fehler beim Speichern der Minecraft Konfiguration: {e}", "danger")
    return redirect(url_for("minecraft_status_page"))

@app.route("/minecraft/start", methods=["POST"])
@login_required
def minecraft_status_start(): 
    flash("Überwachung an.", "success"); 
    return redirect(url_for("minecraft_status_page"))

@app.route("/minecraft/stop", methods=["POST"])
@login_required
def minecraft_status_stop(): 
    flash("Überwachung aus.", "info"); 
    return redirect(url_for("minecraft_status_page"))

@app.route("/minecraft/reset-message", methods=["POST"])
@login_required
def minecraft_status_reset_message():
    try:
        config = load_json(MINECRAFT_STATUS_CONFIG_FILE)
        if "last_posted_message_id" in config:
            del config["last_posted_message_id"]
            save_json(MINECRAFT_STATUS_CONFIG_FILE, config)
            flash("ID der Minecraft-Statusnachricht wurde zurückgesetzt.", "success")
            log.info("Minecraft status message ID has been reset by user.")
        else:
            flash("Es war keine ID für eine Minecraft-Statusnachricht zum Zurücksetzen vorhanden.", "info")
    except Exception as e:
        log.error(f"Error resetting Minecraft status message: {e}")
        flash(f"Fehler beim Zurücksetzen der Nachricht: {e}", "danger")
    return redirect(url_for("minecraft_status_page"))

# --- QUIZ & UMFRAGE ---
def question_fingerprint(q: dict) -> str:
    try:
        frage = str(q.get("frage", "")).strip()
        optionen = q.get("optionen", [])
        if not isinstance(optionen, list):
            log.warning(f"'optionen' in quiz question is not a list: {q}")
            optionen = []
        payload = frage + "||" + "||".join([str(x).strip() for x in sorted(optionen)])
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()
    except Exception as e:
        log.error(f"Error generating question fingerprint for {q}: {e}")
        return ""

@app.route("/quiz-settings", methods=["GET", "POST"])
@login_required
def quiz_settings():
    cfg = load_json(QUIZ_BOT_CONFIG_FILE)
    if request.method == "POST":
        action = request.form.get("action")
        try:
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
                json.loads(questions_json) # Validate JSON
                with open(QUIZ_FRAGEN_FILE, "w", encoding="utf-8") as f:
                    f.write(questions_json)
                flash("Fragen gespeichert.", "success")
            elif action == "save_asked_questions":
                asked_questions_json = request.form.get("asked_questions_json")
                asked_questions_list = json.loads(asked_questions_json) # Validate JSON
                asked_hashes = [question_fingerprint(q) for q in asked_questions_list]
                save_json(QUIZ_FRAGEN_GESTELLT_FILE, asked_hashes)
                flash("Liste der gestellten Fragen gespeichert.", "success")
            else:
                log.warning(f"Unknown action '{action}' in quiz settings (POST)")
                flash(f"Unbekannte Aktion: {action}.", "danger")
        except json.JSONDecodeError:
            flash("Fehler: Ungültiges JSON-Format.", "danger")
            log.error(f"Invalid JSON format provided in quiz settings for action '{action}'.")
        except ValueError as e:
            flash(f"Fehler: Ungültige Zahleneingabe für Zeitplan. {e}", "danger")
            log.error(f"Invalid integer value in quiz schedule form: {e}")
        except IOError as e:
            flash(f"Fehler beim Speichern der Quizfragen: {e}", "danger")
            log.error(f"Error writing quiz questions file: {e}")
        except Exception as e:
            flash(f"Fehler beim Speichern der Quiz-Einstellungen: {e}", "danger")
            log.error(f"Error saving quiz settings for action '{action}': {e}")
        
        return redirect(url_for("quiz_settings"))

    try:
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
    except Exception as e:
        log.error(f"Error loading quiz settings page: {e}")
        flash(f"Fehler beim Laden der Quiz-Einstellungen: {e}", "danger")
        return redirect(url_for("index"))

@app.route("/umfrage-settings", methods=["GET", "POST"])
@login_required
def umfrage_settings():
    cfg = load_json(UMFRAGE_BOT_CONFIG_FILE)
    if request.method == "POST":
        action = request.form.get("action")
        try:
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
                json.loads(questions_json) # Validate JSON
                with open(UMFRAGEN_FILE, "w", encoding="utf-8") as f:
                    f.write(questions_json)
                flash("Umfragen gespeichert.", "success")
            elif action == "save_asked_questions":
                asked_questions_json = request.form.get("asked_questions_json")
                asked_questions_list = json.loads(asked_questions_json) # Validate JSON
                asked_hashes = [question_fingerprint(q) for q in asked_questions_list]
                save_json(UMFRAGEN_GESTELLT_FILE, asked_hashes)
                flash("Liste der gestellten Umfragen gespeichert.", "success")
            else:
                log.warning(f"Unknown action '{action}' in umfrage settings (POST)")
                flash(f"Unbekannte Aktion: {action}.", "danger")
        except json.JSONDecodeError:
            flash("Fehler: Ungültiges JSON-Format.", "danger")
            log.error(f"Invalid JSON format provided in umfrage settings for action '{action}'.")
        except ValueError as e:
            flash(f"Fehler: Ungültige Zahleneingabe für Zeitplan. {e}", "danger")
            log.error(f"Invalid integer value in umfrage schedule form: {e}")
        except IOError as e:
            flash(f"Fehler beim Speichern der Umfragen: {e}", "danger")
            log.error(f"Error writing umfrage questions file: {e}")
        except Exception as e:
            flash(f"Fehler beim Speichern der Umfrage-Einstellungen: {e}", "danger")
            log.error(f"Error saving umfrage settings for action '{action}': {e}")

        return redirect(url_for("umfrage_settings"))
    
    try:
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
    except Exception as e:
        log.error(f"Error loading umfrage settings page: {e}")
        flash(f"Fehler beim Laden der Umfrage-Einstellungen: {e}", "danger")
        return redirect(url_for("index"))

@app.route("/umfrage/send-random", methods=["POST"])
@login_required
def umfrage_send_random():
    try:
        with open(os.path.join(UMFRAGE_BOT_DIR, "send_now.tmp"), "w") as f:
            f.write("1")
        flash("Befehl zum Senden einer Umfrage gesendet.", "info")
    except IOError as e:
        log.error(f"Error writing umfrage send_now.tmp file: {e}")
        flash(f"Fehler beim Senden des Befehls: {e}", "danger")
    except Exception as e:
        log.error(f"An unexpected error occurred while sending random umfrage: {e}")
        flash(f"Fehler beim Senden des Befehls: {e}", "danger")
    return redirect(url_for("umfrage_settings"))

@app.route("/quiz/send-random", methods=["POST"])
@login_required
def quiz_send_random():
    try:
        with open(os.path.join(QUIZ_BOT_DIR, "send_now.tmp"), "w") as f:
            f.write("1")
        flash("Befehl zum Senden einer Quizfrage gesendet.", "info")
    except IOError as e:
        log.error(f"Error writing quiz send_now.tmp file: {e}")
        flash(f"Fehler beim Senden des Befehls: {e}", "danger")
    except Exception as e:
        log.error(f"An unexpected error occurred while sending random quiz: {e}")
        flash(f"Fehler beim Senden des Befehls: {e}", "danger")
    return redirect(url_for("quiz_settings"))

# Proxy für Avatare
@app.route("/tg/avatar/<user_id>")
@login_required
def tg_avatar_proxy(user_id):
    try:
        for folder in ["avatars", "tg_cache/avatars"]:
            path = os.path.join(DATA_DIR, folder, f"{user_id}.jpg")
            if os.path.exists(path): return send_file(path)
        log.warning(f"Avatar for user {user_id} not found.")
        return abort(404)
    except Exception as e:
        log.error(f"Error serving avatar for user {user_id}: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__": app.run(host="0.0.0.0", port=9002, debug=False)
