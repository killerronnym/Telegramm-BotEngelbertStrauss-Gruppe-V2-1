
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

from flask import Flask, render_template, request, flash, redirect, url_for, render_template_string
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import TelegramError
from apscheduler.schedulers.background import BackgroundScheduler
import pytz

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]',
    handlers=[RotatingFileHandler('app.log', maxBytes=10240, backupCount=5), logging.StreamHandler()],
    force=True
)
log = logging.getLogger(__name__)

# --- Globale Variablen ---
app = Flask(__name__, template_folder='src')
app.secret_key = os.urandom(24)
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Dateipfade
CONFIG_FILE = 'config.json'
OUTFIT_BOT_CONFIG_FILE = 'outfit_bot_config.json'
BOT_SETTINGS_CONFIG_FILE = 'bot_settings_config.json'
ID_FINDER_CONFIG_FILE = 'id_finder_config.json'
OUTFIT_BOT_SCRIPT = 'outfit_bot.py'
OUTFIT_BOT_LOG = 'outfit_bot.log'
INVITE_BOT_SCRIPT = 'invite_bot.py'
INVITE_BOT_LOG = 'invite_bot.log'
ID_FINDER_BOT_SCRIPT = 'id_finder_bot.py'
ID_FINDER_BOT_LOG = 'id_finder_bot.log'
QUIZFRAGEN_FILE = 'quizfragen.json'
GESTELLTE_QUIZFRAGEN_FILE = 'gestellte_quizfragen.json'
UMFRAGEN_FILE = 'umfragen.json'
GESTELLTE_UMFRAGEN_FILE = 'gestellte_umfragen.json'

# Prozess-Variablen
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
        "link_ttl_minutes": 15
    }
    return load_json(BOT_SETTINGS_CONFIG_FILE, default)

def save_bot_settings_config(data):
    save_json(BOT_SETTINGS_CONFIG_FILE, data)

# --- Hilfsfunktionen für Bot Management (Generisch) ---
def is_bot_running(process):
    return process and process.poll() is None

def get_bot_logs(log_file, lines=30):
    if not os.path.exists(log_file):
        return ["Keine Log-Datei vorhanden."]
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            return f.readlines()[-lines:]
    except Exception as e:
        return [f"Fehler beim Lesen der Logs: {e}"]

def start_bot_process(script_path, log_path):
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        return None, "Nicht im Hauptprozess, Bot wird hier nicht gestartet."
    try:
        python_executable = __import__('sys').executable
        with open(log_path, "a", encoding="utf-8") as log_file:
            process = subprocess.Popen(
                [python_executable, script_path],
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

# --- Bot Management Instanzen ---
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


# --- Haupt-Web-Routen ---
@app.route("/")
def index():
    return render_template('index.html', config=load_config())

async def send_telegram_poll(bot_token, channel_id, question, options, poll_type, correct_option_id=None, is_anonymous=True, topic_id=None):
    try:
        bot = telegram.Bot(token=bot_token)
        kwargs = {
            'chat_id': channel_id,
            'question': question,
            'options': options,
            'type': poll_type,
            'correct_option_id': correct_option_id,
            'is_anonymous': is_anonymous
        }
        if topic_id:
            kwargs['message_thread_id'] = topic_id
        await bot.send_poll(**kwargs)
        return True, None
    except Exception as e:
        return False, str(e)

@app.route('/send_quizfrage', methods=['POST'])
def send_quizfrage_route():
    config = load_config().get('quiz', {})
    bot_token, channel_id, topic_id = config.get('token'), config.get('channel_id'), config.get('topic_id')
    if not bot_token or not channel_id:
        flash("Bot Token oder Channel ID für Quiz nicht konfiguriert.", "danger")
        return redirect(url_for('index'))
    
    all_q = load_json(QUIZFRAGEN_FILE, [])
    if not all_q:
        flash("Keine Quizfragen in quizfragen.json gefunden.", "warning")
        return redirect(url_for('index'))

    for i, q in enumerate(all_q):
        if 'id' not in q: q['id'] = i

    asked_q_ids = load_json(GESTELLTE_QUIZFRAGEN_FILE, [])
    available = [q for q in all_q if q.get('id') not in asked_q_ids]
    if not available:
        asked_q_ids = []
        available = all_q
    
    if not available:
        flash("Alle Quizfragen wurden bereits gestellt.", "info")
        return redirect(url_for('index'))
        
    question = random.choice(available)
    success, error = asyncio.run(send_telegram_poll(bot_token, channel_id, question['frage'], question['optionen'], 'quiz', question['antwort'], topic_id=topic_id))
    
    if success:
        asked_q_ids.append(question['id'])
        save_json(GESTELLTE_QUIZFRAGEN_FILE, asked_q_ids)
        flash('Quizfrage gesendet!', 'success')
    else:
        flash(f"Fehler beim Senden der Quizfrage: {error}", "danger")
    return redirect(url_for('index'))

@app.route('/send_umfrage', methods=['POST'])
def send_umfrage_route():
    config = load_config().get('umfrage', {})
    bot_token, channel_id, topic_id = config.get('token'), config.get('channel_id'), config.get('topic_id')
    if not bot_token or not channel_id:
        flash("Bot Token oder Channel ID für Umfrage nicht konfiguriert.", "danger")
        return redirect(url_for('index'))

    all_p = load_json(UMFRAGEN_FILE, [])
    if not all_p:
        flash("Keine Umfragen in umfragen.json gefunden.", "warning")
        return redirect(url_for('index'))

    for i, p in enumerate(all_p):
        if 'id' not in p: p['id'] = i

    asked_p_ids = load_json(GESTELLTE_UMFRAGEN_FILE, [])
    available = [p for p in all_p if p.get('id') not in asked_p_ids]
    if not available:
        asked_p_ids = []
        available = all_p

    if not available:
        flash("Alle Umfragen wurden bereits gestellt.", "info")
        return redirect(url_for('index'))

    poll = random.choice(available)
    success, error = asyncio.run(send_telegram_poll(bot_token, channel_id, poll['frage'], poll['optionen'], 'regular', is_anonymous=False, topic_id=topic_id))

    if success:
        asked_p_ids.append(poll['id'])
        save_json(GESTELLTE_UMFRAGEN_FILE, asked_p_ids)
        flash('Umfrage gesendet!', 'success')
    else:
        flash(f"Fehler beim Senden der Umfrage: {error}", "danger")
    return redirect(url_for('index'))

@app.route('/save_settings', methods=['POST'])
def handle_settings():
    config = load_config()
    form = request.form
    config_type = form.get('config_type')
    if config_type not in config: return redirect(url_for('index'))
    
    if form.get('action') == 'save_settings':
        config[config_type].update({
            'token': form.get('token', '').strip(),
            'channel_id': form.get('channel_id', '').strip(),
            'topic_id': form.get('topic_id', '').strip(),
            'time': form.get('time', '12:00')
        })
        flash(f'{config_type.capitalize()}-Einstellungen gespeichert.', 'success')
    
    save_json(CONFIG_FILE, config)
    return redirect(url_for('index'))

# --- Web-Routen für Invite-Bot ---
@app.route("/bot-settings", methods=['GET', 'POST'])
def bot_settings():
    config = load_bot_settings_config()
    if request.method == 'POST':
        if 'action' in request.form:
            action = request.form['action']
            if action == 'start_invite_bot':
                success, msg = start_invite_bot()
            elif action == 'stop_invite_bot':
                success, msg = stop_invite_bot()
            flash(msg, "success" if success else "danger")
        else:
            config['is_enabled'] = 'is_enabled' in request.form
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
        invite_bot_logs=get_invite_bot_logs(30)
    )

# --- Web-Routen für ID-Finder-Bot ---
@app.route("/id-finder", methods=['GET', 'POST'])
def id_finder_dashboard():
    config = load_json(ID_FINDER_CONFIG_FILE, {"is_enabled": False, "bot_token": ""})
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'save_config':
            config['is_enabled'] = 'is_enabled' in request.form
            config['bot_token'] = request.form.get('bot_token', '').strip()
            save_json(ID_FINDER_CONFIG_FILE, config)
            flash("ID-Finder-Bot Einstellungen gespeichert!", "success")
        elif action == 'start_bot':
            success, msg = start_id_finder_bot()
            flash(msg, "success" if success else "danger")
        elif action == 'stop_bot':
            success, msg = stop_id_finder_bot()
            flash(msg, "success" if success else "danger")
        return redirect(url_for('id_finder_dashboard'))

    return render_template(
        'id_finder_dashboard.html',
        config=config,
        is_running=is_id_finder_bot_running(),
        logs=get_id_finder_bot_logs(30)
    )

# --- Web-Routen für Outfit-Bot ---
@app.route("/outfit-bot/dashboard")
def outfit_bot_dashboard():
    config = load_json(OUTFIT_BOT_CONFIG_FILE, {})
    return render_template(
        'outfit_bot_dashboard.html', 
        config=config, 
        is_running=is_outfit_bot_running(),
        logs=get_outfit_bot_logs(30)
    )

@app.route("/outfit-bot/start", methods=['POST'])
def outfit_bot_start():
    success, msg = start_outfit_bot()
    flash(msg, "success" if success else "danger")
    return redirect(url_for('outfit_bot_dashboard'))

@app.route("/outfit-bot/stop", methods=['POST'])
def outfit_bot_stop():
    success, msg = stop_outfit_bot()
    flash(msg, "success" if success else "danger")
    return redirect(url_for('outfit_bot_dashboard'))

@app.route("/outfit-bot/save-config", methods=['POST'])
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

# NEU: Wiederhergestellte Routen für manuelle Aktionen
def trigger_bot_command(command_name):
    """Erstellt eine temporäre Datei, um einen Befehl an den Bot zu signalisieren."""
    with open(f"command_{command_name}.tmp", 'w') as f:
        f.write('trigger')

@app.route("/outfit-bot/start-contest", methods=['POST'])
def outfit_bot_start_contest():
    if not is_outfit_bot_running():
        flash("Bot läuft nicht! Bitte erst starten.", "danger")
    else:
        trigger_bot_command('start_contest')
        flash("Befehl 'Wettbewerb starten' gesendet.", "info")
    return redirect(url_for('outfit_bot_dashboard'))

@app.route("/outfit-bot/announce-winner", methods=['POST'])
def outfit_bot_announce_winner():
    if not is_outfit_bot_running():
        flash("Bot läuft nicht! Bitte erst starten.", "danger")
    else:
        trigger_bot_command('announce_winner')
        flash("Befehl 'Gewinner auslosen' gesendet.", "info")
    return redirect(url_for('outfit_bot_dashboard'))

# --- Hintergrundprozesse ---
def start_background_processes():
    start_outfit_bot()
    start_invite_bot()
    start_id_finder_bot()

def shutdown_background_processes():
    stop_outfit_bot()
    stop_invite_bot()
    stop_id_finder_bot()

# === ANWENDUNGSSTART ===
if __name__ == '__main__':
    atexit.register(shutdown_background_processes)
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
         start_background_processes() 

    app.run(host='0.0.0.0', port=8080, debug=True, use_reloader=True)
