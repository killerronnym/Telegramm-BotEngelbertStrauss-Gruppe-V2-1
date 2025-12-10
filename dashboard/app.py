
import os
import random
import json
import asyncio
import logging
from logging.handlers import RotatingFileHandler
import atexit
import threading
import subprocess
from datetime import datetime
import hashlib
from functools import wraps
from urllib.parse import urlparse
import uuid
import sys

from flask import Flask, render_template, request, flash, redirect, url_for, session, make_response
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import TelegramError
from apscheduler.schedulers.background import BackgroundScheduler
import pytz

# --- Logging (Global & App) ---
# Konfiguriere Logging so, dass es auf STDOUT schreibt
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]',
    handlers=[
        RotatingFileHandler('app.log', maxBytes=10240, backupCount=5),
        logging.StreamHandler(sys.stdout)
    ],
    force=True
)
log = logging.getLogger(__name__)

# --- Flask App Initialisierung ---
app = Flask(__name__, template_folder='src')
app.secret_key = 'b13f172933b9a1274adb024d47fc7552d2e85864693cb9a2' 
app.config['TEMPLATES_AUTO_RELOAD'] = True

# --- Globale Variablen & Dateipfade ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
USERS_FILE = os.path.join(BASE_DIR, 'users.json')

# Spezifische Log-Dateien
QUIZ_LOG_FILE = os.path.join(BASE_DIR, 'quiz_log.log')
UMFRAGE_LOG_FILE = os.path.join(BASE_DIR, 'umfrage_log.log')

OUTFIT_BOT_DIR = os.path.join(PROJECT_ROOT, 'outfit_bot')
OUTFIT_BOT_CONFIG_FILE = os.path.join(OUTFIT_BOT_DIR, 'outfit_bot_config.json')
OUTFIT_BOT_SCRIPT = os.path.join(OUTFIT_BOT_DIR, 'outfit_bot.py')
OUTFIT_BOT_LOG = os.path.join(OUTFIT_BOT_DIR, 'outfit_bot.log')

INVITE_BOT_DIR = os.path.join(PROJECT_ROOT, 'invite_bot')
BOT_SETTINGS_CONFIG_FILE = os.path.join(INVITE_BOT_DIR, 'bot_settings_config.json')
INVITE_BOT_SCRIPT = os.path.join(INVITE_BOT_DIR, 'invite_bot.py')
INVITE_BOT_LOG = os.path.join(INVITE_BOT_DIR, 'invite_bot.log')
USER_INTERACTIONS_LOG_FILE = os.path.join(INVITE_BOT_DIR, 'user_interactions.log')

ID_FINDER_BOT_DIR = os.path.join(PROJECT_ROOT, 'id_finder_bot')
ID_FINDER_CONFIG_FILE = os.path.join(ID_FINDER_BOT_DIR, 'id_finder_config.json')
ID_FINDER_BOT_SCRIPT = os.path.join(ID_FINDER_BOT_DIR, 'id_finder_bot.py')
ID_FINDER_BOT_LOG = os.path.join(ID_FINDER_BOT_DIR, 'id_finder_bot.log')
ID_FINDER_COMMAND_LOG = os.path.join(ID_FINDER_BOT_DIR, 'id_finder_command.log')

DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
QUIZFRAGEN_FILE = os.path.join(DATA_DIR, 'quizfragen.json')
GESTELLTE_QUIZFRAGEN_FILE = os.path.join(DATA_DIR, 'gestellte_quizfragen.json')
UMFRAGEN_FILE = os.path.join(DATA_DIR, 'umfragen.json')
GESTELLTE_UMFRAGEN_FILE = os.path.join(DATA_DIR, 'gestellte_umfragen.json')


# --- Prozess-Variablen ---
outfit_bot_process = None
invite_bot_process = None
id_finder_bot_process = None

# --- Hilfsfunktionen für JSON ---
def load_json(file_path, default_data):
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0: return default_data
    try:
        with open(file_path, 'r', encoding='utf-8') as f: return json.load(f)
    except json.JSONDecodeError: return default_data

def save_json(file_path, data):
    with open(file_path, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

def load_config():
    default = {"quiz": {}, "umfrage": {}}
    return load_json(CONFIG_FILE, default)

def load_bot_settings_config():
    default = {
        "is_enabled": False,
        "bot_token": "",
        "main_chat_id": "",
        "topic_id": "",
        "link_ttl_minutes": 15,
        "repost_profile_for_existing_members": True
    }
    return load_json(BOT_SETTINGS_CONFIG_FILE, default)

def save_bot_settings_config(data):
    save_json(BOT_SETTINGS_CONFIG_FILE, data)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# --- Logging Helper ---
def log_to_file(file_path, message):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] {message}\n")
    except Exception as e:
        log.error(f"Konnte nicht in Log-Datei {file_path} schreiben: {e}")

# --- Initialisierung der Benutzerdatei ---
def initialize_users():
    if not os.path.exists(USERS_FILE):
        default_users = {"admin": hash_password("password")}
        save_json(USERS_FILE, default_users)
        log.info(f"Standard-Benutzerdatei '{USERS_FILE}' erstellt. Benutzer: 'admin', Passwort: 'password'")

initialize_users()

def load_users():
    return load_json(USERS_FILE, {})

# --- Login & Session Management ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        users = load_users()
        
        if username in users and users[username] == hash_password(password):
            session['logged_in'] = True
            session['user'] = username
            flash('Erfolgreich angemeldet!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Ungültiger Benutzername oder Passwort.', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Sie wurden erfolgreich abgemeldet.', 'info')
    return redirect(url_for('login'))

# --- Bot Management Helper ---
def is_bot_running(process):
    return process and process.poll() is None

def get_bot_logs(log_file, lines=100):
    if not os.path.exists(log_file): return ["Keine Log-Datei vorhanden."]
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            return reversed(f.readlines()[-lines:])
    except Exception as e:
        return [f"Fehler beim Lesen der Logs: {e}"]

def start_bot_process(script_path, log_path):
    global outfit_bot_process, invite_bot_process, id_finder_bot_process
    if script_path == OUTFIT_BOT_SCRIPT and is_bot_running(outfit_bot_process):
        return outfit_bot_process, f"{os.path.basename(script_path)} läuft bereits."
    if script_path == INVITE_BOT_SCRIPT and is_bot_running(invite_bot_process):
        return invite_bot_process, f"{os.path.basename(script_path)} läuft bereits."
    if script_path == ID_FINDER_BOT_SCRIPT and is_bot_running(id_finder_bot_process):
        return id_finder_bot_process, f"{os.path.basename(script_path)} läuft bereits."

    try:
        cwd = os.path.dirname(script_path)
        python_executable = __import__('sys').executable
        with open(log_path, "a", encoding="utf-8") as log_file:
            process = subprocess.Popen(
                [python_executable, script_path],
                cwd=cwd,
                stdout=log_file, stderr=log_file, text=True, bufsize=1, universal_newlines=True
            )
        log.info(f"{script_path} gestartet mit PID: {process.pid}")
        return process, f"{os.path.basename(script_path)} erfolgreich gestartet."
    except Exception as e:
        log.error(f"Fehler beim Starten von {script_path}: {e}", exc_info=True)
        return None, str(e)

def stop_bot_process(process):
    if not process or process.poll() is not None:
        return None, "Bot läuft nicht."
    try:
        process.terminate()
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
    except Exception as e:
        log.error(f"Fehler beim Stoppen eines Bots: {e}", exc_info=True)
        return process, str(e)
    return None, "Bot erfolgreich gestoppt."

# --- Bot Instanzen Wrapper ---
def is_outfit_bot_running(): global outfit_bot_process; return is_bot_running(outfit_bot_process)
def start_outfit_bot(): global outfit_bot_process; outfit_bot_process, msg = start_bot_process(OUTFIT_BOT_SCRIPT, OUTFIT_BOT_LOG); return bool(outfit_bot_process), msg
def stop_outfit_bot(): global outfit_bot_process; outfit_bot_process, msg = stop_bot_process(outfit_bot_process); return not bool(outfit_bot_process), msg
def get_outfit_bot_logs(lines=30): return get_bot_logs(OUTFIT_BOT_LOG, lines)

def is_invite_bot_running(): global invite_bot_process; return is_bot_running(invite_bot_process)
def start_invite_bot(): global invite_bot_process; invite_bot_process, msg = start_bot_process(INVITE_BOT_SCRIPT, INVITE_BOT_LOG); return bool(invite_bot_process), msg
def stop_invite_bot(): global invite_bot_process; invite_bot_process, msg = stop_bot_process(invite_bot_process); return not bool(invite_bot_process), msg
def get_invite_bot_logs(lines=30): return get_bot_logs(INVITE_BOT_LOG, lines)

def is_id_finder_bot_running(): global id_finder_bot_process; return is_bot_running(id_finder_bot_process)
def start_id_finder_bot(): global id_finder_bot_process; id_finder_bot_process, msg = start_bot_process(ID_FINDER_BOT_SCRIPT, ID_FINDER_BOT_LOG); return bool(id_finder_bot_process), msg
def stop_id_finder_bot(): global id_finder_bot_process; id_finder_bot_process, msg = stop_bot_process(id_finder_bot_process); return not bool(id_finder_bot_process), msg
def get_id_finder_bot_logs(lines=30): return get_bot_logs(ID_FINDER_BOT_LOG, lines)
def get_id_finder_command_logs(lines=100): return get_bot_logs(ID_FINDER_COMMAND_LOG, lines)


# --- ROUTEN ---

@app.route("/")
@login_required
def index():
    config = load_config()
    return render_template('index.html', config=config)

# --- QUIZ ROUTEN ---
@app.route('/quiz-settings', methods=['GET', 'POST'])
@login_required
def quiz_settings():
    config = load_config()
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'save_settings':
            if 'quiz' not in config: config['quiz'] = {}
            config['quiz']['token'] = request.form.get('token', '').strip()
            config['quiz']['channel_id'] = request.form.get('channel_id', '').strip()
            config['quiz']['topic_id'] = request.form.get('topic_id', '').strip()
            save_json(CONFIG_FILE, config)
            flash("Quiz-Einstellungen erfolgreich gespeichert.", "success")
            log_to_file(QUIZ_LOG_FILE, "Einstellungen gespeichert.")
            
        elif action == 'clear_log':
            try:
                open(QUIZ_LOG_FILE, 'w').close()
                flash("Quiz-Log geleert.", "success")
            except Exception as e:
                flash(f"Fehler beim Leeren des Logs: {e}", "danger")

        return redirect(url_for('quiz_settings'))

    logs = get_bot_logs(QUIZ_LOG_FILE, 100)
    return render_template('quiz_settings.html', config=config, logs=logs)

@app.route('/send_quizfrage', methods=['POST'])
@login_required
def send_quizfrage_route():
    config = load_json(CONFIG_FILE, {}).get('quiz', {})
    bot_token = config.get('token')
    channel_id = config.get('channel_id')
    topic_id = config.get('topic_id')
    
    if not bot_token or not channel_id:
        msg = "FEHLER: Bot Token oder Channel ID nicht konfiguriert."
        flash(msg, "danger")
        log_to_file(QUIZ_LOG_FILE, msg)
        return redirect(url_for('index'))
    
    all_q = load_json(QUIZFRAGEN_FILE, [])
    if not all_q:
        msg = "FEHLER: Keine Quizfragen in quizfragen.json gefunden."
        flash(msg, "warning")
        log_to_file(QUIZ_LOG_FILE, msg)
        return redirect(url_for('index'))

    for i, q in enumerate(all_q):
        if 'id' not in q: q['id'] = i

    asked_q_ids = load_json(GESTELLTE_QUIZFRAGEN_FILE, [])
    available = [q for q in all_q if q.get('id') not in asked_q_ids]
    if not available:
        asked_q_ids = []
        available = all_q
        log_to_file(QUIZ_LOG_FILE, "Alle Fragen gestellt. Reset der gestellten Fragen.")
    
    question = random.choice(available)
    log_to_file(QUIZ_LOG_FILE, f"Versuche Quizfrage ID {question['id']} zu senden...")
    
    success, error = asyncio.run(send_telegram_poll(
        bot_token, channel_id, question['frage'], question['optionen'], 'quiz', 
        question['antwort'], topic_id=topic_id
    ))
    
    if success:
        asked_q_ids.append(question['id'])
        save_json(GESTELLTE_QUIZFRAGEN_FILE, asked_q_ids)
        msg = f"Quizfrage erfolgreich gesendet! (ID: {question['id']})"
        flash(msg, 'success')
        log_to_file(QUIZ_LOG_FILE, msg)
    else:
        msg = f"FEHLER beim Senden an Telegram: {error}"
        flash(msg, "danger")
        log_to_file(QUIZ_LOG_FILE, msg)
        
    return redirect(url_for('index'))


# --- UMFRAGE ROUTEN ---
@app.route('/umfrage-settings', methods=['GET', 'POST'])
@login_required
def umfrage_settings():
    config = load_config()
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'save_settings':
            if 'umfrage' not in config: config['umfrage'] = {}
            config['umfrage']['token'] = request.form.get('token', '').strip()
            config['umfrage']['channel_id'] = request.form.get('channel_id', '').strip()
            config['umfrage']['topic_id'] = request.form.get('topic_id', '').strip()
            save_json(CONFIG_FILE, config)
            flash("Umfrage-Einstellungen erfolgreich gespeichert.", "success")
            log_to_file(UMFRAGE_LOG_FILE, "Einstellungen gespeichert.")
            
        elif action == 'clear_log':
            try:
                open(UMFRAGE_LOG_FILE, 'w').close()
                flash("Umfrage-Log geleert.", "success")
            except Exception as e:
                flash(f"Fehler beim Leeren des Logs: {e}", "danger")

        return redirect(url_for('umfrage_settings'))

    logs = get_bot_logs(UMFRAGE_LOG_FILE, 100)
    return render_template('umfrage_settings.html', config=config, logs=logs)

@app.route('/send_umfrage', methods=['POST'])
@login_required
def send_umfrage_route():
    config = load_json(CONFIG_FILE, {}).get('umfrage', {})
    bot_token = config.get('token')
    channel_id = config.get('channel_id')
    topic_id = config.get('topic_id')
    
    if not bot_token or not channel_id:
        msg = "FEHLER: Bot Token oder Channel ID nicht konfiguriert."
        flash(msg, "danger")
        log_to_file(UMFRAGE_LOG_FILE, msg)
        return redirect(url_for('index'))

    all_p = load_json(UMFRAGEN_FILE, [])
    if not all_p:
        msg = "FEHLER: Keine Umfragen in umfragen.json gefunden."
        flash(msg, "warning")
        log_to_file(UMFRAGE_LOG_FILE, msg)
        return redirect(url_for('index'))

    for i, p in enumerate(all_p):
        if 'id' not in p: p['id'] = i

    asked_p_ids = load_json(GESTELLTE_UMFRAGEN_FILE, [])
    available = [p for p in all_p if p.get('id') not in asked_p_ids]
    if not available:
        asked_p_ids = []
        available = all_p
        log_to_file(UMFRAGE_LOG_FILE, "Alle Umfragen gestellt. Reset der gestellten Umfragen.")

    poll = random.choice(available)
    log_to_file(UMFRAGE_LOG_FILE, f"Versuche Umfrage ID {poll['id']} zu senden...")
    
    success, error = asyncio.run(send_telegram_poll(
        bot_token, channel_id, poll['frage'], poll['optionen'], 'regular', 
        is_anonymous=False, topic_id=topic_id
    ))

    if success:
        asked_p_ids.append(poll['id'])
        save_json(GESTELLTE_UMFRAGEN_FILE, asked_p_ids)
        msg = f"Umfrage erfolgreich gesendet! (ID: {poll['id']})"
        flash(msg, 'success')
        log_to_file(UMFRAGE_LOG_FILE, msg)
    else:
        msg = f"FEHLER beim Senden an Telegram: {error}"
        flash(msg, "danger")
        log_to_file(UMFRAGE_LOG_FILE, msg)
        
    return redirect(url_for('index'))

async def send_telegram_poll(bot_token, channel_id, question, options, poll_type, correct_option_id=None, is_anonymous=True, topic_id=None):
    try:
        bot = telegram.Bot(token=bot_token)
        kwargs = {'chat_id': channel_id, 'question': question, 'options': options, 'type': poll_type, 'correct_option_id': correct_option_id, 'is_anonymous': is_anonymous}
        if topic_id: kwargs['message_thread_id'] = topic_id
        await bot.send_poll(**kwargs)
        return True, None
    except Exception as e:
        return False, str(e)


# --- Andere Bot-Settings ---
@app.route("/bot-settings", methods=['GET', 'POST'])
@login_required
def bot_settings():
    # ... (Code wie gehabt) ...
    config = load_bot_settings_config()
    if request.method == 'POST':
        action = request.form.get('action')
        if action:
            if action == 'start_invite_bot':
                success, msg = start_invite_bot()
                flash(msg, "success" if success else "danger")
            elif action == 'stop_invite_bot':
                success, msg = stop_invite_bot()
                flash(msg, "success" if success else "danger")
            elif action == 'clear_user_interactions_log':
                try:
                    with open(USER_INTERACTIONS_LOG_FILE, 'w') as f: f.write('')
                    flash("Benutzer-Interaktions-Log erfolgreich gelöscht.", "success")
                except Exception as e:
                    flash(f"Fehler beim Löschen des Logs: {e}", "danger")
        else:
            config['is_enabled'] = 'is_enabled' in request.form
            config['repost_profile_for_existing_members'] = 'repost_profile_for_existing_members' in request.form
            config['bot_token'] = request.form.get('bot_token', '').strip()
            config['main_chat_id'] = request.form.get('main_chat_id', '').strip()
            config['topic_id'] = request.form.get('topic_id', '').strip()
            config['link_ttl_minutes'] = int(request.form.get('link_ttl_minutes', 15))
            save_bot_settings_config(config)
            flash("Einstellungen erfolgreich gespeichert!", "success")
        return redirect(url_for('bot_settings'))

    return render_template(
        'bot_settings.html', 
        config=config, 
        is_invite_running=is_invite_bot_running(), 
        invite_bot_logs=get_invite_bot_logs(30),
        user_interaction_logs=get_bot_logs(USER_INTERACTIONS_LOG_FILE, 1000)
    )

# --- (Rest der Routen für ID-Finder und Outfit-Bot bleiben bestehen) ---
# ...
@app.route("/id-finder", methods=['GET', 'POST'])
@login_required
def id_finder_dashboard():
    config = load_json(ID_FINDER_CONFIG_FILE, {})
    if request.method == 'POST':
        action = request.form.get('action')
        config['bot_token'] = request.form.get('bot_token', '').strip()
        config['main_group_id'] = request.form.get('main_group_id', '').strip()
        config['log_topic_id'] = request.form.get('log_topic_id', '').strip() or None

        if action == 'save_config':
            save_json(ID_FINDER_CONFIG_FILE, config)
            flash("Einstellungen erfolgreich gespeichert!", "success")
        elif action == 'start_bot':
            config['is_enabled'] = True
            save_json(ID_FINDER_CONFIG_FILE, config)
            success, msg = start_id_finder_bot()
            flash(msg, "success" if success else "danger")
        elif action == 'stop_bot':
            config['is_enabled'] = False
            save_json(ID_FINDER_CONFIG_FILE, config)
            success, msg = stop_id_finder_bot()
            flash(msg, "success" if success else "danger")
        return redirect(url_for('id_finder_dashboard'))
    return render_template(
        'id_finder_dashboard.html',
        config=config,
        is_running=is_id_finder_bot_running(),
        command_logs=get_id_finder_command_logs(200),
        system_logs=get_id_finder_bot_logs(100)
    )

@app.route("/id-finder/commands")
@login_required
def id_finder_commands():
    return render_template('id_finder_commands.html')

@app.route("/outfit-bot/dashboard")
@login_required
def outfit_bot_dashboard():
    config = load_json(OUTFIT_BOT_CONFIG_FILE, {})
    return render_template('outfit_bot_dashboard.html', config=config, is_running=is_outfit_bot_running(), logs=get_outfit_bot_logs(30))

@app.route("/outfit-bot/start", methods=['POST'])
@login_required
def outfit_bot_start():
    success, msg = start_outfit_bot()
    flash(msg, "success" if success else "danger")
    return redirect(url_for('outfit_bot_dashboard'))

@app.route("/outfit-bot/stop", methods=['POST'])
@login_required
def outfit_bot_stop():
    success, msg = stop_outfit_bot()
    flash(msg, "success" if success else "danger")
    return redirect(url_for('outfit_bot_dashboard'))

@app.route("/outfit-bot/save-config", methods=['POST'])
@login_required
def outfit_bot_save_config():
    config = load_json(OUTFIT_BOT_CONFIG_FILE, {})
    form = request.form
    config.update({
        'BOT_TOKEN': form.get('BOT_TOKEN', '').strip(),
        'CHAT_ID': form.get('CHAT_ID', '').strip(),
        'TOPIC_ID': form.get('TOPIC_ID', '').strip(),
        'POST_TIME': form.get('POST_TIME', '18:00'),
        'WINNER_TIME': form.get('WINNER_TIME', '22:00'),
        'AUTO_POST_ENABLED': form.get('AUTO_POST_ENABLED') == 'true'
    })
    admin_ids_str = form.get('ADMIN_USER_IDS', '')
    config['ADMIN_USER_IDS'] = [int(id.strip()) for id in admin_ids_str.split(',') if id.strip().isdigit()]
    save_json(OUTFIT_BOT_CONFIG_FILE, config)
    flash("Outfit-Bot Konfiguration gespeichert!", "success")
    return redirect(url_for('outfit_bot_dashboard'))

@app.route("/outfit-bot/start-contest", methods=['POST'])
@login_required
def outfit_bot_start_contest():
    if not is_outfit_bot_running():
        flash("Bot läuft nicht! Bitte erst starten.", "danger")
    else:
        with open(os.path.join(OUTFIT_BOT_DIR, "command_start_contest.tmp"), 'w') as f: f.write('trigger')
        flash("Befehl 'Wettbewerb starten' gesendet.", "info")
    return redirect(url_for('outfit_bot_dashboard'))

@app.route("/outfit-bot/announce-winner", methods=['POST'])
@login_required
def outfit_bot_announce_winner():
    if not is_outfit_bot_running():
        flash("Bot läuft nicht! Bitte erst starten.", "danger")
    else:
        with open(os.path.join(OUTFIT_BOT_DIR, "command_announce_winner.tmp"), 'w') as f: f.write('trigger')
        flash("Befehl 'Gewinner auslosen' gesendet.", "info")
    return redirect(url_for('outfit_bot_dashboard'))

# --- Hintergrundprozesse ---
def start_background_processes():
    if load_bot_settings_config().get('is_enabled', False):
        start_invite_bot()
    if load_json(ID_FINDER_CONFIG_FILE, {}).get('is_enabled', False):
        start_id_finder_bot()
    if load_json(OUTFIT_BOT_CONFIG_FILE, {}).get('AUTO_POST_ENABLED', False):
        start_outfit_bot()

def shutdown_background_processes():
    stop_outfit_bot()
    stop_invite_bot()
    stop_id_finder_bot()

if __name__ == '__main__':
    atexit.register(shutdown_background_processes)
    initialize_users()
    start_background_processes()
    app.run(host='0.0.0.0', port=8080, debug=True, use_reloader=False)
