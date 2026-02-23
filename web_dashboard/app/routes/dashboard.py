from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
import os
import json
import subprocess
import sys
import signal
from datetime import datetime, timedelta
from sqlalchemy import func
from werkzeug.utils import secure_filename
from ..models import db, BotSettings, Broadcast, TopicMapping, User, IDFinderAdmin, IDFinderUser, IDFinderMessage

bp = Blueprint('dashboard', __name__)

# Fixed PROJECT_ROOT to point to the actual project root, not the web_dashboard directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
BASE_DIR = os.path.join(PROJECT_ROOT, 'web_dashboard')

# Bot PID Files
INVITE_BOT_PID_FILE = os.path.join(BASE_DIR, "invite_bot.pid")
ID_FINDER_BOT_PID_FILE = os.path.join(BASE_DIR, "id_finder_bot.pid")

# Log Files
INVITE_BOT_ERROR_LOG = os.path.join(BASE_DIR, "invite_bot_error.log")
USER_INTERACTION_LOG_FILE = os.path.join(PROJECT_ROOT, "user_interactions.log")
INVITE_BOT_LOG_FILE = os.path.join(BASE_DIR, "invite_bot.log")
ID_FINDER_BOT_LOG_FILE = os.path.join(PROJECT_ROOT, "bots", "id_finder_bot", "id_finder_bot.log")
START_DEBUG_LOG_FILE = os.path.join(BASE_DIR, "start_debug.log")
DIRECT_START_OUTPUT_LOG = os.path.join(BASE_DIR, "direct_start_output.log") # New debug log

def is_process_running(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

def get_bot_status_simple():
    status = {
        "invite": {"running": False},
        "quiz": {"running": False},
        "umfrage": {"running": False},
        "outfit": {"running": False},
        "id_finder": {"running": False}
    }
    
    # Invite Bot
    if os.path.exists(INVITE_BOT_PID_FILE):
        try:
            with open(INVITE_BOT_PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            if is_process_running(pid):
                status["invite"]["running"] = True
            else:
                os.remove(INVITE_BOT_PID_FILE)
        except (IOError, ValueError):
            if os.path.exists(INVITE_BOT_PID_FILE):
                os.remove(INVITE_BOT_PID_FILE)

    # ID Finder Bot
    if os.path.exists(ID_FINDER_BOT_PID_FILE):
        try:
            with open(ID_FINDER_BOT_PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            if is_process_running(pid):
                status["id_finder"]["running"] = True
            else:
                os.remove(ID_FINDER_BOT_PID_FILE)
        except (IOError, ValueError):
            if os.path.exists(ID_FINDER_BOT_PID_FILE):
                os.remove(ID_FINDER_BOT_PID_FILE)

    return status

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

@bp.route('/broadcast_manager')
def broadcast_manager():
    topics = TopicMapping.query.all()
    known_topics = {t.topic_id: t.topic_name for t in topics}
    broadcasts = Broadcast.query.order_by(Broadcast.created_at.desc()).all()
    return render_template('broadcast_manager.html', known_topics=known_topics, broadcasts=broadcasts)

@bp.route('/broadcast_manager/save', methods=['POST'])
def save_broadcast():
    text = request.form.get('text')
    topic_id = request.form.get('topic_id')
    send_mode = request.form.get('send_mode', 'standard')
    scheduled_at_str = request.form.get('scheduled_at')
    pin_message = 'pin_message' in request.form
    silent_send = 'silent_send' in request.form
    
    media = request.files.get('media')
    media_path = None
    media_type = None

    if media and media.filename:
        filename = secure_filename(media.filename)
        upload_folder = os.path.join(BASE_DIR, 'app', 'static', 'uploads')
        os.makedirs(upload_folder, exist_ok=True)
        file_path = os.path.join(upload_folder, filename)
        media.save(file_path)
        media_path = f'uploads/{filename}'
        if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
            media_type = 'image'
        elif filename.lower().endswith(('.mp4', '.mov')):
            media_type = 'video'
        else:
            media_type = 'document'

    scheduled_at = None
    if scheduled_at_str:
        try:
            scheduled_at = datetime.strptime(scheduled_at_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            pass

    broadcast = Broadcast(
        text=text,
        topic_id=topic_id,
        send_mode=send_mode,
        media_path=media_path,
        media_type=media_type,
        scheduled_at=scheduled_at,
        pin_message=pin_message,
        silent_send=silent_send
    )
    db.session.add(broadcast)
    db.session.commit()
    flash('Broadcast gespeichert.', 'success')
    return redirect(url_for('dashboard.broadcast_manager'))

@bp.route('/broadcast_manager/topic/save', methods=['POST'])
def save_topic_mapping():
    topic_id = request.form.get('topic_id')
    topic_name = request.form.get('topic_name')
    if topic_id and topic_name:
        mapping = TopicMapping.query.filter_by(topic_id=topic_id).first()
        if mapping:
            mapping.topic_name = topic_name
        else:
            mapping = TopicMapping(topic_id=topic_id, topic_name=topic_name)
            db.session.add(mapping)
        db.session.commit()
        flash('Topic gespeichert.', 'success')
    else:
        flash('Fehler: Topic ID und Name erforderlich.', 'danger')
    return redirect(url_for('dashboard.broadcast_manager'))

@bp.route('/broadcast_manager/topic/delete/<topic_id>', methods=['POST'])
def delete_topic_mapping(topic_id):
    mapping = TopicMapping.query.filter_by(topic_id=topic_id).first()
    if mapping:
        db.session.delete(mapping)
        db.session.commit()
        flash('Topic gelöscht.', 'success')
    return redirect(url_for('dashboard.broadcast_manager'))

@bp.route('/broadcast_manager/delete/<int:broadcast_id>', methods=['POST'])
def delete_broadcast(broadcast_id):
    broadcast = Broadcast.query.get(broadcast_id)
    if broadcast:
        db.session.delete(broadcast)
        db.session.commit()
        flash('Broadcast gelöscht.', 'success')
    return redirect(url_for('dashboard.broadcast_manager'))

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

@bp.route('/quiz-settings', methods=['GET', 'POST'])
def quiz_settings():
    settings = BotSettings.query.filter_by(bot_name='quiz').first()
    if not settings:
        settings = BotSettings(bot_name='quiz', config_json='{}')
        db.session.add(settings)
        db.session.commit()
    
    config = json.loads(settings.config_json)
    
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'save_settings':
            config['bot_token'] = request.form.get('token')
            config['channel_id'] = request.form.get('channel_id')
            config['topic_id'] = request.form.get('topic_id')
        elif action == 'save_schedule':
            config['schedule'] = {
                'enabled': 'schedule_enabled' in request.form,
                'time': request.form.get('schedule_time'),
                'days': [int(d) for d in request.form.getlist('schedule_days')]
            }
        
        settings.config_json = json.dumps(config)
        db.session.commit()
        return redirect(url_for('dashboard.quiz_settings'))

    schedule = config.get('schedule', {'enabled': False, 'time': '12:00', 'days': []})
    stats = {'total': 0, 'asked': 0, 'remaining': 0}
    
    return render_template('quiz_settings.html', 
                           schedule=schedule, 
                           stats=stats, 
                           config=config, 
                           questions_json='[]', 
                           asked_questions_json='[]', 
                           logs=[])

@bp.route('/umfrage-settings', methods=['GET', 'POST'])
def umfrage_settings():
    settings = BotSettings.query.filter_by(bot_name='umfrage').first()
    if not settings:
        settings = BotSettings(bot_name='umfrage', config_json='{}')
        db.session.add(settings)
        db.session.commit()
    
    config = json.loads(settings.config_json)
    if request.method == 'POST':
        # Save logic for umfrage
        pass
    
    return render_template('umfrage_settings.html', config=config, schedule={}, stats={}, logs=[])

@bp.route('/outfit-bot', methods=['GET', 'POST'])
def outfit_bot_dashboard():
    settings = BotSettings.query.filter_by(bot_name='outfit').first()
    if not settings:
        settings = BotSettings(bot_name='outfit', config_json='{}')
        db.session.add(settings)
        db.session.commit()
    
    config = json.loads(settings.config_json)
    return render_template('outfit_bot_dashboard.html', config=config, is_running=False, logs=[], duel_status={'active': False})

@bp.route('/outfit-bot/actions/<action>', methods=['POST'])
def outfit_bot_actions(action):
    # Handle actions
    return redirect(url_for('dashboard.outfit_bot_dashboard'))

# --- ID Finder Bot Logic ---

def get_id_finder_settings():
    settings = BotSettings.query.filter_by(bot_name='id_finder').first()
    if not settings:
        initial_config = {
            'bot_token': '',
            'admin_group_id': 0,
            'main_group_id': 0,
            'admin_log_topic_id': None,
            'delete_commands': True,
            'bot_message_cleanup_seconds': 60,
            'message_logging_enabled': True,
            'message_logging_ignore_commands': True,
            'message_logging_groups_only': False
        }
        settings = BotSettings(bot_name='id_finder', config_json=json.dumps(initial_config))
        db.session.add(settings)
        db.session.commit()
    return settings

@bp.route('/id-finder', methods=['GET'])
def id_finder_dashboard():
    settings = get_id_finder_settings()
    config = json.loads(settings.config_json)
    users = IDFinderUser.query.order_by(IDFinderUser.last_contact.desc()).all()
    status = get_bot_status_simple()
    
    logs = []
    if os.path.exists(ID_FINDER_BOT_LOG_FILE):
         try:
            with open(ID_FINDER_BOT_LOG_FILE, 'r', encoding='utf-8') as f:
                logs = f.readlines()[-50:]
         except: pass

    return render_template('id_finder_dashboard.html', 
                           config=config, 
                           user_registry=users, 
                           is_running=status['id_finder']['running'],
                           logs=logs)

@bp.route('/id-finder/save-config', methods=['POST'])
def id_finder_save_config():
    settings = get_id_finder_settings()
    config = json.loads(settings.config_json)
    
    config['bot_token'] = request.form.get('bot_token', config.get('bot_token', ''))
    
    try: config['admin_group_id'] = int(request.form.get('admin_group_id', 0))
    except: pass
    
    try: config['main_group_id'] = int(request.form.get('main_group_id', 0))
    except: pass
    
    try: config['admin_log_topic_id'] = int(request.form.get('admin_log_topic_id') or 0)
    except: config['admin_log_topic_id'] = None
    
    config['delete_commands'] = 'delete_commands' in request.form
    
    try: config['bot_message_cleanup_seconds'] = int(request.form.get('bot_message_cleanup_seconds', 0))
    except: pass
    
    config['message_logging_enabled'] = 'message_logging_enabled' in request.form
    config['message_logging_ignore_commands'] = 'message_logging_ignore_commands' in request.form
    config['message_logging_groups_only'] = 'message_logging_groups_only' in request.form
    
    settings.config_json = json.dumps(config)
    db.session.commit()
    flash('ID-Finder Konfiguration gespeichert.', 'success')
    return redirect(url_for('dashboard.id_finder_dashboard'))

@bp.route('/id-finder/commands')
def id_finder_commands():
    return render_template('id_finder_commands.html')

@bp.route('/id-finder/admin-panel')
def id_finder_admin_panel():
    admins = IDFinderAdmin.query.all()
    
    # Define available permissions (you can expand this)
    available_permission_groups = {
        "Basis-Moderation": {
            "can_warn": "Nutzer warnen",
            "can_mute": "Nutzer stummschalten",
            "can_ban": "Nutzer bannen"
        },
        "Nachrichten-Management": {
            "can_delete": "Nachrichten löschen",
            "can_purge": "Chat leeren (Purge)"
        },
        "System": {
            "can_broadcast": "Broadcasts senden",
            "can_manage_admins": "Admins verwalten"
        }
    }
    
    return render_template('id_finder_admin_panel.html', 
                           admins=admins, 
                           available_permission_groups=available_permission_groups)

@bp.route('/id-finder/admin-panel/add', methods=['POST'])
def id_finder_add_admin():
    admin_id = request.form.get('admin_id')
    admin_name = request.form.get('admin_name')
    
    if not admin_id or not admin_name:
        flash('ID und Name sind erforderlich.', 'danger')
        return redirect(url_for('dashboard.id_finder_admin_panel'))
    
    try:
        telegram_id = int(admin_id)
        existing = IDFinderAdmin.query.filter_by(telegram_id=telegram_id).first()
        if existing:
            flash('Admin mit dieser ID existiert bereits.', 'warning')
        else:
            new_admin = IDFinderAdmin(telegram_id=telegram_id, name=admin_name)
            # Default permissions: empty or some basic ones?
            db.session.add(new_admin)
            db.session.commit()
            flash('Admin erfolgreich hinzugefügt.', 'success')
    except ValueError:
        flash('Ungültige Telegram ID.', 'danger')
        
    return redirect(url_for('dashboard.id_finder_admin_panel'))

@bp.route('/id-finder/admin-panel/delete', methods=['POST'])
def id_finder_delete_admin():
    admin_id = request.form.get('admin_id')
    admin = IDFinderAdmin.query.filter_by(telegram_id=admin_id).first()
    if admin:
        db.session.delete(admin)
        db.session.commit()
        flash('Admin gelöscht.', 'success')
    else:
        flash('Admin nicht gefunden.', 'danger')
    return redirect(url_for('dashboard.id_finder_admin_panel'))

@bp.route('/id-finder/admin-panel/update', methods=['POST'])
def id_finder_update_admin_permissions():
    admin_id = request.form.get('admin_id')
    admin = IDFinderAdmin.query.filter_by(telegram_id=admin_id).first()
    if not admin:
        flash('Admin nicht gefunden.', 'danger')
        return redirect(url_for('dashboard.id_finder_admin_panel'))
    
    # Collect all permissions from form
    permissions = {}
    # We need to know which keys to look for. For now, we take all form keys except admin_id
    for key in request.form.keys():
        if key != 'admin_id':
            permissions[key] = True
            
    admin.permissions = permissions
    db.session.commit()
    flash(f'Berechtigungen für {admin.name} aktualisiert.', 'success')
    return redirect(url_for('dashboard.id_finder_admin_panel'))

@bp.route('/id-finder/analytics')
def id_finder_analytics():
    days = request.args.get('days', type=int)
    month = request.args.get('month', 0, type=int)
    year = request.args.get('year', 0, type=int)
    
    query = IDFinderMessage.query
    
    if days:
        start_date = datetime.utcnow() - timedelta(days=days)
        query = query.filter(IDFinderMessage.timestamp >= start_date)
    
    if month:
        query = query.filter(func.strftime('%m', IDFinderMessage.timestamp) == f'{month:02d}')
    if year:
        query = query.filter(func.strftime('%Y', IDFinderMessage.timestamp) == str(year))

    messages = query.all()
    total_users = IDFinderUser.query.count()
    total_messages = len(messages)
    
    # Hourly distribution
    busiest_hours = [0] * 24
    for m in messages:
        busiest_hours[m.timestamp.hour] += 1
        
    # Weekday distribution (0=Monday, 6=Sunday)
    busiest_days = [0] * 7
    for m in messages:
        busiest_days[m.timestamp.weekday()] += 1
        
    # Leaderboard & Activity Timeline
    # Timeline is harder without more sophisticated grouping, let's do last 30 days for labels
    labels = []
    total_timeline = []
    if days:
        for i in range(days):
            date = (datetime.utcnow() - timedelta(days=days-1-i)).date()
            labels.append(date.strftime('%d.%m.'))
            total_timeline.append(sum(1 for m in messages if m.timestamp.date() == date))
    else:
        # Default last 7 days
        for i in range(7):
            date = (datetime.utcnow() - timedelta(days=6-i)).date()
            labels.append(date.strftime('%d.%m.'))
            total_timeline.append(sum(1 for m in messages if m.timestamp.date() == date))

    # Leaderboard
    user_stats = {}
    for m in messages:
        uid = m.telegram_user_id
        if uid not in user_stats:
            user = IDFinderUser.query.filter_by(telegram_id=uid).first()
            user_stats[uid] = {'uid': uid, 'name': user.first_name if user else str(uid), 'msgs': 0, 'media': 0, 'reacts': 0}
        user_stats[uid]['msgs'] += 1
        if m.content_type != 'text':
            user_stats[uid]['media'] += 1
            
    leaderboard = sorted(user_stats.values(), key=lambda x: x['msgs'], reverse=True)[:20]

    activity_data = {
        'timeline': {'labels': labels, 'total': total_timeline},
        'busiest_hours': busiest_hours,
        'busiest_days': busiest_days,
        'leaderboard': leaderboard
    }
    
    stats = {
        'total_users': total_users,
        'total_messages': total_messages
    }

    return render_template('id_finder_analytics.html', stats=stats, activity=activity_data)

@bp.route('/api/id-finder/user-activity/<int:uid>')
def id_finder_user_activity_api(uid):
    days = request.args.get('days', 7, type=int)
    
    timeline = []
    for i in range(days):
        date = (datetime.utcnow() - timedelta(days=days-1-i)).date()
        count = IDFinderMessage.query.filter(
            IDFinderMessage.telegram_user_id == uid,
            func.date(IDFinderMessage.timestamp) == date
        ).count()
        timeline.append(count)
        
    return jsonify({'timeline': timeline})

@bp.route('/id-finder/user/<int:user_id>')
def id_finder_user_detail(user_id):
    user = IDFinderUser.query.filter_by(telegram_id=user_id).first()
    if not user:
        flash(f'User {user_id} nicht gefunden.', 'danger')
        return redirect(url_for('dashboard.id_finder_dashboard'))
    
    messages = IDFinderMessage.query.filter_by(telegram_user_id=user_id).order_by(IDFinderMessage.timestamp.desc()).limit(100).all()
    
    return render_template('id_finder_user_detail.html', user=user, messages=messages)

@bp.route('/id-finder/delete-user/<int:user_id>', methods=['POST'])
def id_finder_delete_user(user_id):
    user = IDFinderUser.query.filter_by(telegram_id=user_id).first()
    if user:
        db.session.delete(user)
        db.session.commit()
        flash(f'User {user_id} und alle zugehörigen Nachrichten wurden gelöscht.', 'success')
    else:
        flash('User nicht gefunden.', 'warning')
    
    return redirect(url_for('dashboard.id_finder_dashboard'))

@bp.route('/bot-action/<bot_name>/<action>', methods=['POST'])
def bot_action_route(bot_name, action):
    if bot_name == 'id_finder':
        if action == 'start':
            if os.path.exists(ID_FINDER_BOT_PID_FILE):
                 try:
                    pid_val = int(open(ID_FINDER_BOT_PID_FILE).read().strip())
                    if is_process_running(pid_val):
                        flash('ID-Finder läuft bereits.', 'warning')
                        return redirect(url_for('dashboard.id_finder_dashboard'))
                    else:
                        os.remove(ID_FINDER_BOT_PID_FILE)
                 except:
                    os.remove(ID_FINDER_BOT_PID_FILE)

            try:
                python_exe = sys.executable
                bot_script = os.path.join(PROJECT_ROOT, "bots", "id_finder_bot", "id_finder_bot.py")
                
                # Ensure log directory exists
                os.makedirs(os.path.dirname(ID_FINDER_BOT_LOG_FILE), exist_ok=True)
                
                with open(ID_FINDER_BOT_LOG_FILE, 'a') as log_file:
                    process = subprocess.Popen(
                        [python_exe, bot_script], start_new_session=True,
                        stdout=log_file, stderr=log_file
                    )
                
                with open(ID_FINDER_BOT_PID_FILE, 'w') as f:
                    f.write(str(process.pid))
                
                flash('ID-Finder Bot gestartet.', 'success')
            except Exception as e:
                flash(f'Fehler beim Starten: {e}', 'danger')

        elif action == 'stop':
            if os.path.exists(ID_FINDER_BOT_PID_FILE):
                try:
                    with open(ID_FINDER_BOT_PID_FILE, 'r') as f:
                        pid = int(f.read().strip())
                    os.kill(pid, signal.SIGTERM)
                    os.remove(ID_FINDER_BOT_PID_FILE)
                    flash('ID-Finder Bot gestoppt.', 'success')
                except Exception as e:
                     flash(f'Fehler beim Stoppen: {e}', 'danger')
            else:
                flash('ID-Finder läuft nicht.', 'warning')
                
    return redirect(url_for('dashboard.id_finder_dashboard'))

# --- End ID Finder Bot Logic ---

@bp.route('/minecraft', methods=['GET', 'POST'])
def minecraft_status_page():
    class Config:
        def __init__(self):
            self.mc_host = ''
            self.mc_port = 25565
            self.display_host = ''
            self.display_port = 25565
            self.chat_id = ''
            self.topic_id = ''
            self.update_seconds = 30
            self.delete_player_seconds = 8
            self.status_message_id = ''
            self.host = ''
            self.port = ''
            
    cfg = Config()
    return render_template('minecraft_status.html', cfg=cfg, latency_ms=None, motd=None, players_text=None, error=None, log_paths=[], log_tail='')

@bp.route('/users')
def manage_users():
    users = User.query.all()
    users_dict = {u.username: {'role': u.role} for u in users}
    return render_template('manage_users.html', users=users_dict)

@bp.route('/users/add', methods=['POST'])
def add_user():
    username = request.form.get('username')
    password = request.form.get('password')
    role = request.form.get('role', 'user')
    if username and password:
        if User.query.filter_by(username=username).first():
            flash('Benutzer existiert bereits', 'danger')
        else:
            user = User(username=username, role=role)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash('Benutzer angelegt', 'success')
    return redirect(url_for('dashboard.manage_users'))

@bp.route('/users/delete/<username>', methods=['POST'])
def delete_user(username):
    user = User.query.filter_by(username=username).first()
    if user:
        db.session.delete(user)
        db.session.commit()
        flash('Benutzer gelöscht', 'success')
    return redirect(url_for('dashboard.manage_users'))

@bp.route('/users/edit/<username>', methods=['POST'])
def edit_user(username):
    user = User.query.filter_by(username=username).first()
    if user:
        new_username = request.form.get('new_username')
        new_password = request.form.get('new_password')
        new_role = request.form.get('new_role')
        
        if new_username and new_username != username:
            user.username = new_username
        if new_password:
            user.set_password(new_password)
        if new_role:
            user.role = new_role
        db.session.commit()
        flash('Benutzer aktualisiert', 'success')
    return redirect(url_for('dashboard.manage_users'))
