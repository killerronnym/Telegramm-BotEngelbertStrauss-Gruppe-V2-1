from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
import os
import json
import subprocess
import sys
import signal
from datetime import datetime
from ..models import db, BotSettings

bp = Blueprint('dashboard', __name__)

# Fixed PROJECT_ROOT to point to the actual project root, not the web_dashboard directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
BASE_DIR = os.path.join(PROJECT_ROOT, 'web_dashboard')
INVITE_BOT_PID_FILE = os.path.join(BASE_DIR, "invite_bot.pid")
INVITE_BOT_ERROR_LOG = os.path.join(BASE_DIR, "invite_bot_error.log")
USER_INTERACTION_LOG_FILE = os.path.join(PROJECT_ROOT, "user_interactions.log")
INVITE_BOT_LOG_FILE = os.path.join(BASE_DIR, "invite_bot.log")
START_DEBUG_LOG_FILE = os.path.join(BASE_DIR, "start_debug.log")
DIRECT_START_OUTPUT_LOG = os.path.join(BASE_DIR, "direct_start_output.log") # New debug log

def is_process_running(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

def get_bot_status_simple():
    invite_running = False
    if os.path.exists(INVITE_BOT_PID_FILE):
        try:
            with open(INVITE_BOT_PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            if is_process_running(pid):
                invite_running = True
            else:
                os.remove(INVITE_BOT_PID_FILE)
        except (IOError, ValueError):
            if os.path.exists(INVITE_BOT_PID_FILE):
                os.remove(INVITE_BOT_PID_FILE)
    return {"invite": {"running": invite_running}}

@bp.context_processor
def inject_globals():
    return {"bot_status": get_bot_status_simple()}

@bp.route('/')
@bp.route('/dashboard')
def index():
    return render_template('index.html', version={"version": "3.0.0"})

def get_invite_bot_settings():
    settings = BotSettings.query.filter_by(bot_name='invite').first()
    if not settings:
        initial_config = {
            'is_enabled': False, 'bot_token': '', 'main_chat_id': '', 'topic_id': '',
            'link_ttl_minutes': 15,
            'start_message': 'Willkommen!', 'rules_message': 'Bitte beachte die Regeln.',
            'blocked_message': 'Du bist gesperrt.', 'privacy_policy': 'Datenschutz...',
            'form_fields': [], 'whitelist_enabled': False, 'whitelist_approval_chat_id': '',
            'whitelist_approval_topic_id': '', 'whitelist_pending_message': 'Dein Antrag wird geprüft.',
            'whitelist_rejection_message': 'Dein Antrag wurde abgelehnt.'
        }
        settings = BotSettings(bot_name='invite', config_json=json.dumps(initial_config))
        db.session.add(settings)
        db.session.commit()
    return settings

@bp.route('/bot-settings', methods=["GET", "POST"])
def bot_settings():
    # Aggressive Debugging: Logge alles, was als POST-Anfrage ankommt
    if request.method == 'POST':
        os.makedirs(os.path.dirname(START_DEBUG_LOG_FILE), exist_ok=True)
        with open(START_DEBUG_LOG_FILE, 'a') as f:
            f.write(f"{datetime.now()}: DEBUG: POST request received. Form data: {request.form}\n")

    invite_bot_settings = get_invite_bot_settings()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'start_invite_bot':
            if os.path.exists(INVITE_BOT_PID_FILE):
                flash('Bot läuft bereits.', 'warning')
            else:
                try:
                    python_exe = sys.executable
                    bot_script = os.path.join(PROJECT_ROOT, "bots", "invite_bot", "invite_bot.py")
                    
                    # Logge den Startversuch
                    os.makedirs(os.path.dirname(DIRECT_START_OUTPUT_LOG), exist_ok=True)
                    with open(DIRECT_START_OUTPUT_LOG, 'a') as log_output_file:
                         log_output_file.write(f"{datetime.now()}: Attempting to start bot in background.\n")
                         log_output_file.write(f"Script path: {bot_script}\n")
                    
                    # Starte den Bot im Hintergrund
                    with open(INVITE_BOT_ERROR_LOG, 'a') as log_file:
                        process = subprocess.Popen(
                            [python_exe, bot_script], start_new_session=True,
                            stdout=log_file, stderr=log_file
                        )
                    
                    with open(INVITE_BOT_PID_FILE, 'w') as f:
                        f.write(str(process.pid))
                    
                    flash('Invite Bot wurde gestartet.', 'success')

                except Exception as e:
                    flash(f'Fehler beim Starten: {e}', 'danger')
                    os.makedirs(os.path.dirname(START_DEBUG_LOG_FILE), exist_ok=True)
                    with open(START_DEBUG_LOG_FILE, 'a') as f:
                        f.write(f"{datetime.now()}: Error starting bot: {e}\n")
        elif action == 'stop_invite_bot':
            if os.path.exists(INVITE_BOT_PID_FILE):
                try:
                    with open(INVITE_BOT_PID_FILE, 'r') as f:
                        pid = int(f.read().strip())
                    os.kill(pid, signal.SIGTERM)
                    os.remove(INVITE_BOT_PID_FILE)
                    flash('Invite Bot wurde gestoppt.', 'success')
                except Exception as e:
                    flash(f'Fehler beim Stoppen: {e}', 'danger')
            else:
                flash('Bot läuft nicht.', 'info')
        elif action == 'save_base_config':
            config = json.loads(invite_bot_settings.config_json)
            config.update({
                'is_enabled': 'is_enabled' in request.form,
                'bot_token': request.form.get('bot_token', ''),
                'main_chat_id': request.form.get('main_chat_id', ''),
                'topic_id': request.form.get('topic_id', ''),
                'link_ttl_minutes': request.form.get('link_ttl_minutes', 15, type=int),
                'whitelist_enabled': 'whitelist_enabled' in request.form,
                'whitelist_approval_chat_id': request.form.get('whitelist_approval_chat_id', ''),
                'whitelist_approval_topic_id': request.form.get('whitelist_approval_topic_id', '')
            })
            invite_bot_settings.config_json = json.dumps(config)
            db.session.commit()
            flash('Konfiguration gespeichert.', 'success')
        return redirect(url_for('dashboard.bot_settings'))
    
    config = json.loads(invite_bot_settings.config_json)
    status = get_bot_status_simple()
    
    user_interaction_logs = []
    if os.path.exists(USER_INTERACTION_LOG_FILE):
        with open(USER_INTERACTION_LOG_FILE, 'r', encoding='utf-8') as f:
            user_interaction_logs = f.readlines()[-50:]
            
    invite_bot_logs = []
    if os.path.exists(INVITE_BOT_LOG_FILE):
        with open(INVITE_BOT_LOG_FILE, 'r', encoding='utf-8') as f:
            invite_bot_logs = f.readlines()[-50:]
    # Check if there are errors in the error log as well and append them if needed
    if os.path.exists(INVITE_BOT_ERROR_LOG):
         with open(INVITE_BOT_ERROR_LOG, 'r', encoding='utf-8') as f:
            error_logs = f.readlines()[-20:]
            if error_logs:
                invite_bot_logs.extend(["--- ERROR LOGS ---"] + error_logs)


    return render_template(
        "bot_settings.html", config=config,
        is_invite_running=status['invite']['running'],
        user_interaction_logs=user_interaction_logs,
        invite_bot_logs=invite_bot_logs
    )

@bp.route('/bot-settings/save-content', methods=['POST'])
def save_invite_content():
    settings = get_invite_bot_settings()
    config = json.loads(settings.config_json)
    config.update({
        'start_message': request.form.get('start_message', ''),
        'rules_message': request.form.get('rules_message', ''),
        'blocked_message': request.form.get('blocked_message', ''),
        'privacy_policy': request.form.get('privacy_policy', ''),
        'whitelist_pending_message': request.form.get('whitelist_pending_message', ''),
        'whitelist_rejection_message': request.form.get('whitelist_rejection_message', '')
    })
    settings.config_json = json.dumps(config)
    db.session.commit()
    flash('Texte gespeichert.', 'success')
    return redirect(url_for('dashboard.bot_settings'))

@bp.route('/bot-settings/add-field', methods=['POST'])
def add_field():
    settings = get_invite_bot_settings()
    config = json.loads(settings.config_json)
    fields = config.setdefault('form_fields', [])
    field_id = request.form.get('field_id')
    if any(f['id'] == field_id for f in fields):
        flash('Feld-ID existiert bereits.', 'danger')
        return redirect(url_for('dashboard.bot_settings'))
    
    new_field = {
        'id': field_id, 'emoji': request.form.get('emoji', '🔹'),
        'display_name': request.form.get('display_name', ''),
        'label': request.form.get('label', ''), 'type': request.form.get('type', 'text'),
        'required': 'required' in request.form, 'enabled': True
    }
    if new_field['type'] == 'number':
        new_field['min_age'] = request.form.get('min_age', type=int)
        new_field['min_age_error_msg'] = request.form.get('min_age_error_msg', '')
    
    fields.append(new_field)
    settings.config_json = json.dumps(config)
    db.session.commit()
    flash('Feld hinzugefügt.', 'success')
    return redirect(url_for('dashboard.bot_settings'))

@bp.route('/bot-settings/edit-field', methods=['POST'])
def edit_field():
    settings = get_invite_bot_settings()
    config = json.loads(settings.config_json)
    field_id = request.form.get('field_id')

    for field in config.get('form_fields', []):
        if field['id'] == field_id:
            field['emoji'] = request.form.get('emoji', '🔹')
            field['display_name'] = request.form.get('display_name', '')
            field['label'] = request.form.get('label', '')
            field['type'] = request.form.get('type', 'text')
            field['required'] = 'required' in request.form
            field['enabled'] = 'enabled' in request.form
            if field['type'] == 'number':
                field['min_age'] = request.form.get('min_age', type=int)
                field['min_age_error_msg'] = request.form.get('min_age_error_msg', '')
            break

    settings.config_json = json.dumps(config)
    db.session.commit()
    flash('Feld aktualisiert.', 'success')
    return redirect(url_for('dashboard.bot_settings'))

@bp.route('/bot-settings/delete-field', methods=['POST'])
def delete_field():
    settings = get_invite_bot_settings()
    config = json.loads(settings.config_json)
    field_id = request.form.get('field_id')
    config['form_fields'] = [f for f in config.get('form_fields', []) if f['id'] != field_id]
    settings.config_json = json.dumps(config)
    db.session.commit()
    flash('Feld gelöscht.', 'success')
    return redirect(url_for('dashboard.bot_settings'))

@bp.route('/bot-settings/move-field/<string:field_id>/<string:direction>', methods=['POST'])
def invite_bot_move_field(field_id, direction):
    settings = get_invite_bot_settings()
    config = json.loads(settings.config_json)
    form_fields = config.get('form_fields', [])
    idx = next((i for i, f in enumerate(form_fields) if f['id'] == field_id), -1)
    if idx != -1:
        if direction == 'up' and idx > 0:
            form_fields[idx], form_fields[idx-1] = form_fields[idx-1], form_fields[idx]
        elif direction == 'down' and idx < len(form_fields)-1:
            form_fields[idx], form_fields[idx+1] = form_fields[idx+1], form_fields[idx]
    config['form_fields'] = form_fields
    settings.config_json = json.dumps(config)
    db.session.commit()
    flash('Feld verschoben.', 'success')
    return redirect(url_for('dashboard.bot_settings'))

@bp.route('/bot-settings/clear-logs/user', methods=['POST'])
def clear_user_logs():
    if os.path.exists(USER_INTERACTION_LOG_FILE):
        try:
            with open(USER_INTERACTION_LOG_FILE, 'w') as f: f.write('')
            flash('User Interaktionen Logs gelöscht.', 'success')
        except Exception as e:
            flash(f'Fehler beim Löschen der Logs: {e}', 'danger')
    return redirect(url_for('dashboard.bot_settings'))

@bp.route('/bot-settings/clear-logs/system', methods=['POST'])
def clear_system_logs():
    if os.path.exists(INVITE_BOT_LOG_FILE):
        with open(INVITE_BOT_LOG_FILE, 'w') as f: f.write('')
    if os.path.exists(INVITE_BOT_ERROR_LOG):
        with open(INVITE_BOT_ERROR_LOG, 'w') as f: f.write('')
    flash('System Logs gelöscht.', 'success')
    return redirect(url_for('dashboard.bot_settings'))

@bp.route('/live_moderation')
def live_moderation():
    return render_template('live_moderation.html')

@bp.route('/critical-errors')
def critical_errors():
    logs = []
    if os.path.exists(os.path.join(BASE_DIR, "critical_errors.log")):
        try:
            with open(os.path.join(BASE_DIR, "critical_errors.log"), 'r') as f: logs = f.readlines()
        except: pass
    return render_template("critical_errors.html", critical_logs=logs)

@bp.route('/api/bot-status')
def bot_status_api():
    return jsonify(get_bot_status_simple())
