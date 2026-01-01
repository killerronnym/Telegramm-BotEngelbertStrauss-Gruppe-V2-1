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
import sys

from flask import Flask, render_template, request, flash, redirect, url_for
from telegram import Bot

# --- Logging (Global & App) ---
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

# Bot Directories
OUTFIT_BOT_DIR = os.path.join(PROJECT_ROOT, 'outfit_bot')
ID_FINDER_BOT_DIR = os.path.join(PROJECT_ROOT, 'id_finder_bot')
INVITE_BOT_DIR = os.path.join(PROJECT_ROOT, 'invite_bot')

# Config Files
OUTFIT_BOT_CONFIG_FILE = os.path.join(OUTFIT_BOT_DIR, 'outfit_bot_config.json')
ID_FINDER_CONFIG_FILE = os.path.join(ID_FINDER_BOT_DIR, 'id_finder_config.json')
INVITE_BOT_CONFIG_FILE = os.path.join(INVITE_BOT_DIR, 'invite_bot_config.json')
DASHBOARD_CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
ADMINS_FILE = os.path.join(BASE_DIR, 'admins.json')  # NEW: Admins File

# Log Files
OUTFIT_BOT_LOG = os.path.join(OUTFIT_BOT_DIR, 'outfit_bot.log')
ID_FINDER_BOT_LOG = os.path.join(ID_FINDER_BOT_DIR, 'id_finder_bot.log')
ID_FINDER_COMMAND_LOG = os.path.join(ID_FINDER_BOT_DIR, 'id_finder_command.log')
INVITE_BOT_LOG = os.path.join(INVITE_BOT_DIR, 'invite_bot.log')
INVITE_BOT_USER_LOG = os.path.join(INVITE_BOT_DIR, 'user_interactions.log')
DASHBOARD_APP_LOG = os.path.join(BASE_DIR, 'app.log')

# Script Files
OUTFIT_BOT_SCRIPT = os.path.join(OUTFIT_BOT_DIR, 'outfit_bot.py')
ID_FINDER_BOT_SCRIPT = os.path.join(ID_FINDER_BOT_DIR, 'id_finder_bot.py')
INVITE_BOT_SCRIPT = os.path.join(INVITE_BOT_DIR, 'invite_bot.py')

# Data Files
OUTFIT_BOT_DATA_FILE = os.path.join(OUTFIT_BOT_DIR, 'outfit_bot_data.json')
QUIZ_DATA_FILE = os.path.join(PROJECT_ROOT, 'data', 'quizfragen.json')
UMFRAGE_DATA_FILE = os.path.join(PROJECT_ROOT, 'data', 'umfragen.json')

# --- Prozess-Variablen ---
outfit_bot_process = None
id_finder_process = None
invite_bot_process = None

# --- Constants ---
# Gruppierte Berechtigungen (für modernes Admin-Panel UI)
AVAILABLE_PERMISSION_GROUPS = {
    "Basis-Moderation": {
        "can_warn": "Verwarnen (/warn, /unwarn, /warnings, /clearwarnings)",
        "can_kick": "Kicken (/kick)",
        "can_ban": "Bannen (/ban)",
        "can_unban": "Entbannen (/unban)",
        "can_mute": "Stummschalten (/mute, /unmute)",
        "can_clear_warns": "Warns löschen (/clearwarnings)"
    },
    "Nachrichten-Management": {
        "can_manage_messages": "Nachrichten verwalten (/del, /purge, /pin, /unpin, /lock, /unlock)"
    },
    "Anti-Spam & Filter": {
        "can_antispam": "Anti-Spam steuern (/antispam)",
        "can_setflood": "Flood-Limit setzen (/setflood)",
        "can_setlinkmode": "Link-Modus setzen (/setlinkmode)",
        "can_blacklist": "Blacklist verwalten (/blacklist add/remove/list)"
    },
    "Rollen & Bot-Rechte": {
        "can_roles": "Rollen/Mods verwalten (/mod, /setrole, /permissions)"
    },
    "Konfiguration & Community": {
        "can_config": "Einstellungen/Onboarding (/settings, /config, /status, /reload, /welcome, /setwelcome, /rules, /setrules, /verify)"
    },
    "System & Debug": {
        "can_debug": "Debug-Modus (/debug)"
    },
    "Tools": {
        "can_see_ids": "IDs anzeigen (/id, /chatid, /userid, /topicid)",
        "can_see_logs": "Logs einsehen",
        "can_manage_admins": "Admins verwalten (Nur Top-Admin)"
    }
}

# Flat-Fallback für ältere Templates/Logik
AVAILABLE_PERMISSIONS = {
    k: v
    for group in AVAILABLE_PERMISSION_GROUPS.values()
    for k, v in group.items()
}

# --- Hilfsfunktionen für JSON ---
def load_json(file_path, default_data={}):
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        return default_data
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return default_data


def save_json(file_path, data):
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# --- Bot Management Helper ---
def is_bot_running(process):
    return process and process.poll() is None


def get_bot_logs(log_file, lines=100):
    if not os.path.exists(log_file):
        return [f"Keine Log-Datei vorhanden unter: {log_file}"]
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            return list(reversed(f.readlines()[-lines:]))
    except Exception as e:
        return [f"Fehler beim Lesen der Logs ({log_file}): {e}"]


def start_bot_process(script_path, log_path):
    global outfit_bot_process

    try:
        cwd = os.path.dirname(script_path)
        py_exec = sys.executable

        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        with open(log_path, "a", encoding="utf-8") as log_f:
            process = subprocess.Popen(
                [py_exec, script_path],
                cwd=cwd,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
        return process, f"{os.path.basename(script_path)} erfolgreich gestartet."
    except Exception as e:
        return None, str(e)


def stop_bot_process(process):
    if not process or process.poll() is not None:
        return None, "Bot läuft nicht."
    try:
        process.terminate()
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
    return None, "Bot erfolgreich gestoppt."


# --- Outfit Bot Wrappers ---
def is_outfit_bot_running():
    return is_bot_running(outfit_bot_process)


def start_outfit_bot():
    global outfit_bot_process
    if is_outfit_bot_running():
        return True, "Outfit Bot läuft bereits."
    outfit_bot_process, msg = start_bot_process(OUTFIT_BOT_SCRIPT, OUTFIT_BOT_LOG)
    return bool(outfit_bot_process), msg


def stop_outfit_bot():
    global outfit_bot_process
    outfit_bot_process, msg = stop_bot_process(outfit_bot_process)
    return not bool(outfit_bot_process), msg


def get_outfit_bot_logs(lines=30):
    return get_bot_logs(OUTFIT_BOT_LOG, lines)


# --- ID Finder Bot Wrappers ---
def is_id_finder_running():
    return is_bot_running(id_finder_process)


def start_id_finder_bot():
    global id_finder_process
    if is_id_finder_running():
        return True, "ID Finder Bot läuft bereits."
    id_finder_process, msg = start_bot_process(ID_FINDER_BOT_SCRIPT, ID_FINDER_BOT_LOG)
    return bool(id_finder_process), msg


def stop_id_finder_bot():
    global id_finder_process
    id_finder_process, msg = stop_bot_process(id_finder_process)
    return not bool(id_finder_process), msg


# --- Invite Bot Wrappers ---
def is_invite_bot_running():
    return is_bot_running(invite_bot_process)


def start_invite_bot():
    global invite_bot_process
    if is_invite_bot_running():
        return True, "Invite Bot läuft bereits."
    invite_bot_process, msg = start_bot_process(INVITE_BOT_SCRIPT, INVITE_BOT_LOG)
    return bool(invite_bot_process), msg


def stop_invite_bot():
    global invite_bot_process
    invite_bot_process, msg = stop_bot_process(invite_bot_process)
    return not bool(invite_bot_process), msg


# --- ROUTEN ---
@app.route("/")
def index():
    return render_template('index.html')


# --- OUTFIT BOT ROUTES ---
@app.route("/outfit-bot/dashboard")
def outfit_bot_dashboard():
    config = load_json(OUTFIT_BOT_CONFIG_FILE)
    duel_status = {"active": False}
    bot_data = load_json(OUTFIT_BOT_DATA_FILE)
    if bot_data and "current_duel" in bot_data:
        duel_data = bot_data["current_duel"]
        contestants = duel_data.get("contestants", {})
        names = [f"@{d.get('username', 'Unbekannt')}" for d in contestants.values()]
        duel_status["active"] = True
        duel_status["contestants"] = " vs ".join(names)

    return render_template(
        'outfit_bot_dashboard.html',
        config=config,
        is_running=is_outfit_bot_running(),
        logs=get_outfit_bot_logs(30),
        duel_status=duel_status
    )


@app.route("/outfit-bot/start", methods=['POST'])
def outfit_bot_start_route():
    success, msg = start_outfit_bot()
    flash(msg, "success" if success else "danger")
    return redirect(url_for('outfit_bot_dashboard'))


@app.route("/outfit-bot/stop", methods=['POST'])
def outfit_bot_stop_route():
    success, msg = stop_outfit_bot()
    flash(msg, "success" if success else "danger")
    return redirect(url_for('outfit_bot_dashboard'))


@app.route("/outfit-bot/clear-logs", methods=['POST'])
def outfit_bot_clear_logs():
    try:
        with open(OUTFIT_BOT_LOG, 'w') as f:
            f.write('')
        flash("Logs erfolgreich geleert.", "success")
    except Exception as e:
        flash(f"Fehler beim Leeren der Logs: {e}", "danger")
    return redirect(url_for('outfit_bot_dashboard'))


@app.route("/outfit-bot/save-config", methods=['POST'])
def outfit_bot_save_config():
    was_running = is_outfit_bot_running()
    if was_running:
        stop_outfit_bot()

    config = load_json(OUTFIT_BOT_CONFIG_FILE)
    form = request.form

    config.update({
        'BOT_TOKEN': form.get('BOT_TOKEN', '').strip(),
        'CHAT_ID': form.get('CHAT_ID', '').strip(),
        'TOPIC_ID': form.get('TOPIC_ID', '').strip() or None,
        'POST_TIME': form.get('POST_TIME', '18:00'),
        'WINNER_TIME': form.get('WINNER_TIME', '22:00'),
        'DUEL_TYPE': form.get('DUEL_TYPE', 'tie_breaker'),
        'DUEL_DURATION_MINUTES': int(form.get('DUEL_DURATION_MINUTES', 60)),
        'TEMPORARY_MESSAGE_DURATION_SECONDS': int(form.get('TEMPORARY_MESSAGE_DURATION_SECONDS', 30))
    })

    config['AUTO_POST_ENABLED'] = 'AUTO_POST_ENABLED' in form
    config['DUEL_MODE'] = 'DUEL_MODE' in form

    admin_ids_str = form.get('ADMIN_USER_IDS', '')
    try:
        config['ADMIN_USER_IDS'] = [
            int(id.strip()) for id in admin_ids_str.split(',')
            if id.strip().isdigit()
        ]
    except ValueError:
        flash("Fehler: Ungültige Admin User ID.", "danger")
        return redirect(url_for('outfit_bot_dashboard'))

    save_json(OUTFIT_BOT_CONFIG_FILE, config)
    flash("Konfiguration gespeichert!", "success")

    if was_running:
        success, msg = start_outfit_bot()
        flash("Bot wird mit neuer Konfiguration neu gestartet.", "info")

    return redirect(url_for('outfit_bot_dashboard'))


@app.route("/outfit-bot/start-contest", methods=['POST'])
def outfit_bot_start_contest():
    if is_outfit_bot_running():
        with open(os.path.join(OUTFIT_BOT_DIR, "command_start_contest.tmp"), 'w') as f:
            f.write('trigger')
        flash("Befehl 'Wettbewerb starten' gesendet.", "info")
    else:
        flash("Bot läuft nicht!", "danger")
    return redirect(url_for('outfit_bot_dashboard'))


@app.route("/outfit-bot/announce-winner", methods=['POST'])
def outfit_bot_announce_winner():
    if is_outfit_bot_running():
        with open(os.path.join(OUTFIT_BOT_DIR, "command_announce_winner.tmp"), 'w') as f:
            f.write('trigger')
        flash("Befehl 'Gewinner auslosen' gesendet.", "info")
    else:
        flash("Bot läuft nicht!", "danger")
    return redirect(url_for('outfit_bot_dashboard'))


@app.route("/outfit-bot/end-duel", methods=['POST'])
def outfit_bot_end_duel():
    if is_outfit_bot_running():
        with open(os.path.join(OUTFIT_BOT_DIR, "command_end_duel.tmp"), 'w') as f:
            f.write('trigger')
        flash("Befehl 'Duell beenden' gesendet.", "info")
    else:
        flash("Bot läuft nicht!", "danger")
    return redirect(url_for('outfit_bot_dashboard'))


# --- INVITE BOT ROUTES ---
@app.route("/bot-settings", methods=['GET', 'POST'])
def bot_settings():
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'start_invite_bot':
            success, msg = start_invite_bot()
            flash(msg, "success" if success else "danger")

        elif action == 'stop_invite_bot':
            success, msg = stop_invite_bot()
            flash(msg, "success" if success else "danger")

        elif action == 'clear_user_interactions_log':
            try:
                with open(INVITE_BOT_USER_LOG, 'w') as f:
                    f.write('')
                flash("Benutzer-Interaktions-Log geleert.", "success")
            except Exception as e:
                flash(f"Fehler beim Leeren des Logs: {e}", "danger")

        elif action == 'clear_invite_bot_log':
            try:
                with open(INVITE_BOT_LOG, 'w') as f:
                    f.write('')
                flash("Bot Log erfolgreich geleert.", "success")
            except Exception as e:
                flash(f"Fehler beim Leeren des Bot Logs: {e}", "danger")

        else:
            was_running = is_invite_bot_running()
            if was_running:
                stop_invite_bot()

            config = load_json(INVITE_BOT_CONFIG_FILE)
            config['bot_token'] = request.form.get('bot_token', '').strip()
            config['main_chat_id'] = request.form.get('main_chat_id', '').strip()
            config['topic_id'] = request.form.get('topic_id', '').strip() or None
            config['is_enabled'] = 'is_enabled' in request.form
            config['repost_profile_for_existing_members'] = 'repost_profile_for_existing_members' in request.form
            try:
                config['link_ttl_minutes'] = int(request.form.get('link_ttl_minutes', 15))
            except ValueError:
                config['link_ttl_minutes'] = 15

            save_json(INVITE_BOT_CONFIG_FILE, config)
            flash("Invite Bot Einstellungen gespeichert.", "success")

            if was_running:
                start_invite_bot()
                flash("Invite Bot neu gestartet.", "info")
            elif config['is_enabled']:
                pass

        return redirect(url_for('bot_settings'))

    config = load_json(INVITE_BOT_CONFIG_FILE)
    invite_bot_logs = get_bot_logs(INVITE_BOT_LOG)
    user_interaction_logs = get_bot_logs(INVITE_BOT_USER_LOG)

    return render_template(
        'bot_settings.html',
        config=config,
        is_invite_running=is_invite_bot_running(),
        invite_bot_logs=invite_bot_logs,
        user_interaction_logs=user_interaction_logs
    )


# --- ID FINDER BOT ROUTES ---
@app.route("/id-finder", methods=['GET', 'POST'])
def id_finder_dashboard():
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'start_bot':
            success, msg = start_id_finder_bot()
            flash(msg, "success" if success else "danger")

        elif action == 'stop_bot':
            success, msg = stop_id_finder_bot()
            flash(msg, "success" if success else "danger")

        elif action == 'clear_system_log':
            try:
                with open(ID_FINDER_BOT_LOG, 'w') as f:
                    f.write('')
                flash("System- & Fehler-Log erfolgreich geleert.", "success")
            except Exception as e:
                flash(f"Fehler beim Leeren des Logs: {e}", "danger")

        elif action == 'clear_command_log':
            try:
                with open(ID_FINDER_COMMAND_LOG, 'w') as f:
                    f.write('')
                flash("Befehls-Logbuch erfolgreich geleert.", "success")
            except Exception as e:
                flash(f"Fehler beim Leeren des Logs: {e}", "danger")

        elif action == 'save_config':
            was_running = is_id_finder_running()
            if was_running:
                stop_id_finder_bot()

            config = load_json(ID_FINDER_CONFIG_FILE)
            config['bot_token'] = request.form.get('bot_token', '').strip()
            config['main_group_id'] = request.form.get('main_group_id', '').strip()
            config['log_topic_id'] = request.form.get('log_topic_id', '').strip() or None

            # --- NEUE EINSTELLUNGEN START ---
            config['delete_commands'] = 'delete_commands' in request.form
            try:
                config['bot_message_cleanup_seconds'] = int(request.form.get('bot_message_cleanup_seconds', 0))
            except ValueError:
                config['bot_message_cleanup_seconds'] = 0
            # --- NEUE EINSTELLUNGEN ENDE ---

            save_json(ID_FINDER_CONFIG_FILE, config)
            flash("ID Finder Konfiguration gespeichert.", "success")

            if was_running:
                start_id_finder_bot()
                flash("ID Finder Bot neu gestartet.", "info")

        return redirect(url_for('id_finder_dashboard'))

    config = load_json(ID_FINDER_CONFIG_FILE)
    system_logs = get_bot_logs(ID_FINDER_BOT_LOG)
    command_logs = get_bot_logs(ID_FINDER_COMMAND_LOG)

    return render_template(
        'id_finder_dashboard.html',
        config=config,
        is_running=is_id_finder_running(),
        system_logs=system_logs,
        command_logs=command_logs
    )


@app.route("/id-finder/commands")
def id_finder_commands():
    return render_template('id_finder_commands.html')


# --- ADMIN PANEL ROUTES ---
@app.route("/id-finder/admin-panel")
def id_finder_admin_panel():
    admins = load_json(ADMINS_FILE)
    return render_template(
        'id_finder_admin_panel.html',
        admins=admins,
        available_permissions=AVAILABLE_PERMISSIONS,
        available_permission_groups=AVAILABLE_PERMISSION_GROUPS
    )


@app.route("/id-finder/add-admin", methods=['POST'])
def id_finder_add_admin():
    admin_id = request.form.get('admin_id', '').strip()
    admin_name = request.form.get('admin_name', '').strip()

    if not admin_id or not admin_name:
        flash("Bitte ID und Namen angeben.", "danger")
        return redirect(url_for('id_finder_admin_panel'))

    admins = load_json(ADMINS_FILE)
    if admin_id in admins:
        flash("Admin existiert bereits.", "warning")
        return redirect(url_for('id_finder_admin_panel'))

    # Default permissions (all false initially)
    default_permissions = {perm: False for perm in AVAILABLE_PERMISSIONS}

    admins[admin_id] = {
        "name": admin_name,
        "permissions": default_permissions
    }

    save_json(ADMINS_FILE, admins)
    flash(f"Admin {admin_name} hinzugefügt.", "success")
    return redirect(url_for('id_finder_admin_panel'))


@app.route("/id-finder/delete-admin", methods=['POST'])
def id_finder_delete_admin():
    admin_id = request.form.get('admin_id')
    admins = load_json(ADMINS_FILE)

    if admin_id in admins:
        del admins[admin_id]
        save_json(ADMINS_FILE, admins)
        flash("Admin gelöscht.", "success")
    else:
        flash("Admin nicht gefunden.", "danger")

    return redirect(url_for('id_finder_admin_panel'))


@app.route("/id-finder/update-admin-permissions", methods=['POST'])
def id_finder_update_admin_permissions():
    admin_id = request.form.get('admin_id')
    admins = load_json(ADMINS_FILE)

    if admin_id not in admins:
        flash("Fehler: Admin nicht gefunden.", "danger")
        return redirect(url_for('id_finder_admin_panel'))

    # Update permissions based on checkboxes
    new_permissions = {}
    for perm_key in AVAILABLE_PERMISSIONS:
        # Checkbox sent 'on' if checked, otherwise nothing
        new_permissions[perm_key] = (request.form.get(perm_key) == 'on')

    admins[admin_id]['permissions'] = new_permissions
    save_json(ADMINS_FILE, admins)

    flash(f"Rechte für {admins[admin_id]['name']} aktualisiert.", "success")
    return redirect(url_for('id_finder_admin_panel'))


# --- QUIZ & UMFRAGE ROUTES ---
@app.route("/quiz-settings", methods=['GET', 'POST'])
def quiz_settings():
    if request.method == 'POST':
        if request.form.get('action') == 'save_settings':
            dashboard_config = load_json(DASHBOARD_CONFIG_FILE)
            if 'quiz' not in dashboard_config:
                dashboard_config['quiz'] = {}
            dashboard_config['quiz']['token'] = request.form.get('token', '').strip()
            dashboard_config['quiz']['channel_id'] = request.form.get('channel_id', '').strip()
            dashboard_config['quiz']['topic_id'] = request.form.get('topic_id', '').strip() or None
            save_json(DASHBOARD_CONFIG_FILE, dashboard_config)
            flash("Quiz Einstellungen gespeichert.", "success")
        elif request.form.get('action') == 'clear_log':
            try:
                with open(DASHBOARD_APP_LOG, 'w') as f:
                    f.write('')
                flash("Log geleert.", "success")
            except Exception as e:
                flash(f"Fehler beim Leeren des Logs: {e}", "danger")

        return redirect(url_for('quiz_settings'))

    dashboard_config = load_json(DASHBOARD_CONFIG_FILE)
    logs = get_bot_logs(DASHBOARD_APP_LOG, lines=50)  # Use helper to get logs
    return render_template('quiz_settings.html', config=dashboard_config, logs=logs)


@app.route("/umfrage-settings", methods=['GET', 'POST'])
def umfrage_settings():
    if request.method == 'POST':
        if request.form.get('action') == 'save_settings':
            dashboard_config = load_json(DASHBOARD_CONFIG_FILE)
            if 'umfrage' not in dashboard_config:
                dashboard_config['umfrage'] = {}
            dashboard_config['umfrage']['token'] = request.form.get('token', '').strip()
            dashboard_config['umfrage']['channel_id'] = request.form.get('channel_id', '').strip()
            dashboard_config['umfrage']['topic_id'] = request.form.get('topic_id', '').strip() or None
            save_json(DASHBOARD_CONFIG_FILE, dashboard_config)
            flash("Umfrage Einstellungen gespeichert.", "success")
        elif request.form.get('action') == 'clear_log':
            try:
                with open(DASHBOARD_APP_LOG, 'w') as f:
                    f.write('')
                flash("Log geleert.", "success")
            except Exception as e:
                flash(f"Fehler beim Leeren des Logs: {e}", "danger")

        return redirect(url_for('umfrage_settings'))

    dashboard_config = load_json(DASHBOARD_CONFIG_FILE)
    logs = get_bot_logs(DASHBOARD_APP_LOG, lines=50)  # Use helper to get logs
    return render_template('umfrage_settings.html', config=dashboard_config, logs=logs)


async def send_telegram_poll(token, chat_id, topic_id, question, options):
    try:
        bot = Bot(token=token)
        # Convert topic_id to int if present, else None
        message_thread_id = int(topic_id) if topic_id and str(topic_id).isdigit() else None

        await bot.send_poll(
            chat_id=chat_id,
            question=question,
            options=options,
            is_anonymous=False,
            allows_multiple_answers=False,  # Standard poll
            message_thread_id=message_thread_id
        )
    ```
::contentReference[oaicite:1]{index=1}
