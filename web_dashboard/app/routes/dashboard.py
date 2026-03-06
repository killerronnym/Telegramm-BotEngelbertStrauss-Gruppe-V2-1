from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, session
from flask_login import login_required, current_user
import os
import json
import subprocess
import sys
import signal
from datetime import datetime, timedelta
from sqlalchemy import func, extract, case, text, true
import traceback
import time
import logging
from werkzeug.utils import secure_filename
from ..models import db, BotSettings, Broadcast, TopicMapping, User, IDFinderAdmin, IDFinderUser, IDFinderMessage, AuditLog, AVAILABLE_PERMISSIONS, AutoReplyRule

# Wir definieren den Blueprint explizit
bp = Blueprint('dashboard', __name__)
logger = logging.getLogger(__name__)

# Pfade berechnen
CURRENT_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_FILE_DIR, '../../..'))
BASE_DIR = os.path.join(PROJECT_ROOT, 'web_dashboard')

# Bot PID Files
INVITE_BOT_PID_FILE = os.path.join(PROJECT_ROOT, "logs", "invite_bot.pid")
ID_FINDER_BOT_PID_FILE = os.path.join(PROJECT_ROOT, "logs", "id_finder_bot.pid")
TIKTOK_BOT_PID_FILE = os.path.join(PROJECT_ROOT, "logs", "tiktok_bot.pid")
QUIZ_BOT_PID_FILE = os.path.join(PROJECT_ROOT, "logs", "quiz_bot.pid")
UMFRAGE_BOT_PID_FILE = os.path.join(PROJECT_ROOT, "logs", "umfrage_bot.pid")
OUTFIT_BOT_PID_FILE = os.path.join(PROJECT_ROOT, "logs", "outfit_bot.pid")

# Log Files
INVITE_BOT_LOG_FILE = os.path.join(PROJECT_ROOT, "logs", "invite_bot.log")
ID_FINDER_BOT_LOG_FILE = os.path.join(PROJECT_ROOT, "logs", "id_finder_bot.log")
TIKTOK_BOT_LOG_FILE = os.path.join(PROJECT_ROOT, "logs", "tiktok_bot.log")
QUIZ_BOT_LOG_FILE = os.path.join(PROJECT_ROOT, "logs", "quiz_bot.log")
UMFRAGE_BOT_LOG_FILE = os.path.join(PROJECT_ROOT, "logs", "umfrage_bot.log")
OUTFIT_BOT_LOG_FILE = os.path.join(PROJECT_ROOT, "logs", "outfit_bot.log")

def is_process_running(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

def safe_clear_log(filepath):
    if not os.path.exists(filepath): return True
    try:
        # Versuch 1: Löschen
        os.remove(filepath)
        return True
    except Exception as e:
        # Versuch 2: Leeren (Truncate), falls Löschen fehlschlägt (File In Use)
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.truncate(0)
            return True
        except Exception as e2:
            print(f"Error clearing log {filepath}: {e}, Truncate error: {e2}")
            return False

def get_master_pid():
    pfile = os.path.join(PROJECT_ROOT, "logs", "main_bot.pid")
    if os.path.exists(pfile):
        try:
            with open(pfile, 'r') as f: return int(f.read().strip())
        except: return None
    return None

def fmt_dt(d):
    """Helper for date formatting (Handles mysql date objects vs sqlite strings)"""
    if not d: return 'Unknown'
    if hasattr(d, 'strftime'): return d.strftime('%d.%m')
    try:
        s = str(d)
        if '-' in s:
            parts = s.split('-')
            if len(parts) >= 3: return f"{parts[2][:2]}.{parts[1]}"
        return s
    except: return 'Err'

def get_bot_status_simple():
    status = {
        "invite": {"running": False}, "quiz": {"running": False}, 
        "umfrage": {"running": False}, "outfit": {"running": False}, 
        "id_finder": {"running": False}, "tiktok": {"running": False},
        "auto_responder": {"running": False}, "profanity_filter": {"running": False},
        "birthday": {"running": False}, "report_bot": {"running": False}, 
        "event_bot": {"running": False}
    }
    
    # ID Finder (Master Bot) ist der einzige echte Prozess
    pid = get_master_pid()
    if pid and is_process_running(pid):
        status["id_finder"]["running"] = True
    
    # Alle anderen Module lesen ihren "Aktiv" Status aus der Datenbank
    try:
        from web_dashboard.app.models import BotSettings
        settings = BotSettings.query.all()
        for s in settings:
            if s.bot_name in status: # Check if bot_name is in status dict
                if s.config_json:
                    c = json.loads(s.config_json)
                    status[s.bot_name]["config"] = c
                    if s.bot_name == 'id_finder':
                        if 'last_heartbeat' in c:
                            status['id_finder']['last_heartbeat'] = c['last_heartbeat']
                    else: # For other bots, check 'is_active'
                        if c.get('is_active'):
                            status[s.bot_name]["running"] = True
    except Exception as e:
        print(f"Fehler beim Lesen des Bot-Status: {e}")
        
    return status

@bp.context_processor
def inject_globals():
    return {"bot_status": get_bot_status_simple()}

@bp.route('/')
@bp.route('/dashboard')
@login_required
def index():
    version_path = os.path.join(PROJECT_ROOT, 'version.json')
    version = {"version": "1.0.0"}
    if os.path.exists(version_path):
        try:
            with open(version_path, 'r') as f: version = json.load(f)
        except: pass
    layout_settings = BotSettings.query.filter_by(bot_name='dashboard_layout').first()
    layout = json.loads(layout_settings.config_json) if layout_settings else None
    return render_template('index.html', version=version, layout=layout)

@bp.route('/api/dashboard/save-layout', methods=['POST'])
@login_required
def save_dashboard_layout():
    data = request.json
    s = BotSettings.query.filter_by(bot_name='dashboard_layout').first()
    if not s: s = BotSettings(bot_name='dashboard_layout', config_json=json.dumps(data)); db.session.add(s)
    else: s.config_json = json.dumps(data)
    db.session.commit()
    return jsonify({"success": True})

# --- AUTO RESPONDER ROUTE ---
@bp.route('/auto-responder')
@login_required
def auto_responder():
    rules = AutoReplyRule.query.order_by(AutoReplyRule.id.desc()).all()
    # Check if the auto_responder bot is toggled 'on' in the main settings
    s = BotSettings.query.filter_by(bot_name='auto_responder').first()
    is_running = False
    if s and s.config_json:
        try:
            cfg = json.loads(s.config_json)
            is_running = cfg.get('is_active', False)
        except:
            pass
    return render_template('auto_responder.html', rules=rules, is_running=is_running)

# --- INVITE BOT ROUTES ---
@bp.route('/bot-settings', methods=["GET", "POST"])
@login_required
def bot_settings():
    s = BotSettings.query.filter_by(bot_name='invite').first()
    if not s:
        cfg = {'is_enabled': False, 'bot_token': '', 'main_chat_id': '', 'topic_id': '', 'link_ttl_minutes': 15, 'start_message': 'Willkommen!', 'rules_message': 'Bitte beachte die Regeln.', 'blocked_message': 'Du bist gesperrt.', 'privacy_policy': 'Datenschutz...', 'form_fields': [], 'whitelist_enabled': False, 'whitelist_approval_chat_id': '', 'whitelist_approval_topic_id': '', 'whitelist_pending_message': 'Wird geprüft.', 'whitelist_rejection_message': 'Abgelehnt.'}
        s = BotSettings(bot_name='invite', config_json=json.dumps(cfg)); db.session.add(s); db.session.commit()
    
    if request.method == 'POST':
        action = request.form.get('action')
        config = json.loads(s.config_json)
        if action == 'save_base_config':
            config.update({'is_enabled': 'is_enabled' in request.form, 'bot_token': request.form.get('bot_token', ''), 'main_chat_id': request.form.get('main_chat_id', ''), 'topic_id': request.form.get('topic_id', ''), 'link_ttl_minutes': request.form.get('link_ttl_minutes', 15, type=int), 'whitelist_enabled': 'whitelist_enabled' in request.form, 'whitelist_approval_chat_id': request.form.get('whitelist_approval_chat_id', ''), 'whitelist_approval_topic_id': request.form.get('whitelist_approval_topic_id', '')})
            s.config_json = json.dumps(config); db.session.commit(); flash('Gespeichert.', 'success')
        return redirect(url_for('dashboard.bot_settings'))

    logs = []
    if os.path.exists(INVITE_BOT_LOG_FILE):
        with open(INVITE_BOT_LOG_FILE, 'r') as f: logs = f.readlines()[-50:]
        
    user_logs = []
    try:
        from ..models import InviteLog
        db_logs = InviteLog.query.order_by(InviteLog.timestamp.desc()).limit(100).all()
        for log in db_logs:
            user_logs.append(f"{log.timestamp.strftime('%Y-%m-%d %H:%M:%S')} - User ID: {log.telegram_user_id} - Username: @{log.username} - Message: {log.action}")
    except Exception as e:
        pass
        
    return render_template("bot_settings.html", config=json.loads(s.config_json), is_invite_running=get_bot_status_simple()['invite']['running'], user_interaction_logs=user_logs, invite_bot_logs=logs)

@bp.route('/bot-settings/save-content', methods=['POST'])
@login_required
def save_invite_content():
    s = BotSettings.query.filter_by(bot_name='invite').first()
    cfg = json.loads(s.config_json)
    cfg.update({k: request.form.get(k, '') for k in ['start_message', 'rules_message', 'blocked_message', 'privacy_policy', 'whitelist_pending_message', 'whitelist_rejection_message']})
    s.config_json = json.dumps(cfg, ensure_ascii=True)
    db.session.commit()
    flash('Texte gespeichert.', 'success')
    return redirect(url_for('dashboard.bot_settings'))

@bp.route('/bot-settings/add-field', methods=['POST'])
@login_required
def add_field():
    s = BotSettings.query.filter_by(bot_name='invite').first()
    cfg = json.loads(s.config_json); fields = cfg.setdefault('form_fields', [])
    min_age = request.form.get('min_age')
    fid = request.form.get('field_id', 'field').strip().lower()
    if not fid: fid = "field"
    
    # Ensure ID is unique
    existing_ids = [f['id'] for f in cfg.get('form_fields', [])]
    base_id = fid
    counter = 1
    while fid in existing_ids:
        fid = f"{base_id}_{counter}"
        counter += 1

    cfg.setdefault('form_fields', []).append({
        'id': fid,
        'emoji': request.form.get('emoji', '🔹'), 
        'display_name': request.form.get('display_name', 'Neues Feld'), 
        'label': request.form.get('label', ''), 
        'type': request.form.get('type', 'text'), 
        'required': 'required' in request.form, 
        'enabled': True,
        'min_age': int(min_age) if min_age and min_age.isdigit() else None,
        'min_age_error_msg': request.form.get('min_age_error_msg', '')
    })
    s.config_json = json.dumps(cfg, ensure_ascii=True); db.session.commit(); return redirect(url_for('dashboard.bot_settings'))

@bp.route('/bot-settings/edit-field', methods=['POST'])
@login_required
def edit_field():
    s = BotSettings.query.filter_by(bot_name='invite').first()
    cfg = json.loads(s.config_json); fid = request.form.get('field_id')
    for f in cfg.get('form_fields', []):
        if f['id'] == fid:
            min_age = request.form.get('min_age')
            f.update({
                'emoji': request.form.get('emoji'), 
                'display_name': request.form.get('display_name'), 
                'label': request.form.get('label'), 
                'type': request.form.get('type'), 
                'required': 'required' in request.form, 
                'enabled': 'enabled' in request.form,
                'min_age': int(min_age) if min_age and min_age.isdigit() else None,
                'min_age_error_msg': request.form.get('min_age_error_msg', '')
            })
    s.config_json = json.dumps(cfg, ensure_ascii=True); db.session.commit(); return redirect(url_for('dashboard.bot_settings'))

@bp.route('/bot-settings/delete-field', methods=['POST'])
@login_required
def delete_field():
    s = BotSettings.query.filter_by(bot_name='invite').first()
    cfg = json.loads(s.config_json)
    fid = request.form.get('field_id')
    # Use a more robust check: delete the first one that matches to handle existing duplicates
    fields = cfg.get('form_fields', [])
    for i, f in enumerate(fields):
        if f['id'] == fid:
            fields.pop(i)
            break
    s.config_json = json.dumps(cfg, ensure_ascii=True)
    db.session.commit()
    return redirect(url_for('dashboard.bot_settings'))

@bp.route('/bot-settings/move-field/<string:field_id>/<string:direction>', methods=['POST'])
@login_required
def invite_bot_move_field(field_id, direction):
    s = BotSettings.query.filter_by(bot_name='invite').first()
    cfg = json.loads(s.config_json); fs = cfg.get('form_fields', [])
    idx = next((i for i, f in enumerate(fs) if f['id'] == field_id), -1)
    if idx != -1:
        if direction == 'up' and idx > 0: fs[idx], fs[idx-1] = fs[idx-1], fs[idx]
        elif direction == 'down' and idx < len(fs)-1: fs[idx], fs[idx+1] = fs[idx+1], fs[idx]
    s.config_json = json.dumps(cfg); db.session.commit(); return redirect(url_for('dashboard.bot_settings'))

@bp.route('/bot-settings/reorder-fields', methods=['POST'])
@login_required
def invite_bot_reorder_fields():
    data = request.get_json()
    if not data or 'field_ids' not in data:
        return jsonify({"success": False, "error": "Invalid data"}), 400
    
    s = BotSettings.query.filter_by(bot_name='invite').first()
    if not s: return jsonify({"success": False, "error": "Settings not found"}), 404
    
    cfg = json.loads(s.config_json); fs = cfg.get('form_fields', [])
    existing_fields = {f.get('id'): f for f in fs}
    
    new_fields = []
    for fid in data['field_ids']:
        if fid in existing_fields:
            new_fields.append(existing_fields[fid])
            
    # Keep missing fields
    new_ids = set(data['field_ids'])
    for fid, f in existing_fields.items():
        if fid not in new_ids:
            new_fields.append(f)
            
    cfg['form_fields'] = new_fields
    s.config_json = json.dumps(cfg)
    db.session.commit()
    return jsonify({"success": True})

@bp.route('/bot-settings/add-command', methods=['POST'])
@login_required
def add_custom_command():
    s = BotSettings.query.filter_by(bot_name='invite').first()
    cfg = json.loads(s.config_json)
    commands = cfg.setdefault('custom_commands', {})
    
    cmd = request.form.get('command_name', '').strip().lower().replace('/', '')
    resp = request.form.get('response_text', '').strip()
    
    if cmd and resp:
        commands[cmd] = resp
        s.config_json = json.dumps(cfg)
        db.session.commit()
        flash(f'Befehl /{cmd} hinzugefügt.', 'success')
    else:
        flash('Befehl und Antwort sind erforderlich.', 'danger')
        
    return redirect(url_for('dashboard.bot_settings'))

@bp.route('/bot-settings/delete-command', methods=['POST'])
@login_required
def delete_custom_command():
    s = BotSettings.query.filter_by(bot_name='invite').first()
    cfg = json.loads(s.config_json)
    commands = cfg.get('custom_commands', {})
    
    cmd = request.form.get('command_name')
    if cmd in commands:
        del commands[cmd]
        s.config_json = json.dumps(cfg)
        db.session.commit()
        flash(f'Befehl /{cmd} gelöscht.', 'info')
        
    return redirect(url_for('dashboard.bot_settings'))

@bp.route('/bot-settings/save-puppy-config', methods=['POST'])
@login_required
def save_puppy_config():
    s = BotSettings.query.filter_by(bot_name='invite').first()
    cfg = json.loads(s.config_json)
    
    cfg['puppy_config'] = {
        'enabled': 'enabled' in request.form,
        'label': request.form.get('label', '').strip(),
        'min_age': int(request.form.get('min_age', 1)),
        'required': 'required' in request.form,
        'error_msg': request.form.get('error_msg', '').strip()
    }
    
    s.config_json = json.dumps(cfg)
    db.session.commit()
    flash('Puppy-Alter Einstellungen gespeichert.', 'success')
    return redirect(url_for('dashboard.bot_settings', _anchor='puppy-panel'))

@bp.route('/bot-settings/clear-logs/user', methods=['POST'])
@login_required
def clear_user_logs():
    from ..models import InviteLog
    try:
        InviteLog.query.delete()
        db.session.commit()
    except:
        db.session.rollback()
    return redirect(url_for('dashboard.bot_settings'))

@bp.route('/bot-settings/clear-logs/system', methods=['POST'])
@login_required
def clear_system_logs():
    if not safe_clear_log(INVITE_BOT_LOG_FILE):
        flash('System-Logs konnten nicht gelöscht werden (File In Use).', 'warning')
    else:
        flash('System-Logs erfolgreich gelöscht.', 'success')
    return redirect(url_for('dashboard.bot_settings'))

# --- BROADCAST ROUTES ---
@bp.route('/broadcast_manager')
@login_required
def broadcast_manager():
    ts = TopicMapping.query.all(); bs = Broadcast.query.order_by(Broadcast.created_at.desc()).all()
    return render_template('broadcast_manager.html', known_topics={str(t.topic_id): t.topic_name for t in ts}, broadcasts=bs)

@bp.route('/broadcast_manager/save', methods=['POST'])
@login_required
def save_broadcast():
    action = request.form.get('action', 'send_now')
    fdir = os.path.join(BASE_DIR, 'app', 'static', 'uploads')
    os.makedirs(fdir, exist_ok=True)

    # Handle multiple file uploads
    uploaded = request.files.getlist('media')
    saved_paths = []
    first_mtype = None
    for m in uploaded:
        if m and m.filename:
            fname = secure_filename(m.filename)
            m.save(os.path.join(fdir, fname))
            rel = f'uploads/{fname}'
            saved_paths.append(rel)
            if first_mtype is None:
                first_mtype = 'image' if fname.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')) else 'video'

    # Determine send time
    if action == 'schedule':
        raw_dt = request.form.get('scheduled_at')
        try:
            scheduled_at = datetime.strptime(raw_dt, '%Y-%m-%dT%H:%M') if raw_dt else datetime.utcnow()
        except ValueError:
            scheduled_at = datetime.utcnow()
    else:
        scheduled_at = datetime.utcnow()

    # Single-file: media_path; multi-file: media_files as JSON list
    mpath = saved_paths[0] if len(saved_paths) == 1 else None
    mtype = first_mtype if len(saved_paths) == 1 else None
    mfiles_json = json.dumps(saved_paths) if len(saved_paths) > 1 else None

    b = Broadcast(
        text=request.form.get('text'),
        topic_id=request.form.get('topic_id') or None,
        send_mode=request.form.get('send_mode', 'standard'),
        scheduled_at=scheduled_at,
        status='pending',
        media_path=mpath,
        media_type=mtype,
        media_files=mfiles_json,
        spoiler='spoiler' in request.form,
        pin_message='pin_message' in request.form,
        silent_send='silent_send' in request.form,
    )
    db.session.add(b)
    db.session.commit()

    if action == 'send_now':
        flash('Nachricht in die Warteschlange eingestellt. Wird in Kuerze gesendet.', 'success')
    else:
        flash(f'Nachricht geplant fuer {scheduled_at.strftime("%d.%m.%Y %H:%M")} UTC.', 'success')

    return redirect(url_for('dashboard.broadcast_manager'))


@bp.route('/broadcast_manager/topic/save', methods=['POST'])
@login_required
def save_topic_mapping():
    tid, tname = request.form.get('topic_id'), request.form.get('topic_name')
    m = TopicMapping.query.filter_by(topic_id=tid).first()
    if m: m.topic_name = tname
    else: db.session.add(TopicMapping(topic_id=tid, topic_name=tname))
    db.session.commit(); return redirect(url_for('dashboard.broadcast_manager'))

@bp.route('/broadcast_manager/topic/delete/<topic_id>', methods=['POST'])
@login_required
def delete_topic_mapping(topic_id):
    m = TopicMapping.query.filter_by(topic_id=topic_id).first()
    if m: db.session.delete(m); db.session.commit()
    return redirect(url_for('dashboard.broadcast_manager'))

@bp.route('/broadcast_manager/delete/<int:broadcast_id>', methods=['POST'])
@login_required
def delete_broadcast(broadcast_id):
    b = Broadcast.query.get(broadcast_id)
    if b: db.session.delete(b); db.session.commit()
    return redirect(url_for('dashboard.broadcast_manager'))

# --- OTHER BOT ROUTES ---
@bp.route('/live-moderation')
@login_required
def live_moderation(): return render_template('live_moderation.html')

@bp.route('/quiz-settings', methods=['GET', 'POST'])
@login_required
def quiz_settings():
    s = BotSettings.query.filter_by(bot_name='quiz').first()
    if not s:
        cfg = {"bot_token": "", "channel_id": "", "topic_id": "", "schedule": {"enabled": False, "time": "12:00", "days": []}}
        s = BotSettings(bot_name='quiz', config_json=json.dumps(cfg))
        db.session.add(s); db.session.commit()
    
    cfg = json.loads(s.config_json)
    
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'save_settings':
            # Token wird zentral über ID-Finder verwaltet
            # cfg['bot_token'] = request.form.get('token')
            cfg['channel_id'] = request.form.get('channel_id')
            cfg['topic_id'] = request.form.get('topic_id')
        elif action == 'save_schedule':
            cfg['schedule'] = {
                'enabled': 'schedule_enabled' in request.form,
                'time': request.form.get('schedule_time', '12:00'),
                'days': [int(d) for d in request.form.getlist('schedule_days')]
            }
        elif action == 'save_questions':
            q_json = request.form.get('questions_json')
            try:
                data = json.loads(q_json)
                q_path = os.path.join(PROJECT_ROOT, "data", "quizfragen.json")
                os.makedirs(os.path.dirname(q_path), exist_ok=True)
                with open(q_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                flash('Fragen gespeichert.', 'success')
            except Exception as e:
                flash(f'Fehler beim Speichern der Fragen: {e}', 'danger')
        elif action == 'save_asked_questions':
            aq_json = request.form.get('asked_questions_json')
            try:
                data = json.loads(aq_json)
                aq_path = os.path.join(PROJECT_ROOT, "instance", "quizfragen_gestellt.json")
                os.makedirs(os.path.dirname(aq_path), exist_ok=True)
                with open(aq_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                flash('Protokoll gespeichert.', 'success')
            except Exception as e:
                flash(f'Fehler beim Speichern des Protokolls: {e}', 'danger')
        
        s.config_json = json.dumps(cfg)
        db.session.commit()
        if action in ['save_settings', 'save_schedule']: flash('Einstellungen gespeichert.', 'success')
        return redirect(url_for('dashboard.quiz_settings'))

    # Load Data for Template
    q_path = os.path.join(PROJECT_ROOT, "data", "quizfragen.json")
    aq_path = os.path.join(PROJECT_ROOT, "instance", "quizfragen_gestellt.json")
    
    questions = []
    if os.path.exists(q_path):
        try:
            with open(q_path, 'r', encoding='utf-8') as f: questions = json.load(f)
        except: pass
        
    asked_questions = []
    if os.path.exists(aq_path):
        try:
            with open(aq_path, 'r', encoding='utf-8') as f: asked_questions = json.load(f)
        except: pass

    logs = []
    if os.path.exists(QUIZ_BOT_LOG_FILE):
        try:
            with open(QUIZ_BOT_LOG_FILE, 'r', encoding='utf-8') as f: logs = f.readlines()[-50:]
        except: pass

    stats = {
        'total': len(questions),
        'asked': len(asked_questions),
        'remaining': max(0, len(questions) - len(asked_questions))
    }

    return render_template('quiz_settings.html', 
                          schedule=cfg.get('schedule', {}), 
                          stats=stats, 
                          config=cfg, 
                          questions_json=json.dumps(questions, indent=2, ensure_ascii=False), 
                          asked_questions_json=json.dumps(asked_questions, indent=2, ensure_ascii=False), 
                          logs=logs)

@bp.route('/quiz/send-random', methods=['POST'])
@login_required
def quiz_send_random():
    try:
        tfile = os.path.abspath(os.path.join(PROJECT_ROOT, "bots", "quiz_bot", "send_now.tmp"))
        os.makedirs(os.path.dirname(tfile), exist_ok=True)
        with open(tfile, 'w') as f: f.write('1')
        
        # Verbose Log to file
        trigger_log = os.path.join(PROJECT_ROOT, "logs", "trigger.log")
        with open(trigger_log, 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now()}] Quiz Trigger written to: {tfile}\n")
            
        # Audit Log
        details = f"Quiz-Trigger geschrieben nach: {tfile}"
        log_entry = AuditLog(user_id=current_user.id, action="quiz_send_manual", details=details)
        db.session.add(log_entry)
        db.session.commit()
        
        flash('Trigger an Quiz-Bot gesendet. Die Nachricht sollte in ca. 10 Sekunden erscheinen.', 'success')
    except Exception as e:
        flash(f'Fehler beim Sende-Trigger: {e}', 'danger')
        print(f"Error in quiz_send_random: {e}")
        
    return redirect(url_for('dashboard.quiz_settings'))

@bp.route('/umfrage-settings', methods=['GET', 'POST'])
@login_required
def umfrage_settings():
    s = BotSettings.query.filter_by(bot_name='umfrage').first()
    if not s:
        cfg = {"bot_token": "", "channel_id": "", "topic_id": "", "schedule": {"enabled": False, "time": "12:00", "days": []}}
        s = BotSettings(bot_name='umfrage', config_json=json.dumps(cfg))
        db.session.add(s); db.session.commit()
    
    cfg = json.loads(s.config_json)
    
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'save_settings':
            # Token wird zentral über ID-Finder verwaltet
            # cfg['bot_token'] = request.form.get('token')
            cfg['channel_id'] = request.form.get('channel_id')
            cfg['topic_id'] = request.form.get('topic_id')
        elif action == 'save_schedule':
            cfg['schedule'] = {
                'enabled': 'schedule_enabled' in request.form,
                'time': request.form.get('schedule_time', '12:00'),
                'days': [int(d) for d in request.form.getlist('schedule_days')]
            }
        elif action == 'save_polls':
            p_json = request.form.get('polls_json')
            try:
                data = json.loads(p_json)
                p_path = os.path.join(PROJECT_ROOT, "data", "umfragen.json")
                os.makedirs(os.path.dirname(p_path), exist_ok=True)
                with open(p_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                flash('Umfragen gespeichert.', 'success')
            except Exception as e:
                flash(f'Fehler beim Speichern der Umfragen: {e}', 'danger')
        elif action == 'save_asked_polls':
            up_json = request.form.get('asked_polls_json')
            try:
                data = json.loads(up_json)
                up_path = os.path.join(PROJECT_ROOT, "instance", "umfragen_gestellt.json")
                os.makedirs(os.path.dirname(up_path), exist_ok=True)
                with open(up_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                flash('Gestellte-Umfragen-Protokoll gespeichert.', 'success')
            except Exception as e:
                flash(f'Fehler beim Speichern des Protokolls: {e}', 'danger')

        s.config_json = json.dumps(cfg)
        db.session.commit()
        if action in ['save_settings', 'save_schedule']: flash('Einstellungen gespeichert.', 'success')
        return redirect(url_for('dashboard.umfrage_settings'))

    # Load Data
    p_path = os.path.join(PROJECT_ROOT, "data", "umfragen.json")
    up_path = os.path.join(PROJECT_ROOT, "instance", "umfragen_gestellt.json")
    
    polls = []
    if os.path.exists(p_path):
        try:
            with open(p_path, 'r', encoding='utf-8') as f: polls = json.load(f)
        except: pass
        
    used_polls = []
    if os.path.exists(up_path):
        try:
            with open(up_path, 'r', encoding='utf-8') as f: used_polls = json.load(f)
        except: pass

    logs = []
    if os.path.exists(UMFRAGE_BOT_LOG_FILE):
        try:
            with open(UMFRAGE_BOT_LOG_FILE, 'r', encoding='utf-8') as f: logs = f.readlines()[-50:]
        except: pass

    stats = {
        'total': len(polls),
        'asked': len(used_polls),
        'remaining': max(0, len(polls) - len(used_polls))
    }

    return render_template('umfrage_settings.html', 
                          config=cfg, 
                          schedule=cfg.get('schedule', {}), 
                          stats=stats, 
                          logs=logs,
                          polls_json=json.dumps(polls, indent=2, ensure_ascii=False),
                          asked_polls_json=json.dumps(used_polls, indent=2, ensure_ascii=False))

@bp.route('/umfrage/send-now', methods=['POST'])
@login_required
def umfrage_send_now():
    try:
        tfile = os.path.abspath(os.path.join(PROJECT_ROOT, "bots", "umfrage_bot", "send_now.tmp"))
        os.makedirs(os.path.dirname(tfile), exist_ok=True)
        with open(tfile, 'w') as f: f.write('1')
        
        # Verbose Log to file
        trigger_log = os.path.join(PROJECT_ROOT, "logs", "trigger.log")
        with open(trigger_log, 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now()}] Umfrage Trigger written to: {tfile}\n")
            
        # Audit Log
        details = f"Umfrage-Trigger geschrieben nach: {tfile}"
        log_entry = AuditLog(user_id=current_user.id, action="umfrage_send_manual", details=details)
        db.session.add(log_entry)
        db.session.commit()
        
        flash('Trigger an Umfrage-Bot gesendet.', 'success')
    except Exception as e:
        flash(f'Fehler beim Sende-Trigger: {e}', 'danger')
        print(f"Error in umfrage_send_now: {e}")
        
    return redirect(url_for('dashboard.umfrage_settings'))

@bp.route('/outfit-bot', methods=['GET', 'POST'])
@login_required
def outfit_bot_dashboard():
    s = BotSettings.query.filter_by(bot_name='outfit').first()
    if not s:
        cfg = {
            "CHAT_ID": "", "TOPIC_ID": "", "POST_TIME": "18:00", "WINNER_TIME": "22:00",
            "AUTO_POST_ENABLED": True, "ADMIN_USER_IDS": [], "DUEL_MODE": False,
            "DUEL_TYPE": "tie_breaker", "DUEL_DURATION_MINUTES": 60, "BOT_TOKEN": ""
        }
        s = BotSettings(bot_name='outfit', config_json=json.dumps(cfg))
        db.session.add(s); db.session.commit()
    
    cfg = json.loads(s.config_json)
    
    logs = []
    if os.path.exists(OUTFIT_BOT_LOG_FILE):
        try:
            with open(OUTFIT_BOT_LOG_FILE, 'r', encoding='utf-8') as f: logs = f.readlines()[-50:]
        except: pass
        
    # Load Duel Status from data file
    data_path = os.path.join(PROJECT_ROOT, "instance", "outfit_bot_data.json")
    duel_status = {'active': False}
    if os.path.exists(data_path):
        try:
            with open(data_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data.get('contest_active'):
                    duel_status = {'active': True, 'contestants': f"{len(data.get('submissions', {}))} Teilnehmer"}
        except: pass

    return render_template('outfit_bot_dashboard.html', 
                          config=cfg, 
                          is_running=get_bot_status_simple()['outfit']['running'], 
                          logs=logs, 
                          duel_status=duel_status)

@bp.route('/outfit-bot/actions/<action>', methods=['POST'])
@login_required
def outfit_bot_actions(action):
    s = BotSettings.query.filter_by(bot_name='outfit').first()
    if not s:
        cfg = DEFAULT_CONFIG.copy()
        s = BotSettings(bot_name='outfit', config_json=json.dumps(cfg))
        db.session.add(s); db.session.commit()
    
    cfg = json.loads(s.config_json)
    
    if action == 'save_config':
        cfg.update({
            # 'BOT_TOKEN': request.form.get('BOT_TOKEN'),
            'CHAT_ID': request.form.get('CHAT_ID'),
            'TOPIC_ID': request.form.get('TOPIC_ID'),
            'AUTO_POST_ENABLED': 'AUTO_POST_ENABLED' in request.form,
            'POST_TIME': request.form.get('POST_TIME', '18:00'),
            'WINNER_TIME': request.form.get('WINNER_TIME', '22:00'),
            'DUEL_MODE': 'DUEL_MODE' in request.form,
            'DUEL_TYPE': request.form.get('DUEL_TYPE', 'tie_breaker'),
            'DUEL_DURATION_MINUTES': int(request.form.get('DUEL_DURATION_MINUTES', 60)),
            'ADMIN_USER_IDS': [uid.strip() for uid in request.form.get('ADMIN_USER_IDS', '').split(',') if uid.strip()]
        })
        s.config_json = json.dumps(cfg)
        db.session.commit()
        flash('Outfit-Konfiguration gespeichert.', 'success')
    
    elif action == 'start_contest':
        tfile = os.path.join(PROJECT_ROOT, "bots", "outfit_bot", "start_contest.tmp")
        # Ensure the bot can notice this file. We should probably use a standard trigger file name or mechanism.
        # Based on outfit_bot.py, it doesn't have a trigger file mechanism yet, only schedule.
        # Let's add it to outfit_bot.py or just use a message file system.
        with open(tfile, 'w') as f: f.write('1')
        flash('Befehl zum Starten des Wettbewerbs gesendet.', 'info')
    
    elif action == 'announce_winner':
        tfile = os.path.join(PROJECT_ROOT, "bots", "outfit_bot", "announce_winner.tmp")
        with open(tfile, 'w') as f: f.write('1')
        flash('Befehl zum Auslosen des Gewinners gesendet.', 'info')
        
    elif action == 'clear_logs':
        if not safe_clear_log(OUTFIT_BOT_LOG_FILE):
            flash('Logs konnten nicht gelöscht werden (File In Use).', 'warning')
        else:
            flash('Logs gelöscht.', 'success')
        
    return redirect(url_for('dashboard.outfit_bot_dashboard'))

@bp.route('/critical-errors')
@login_required
def critical_errors():
    logs = []
    lpath = os.path.join(PROJECT_ROOT, "logs", "critical_errors.log")
    if os.path.exists(lpath):
        with open(lpath, 'r') as f: logs = f.readlines()
    return render_template("critical_errors.html", critical_logs=logs)

@bp.route('/critical-errors/clear', methods=['POST'])
@login_required
def clear_critical_errors():
    lpath = os.path.join(PROJECT_ROOT, "logs", "critical_errors.log")
    if not safe_clear_log(lpath):
        flash('Kritische Fehler konnten nicht gelöscht werden.', 'warning')
    return redirect(url_for('dashboard.critical_errors'))

@bp.route('/id-finder')
@login_required
def id_finder_dashboard():
    s = BotSettings.query.filter_by(bot_name='id_finder').first()
    if not s:
        cfg = {'bot_token': '', 'admin_group_id': 0, 'main_group_id': 0}
        s = BotSettings(bot_name='id_finder', config_json=json.dumps(cfg))
        db.session.add(s)
        db.session.commit()
    
    cfg = json.loads(s.config_json)
    us = IDFinderUser.query.order_by(IDFinderUser.last_contact.desc()).all()
    return render_template('id_finder_dashboard.html', config=cfg, user_registry=us, is_running=get_bot_status_simple()['id_finder']['running'], logs=[])

@bp.route('/id-finder/save-config', methods=['POST'])
@login_required
def id_finder_save_config():
    s = BotSettings.query.filter_by(bot_name='id_finder').first()
    cfg = json.loads(s.config_json)
    admin_group_id = request.form.get('admin_group_id', '').strip().replace('--', '-')
    main_group_id = request.form.get('main_group_id', '').strip().replace('--', '-')
    admin_log_topic_id = request.form.get('admin_log_topic_id', '').strip().replace('--', '-')
    cfg.update({
        'bot_token': request.form.get('bot_token', '').strip(),
        'admin_group_id': int(admin_group_id) if admin_group_id else 0,
        'main_group_id': int(main_group_id) if main_group_id else 0,
        'admin_log_topic_id': int(admin_log_topic_id) if admin_log_topic_id else 0,
        'delete_commands': 'delete_commands' in request.form,
        'bot_message_cleanup_seconds': int(request.form.get('bot_message_cleanup_seconds') or 0),
        'message_logging_enabled': 'message_logging_enabled' in request.form,
        'message_logging_ignore_commands': 'message_logging_ignore_commands' in request.form,
        'message_logging_groups_only': 'message_logging_groups_only' in request.form,
        'max_warnings': int(request.form.get('max_warnings') or 3),
        'punishment_type': request.form.get('punishment_type', 'none'),
        'mute_duration': int(request.form.get('mute_duration') or 24),
        'cleanup_notification_seconds': int(request.form.get('cleanup_notification_seconds') or 60),
        'warning_bot_name': request.form.get('warning_bot_name', 'id_finder')
    })
    s.config_json = json.dumps(cfg)
    db.session.commit()
    flash('Einstellungen gespeichert.', 'success')
    return redirect(url_for('dashboard.id_finder_dashboard'))

@bp.route('/id-finder/user/<int:user_id>')
@login_required
def id_finder_user_detail(user_id):
    u = IDFinderUser.query.filter_by(telegram_id=user_id).first_or_404()
    ms = IDFinderMessage.query.filter_by(telegram_user_id=user_id).order_by(IDFinderMessage.timestamp.desc()).limit(100).all()
    
    topic_ids = list(set([m.message_thread_id for m in ms if m.message_thread_id]))
    topic_map = {}
    if topic_ids:
        mappings = TopicMapping.query.filter(TopicMapping.topic_id.in_(topic_ids)).all()
        topic_map = {m.topic_id: m.topic_name for m in mappings}
        
    return render_template('id_finder_user_detail.html', user=u, messages=ms, topic_map=topic_map)

@bp.route('/id-finder/delete-user/<int:user_id>', methods=['POST'])
@login_required
def id_finder_delete_user(user_id):
    u = IDFinderUser.query.filter_by(telegram_id=user_id).first()
    if u: db.session.delete(u); db.session.commit()
    return redirect(url_for('dashboard.id_finder_dashboard'))

@bp.route('/id-finder/commands')
@login_required
def id_finder_commands(): return render_template('id_finder_commands.html')

@bp.route('/id-finder/admin-panel')
@login_required
def id_finder_admin_panel():
    ads = IDFinderAdmin.query.all()
    admins_dict = {str(a.telegram_id): {'name': a.name, 'permissions': a.permissions} for a in ads}
    
    return render_template('id_finder_admin_panel.html', 
                          admins=admins_dict, 
                          available_permission_groups=AVAILABLE_PERMISSIONS, 
                          available_permissions={})

@bp.route('/id-finder/admin-panel/add', methods=['POST'])
@login_required
def id_finder_add_admin():
    admin_id = request.form.get('admin_id')
    admin_name = request.form.get('admin_name')
    if admin_id and admin_name:
        existing = IDFinderAdmin.query.filter_by(telegram_id=int(admin_id)).first()
        if not existing:
            new_admin = IDFinderAdmin(telegram_id=int(admin_id), name=admin_name, permissions={})
            db.session.add(new_admin)
            db.session.commit()
            flash('Admin erfolgreich hinzugefügt.', 'success')
        else:
            flash('Admin existiert bereits.', 'warning')
    return redirect(url_for('dashboard.id_finder_admin_panel'))

@bp.route('/id-finder/admin-panel/delete', methods=['POST'])
@login_required
def id_finder_delete_admin():
    admin_id = request.form.get('admin_id')
    if admin_id:
        admin = IDFinderAdmin.query.filter_by(telegram_id=int(admin_id)).first()
        if admin:
            db.session.delete(admin)
            db.session.commit()
            flash('Admin erfolgreich gelöscht.', 'success')
    return redirect(url_for('dashboard.id_finder_admin_panel'))

@bp.route('/id-finder/admin-panel/update-permissions', methods=['POST'])
@login_required
def id_finder_update_admin_permissions():
    admin_id = request.form.get('admin_id')
    if admin_id:
        admin = IDFinderAdmin.query.filter_by(telegram_id=int(admin_id)).first()
        if admin:
            # All form fields except admin_id are considered permissions
            perms = {k: True for k in request.form.keys() if k != 'admin_id'}
            admin.permissions = perms
            db.session.commit()
            flash('Berechtigungen erfolgreich aktualisiert.', 'success')
    return redirect(url_for('dashboard.id_finder_admin_panel'))

@bp.route('/id-finder/analytics')
@login_required
def id_finder_analytics():
    sys.stdout.write("--- [DEBUG] Entered id_finder_analytics ---\n")
    sys.stdout.flush()
    try:
        try:
            days = int(request.args.get('days') or 7)
        except ValueError:
            days = 7

        try:
            month = int(request.args.get('month') or 0)
            year = int(request.args.get('year') or 0)
        except ValueError:
            month = 0
            year = 0

        query_filter = true()
        
        # Handle time filtering
        now = datetime.utcnow()
        if year > 0 and month > 0:
            query_filter = (extract('year', IDFinderMessage.timestamp) == year) & (extract('month', IDFinderMessage.timestamp) == month)
        elif year > 0:
            query_filter = extract('year', IDFinderMessage.timestamp) == year
        elif days > 0:
            cutoff = now - timedelta(days=days)
            query_filter = IDFinderMessage.timestamp >= cutoff

        sys.stdout.write(f"--- [DEBUG] Filter set. Days={days}, Month={month}, Year={year} ---\n")
        sys.stdout.flush()

        total_users = IDFinderUser.query.count()

        # Leaderboard
        leaderboard_query = db.session.query(
            IDFinderUser.telegram_id,
            IDFinderUser.first_name,
            func.count(IDFinderMessage.id).label('msg_count'),
            func.sum(case((IDFinderMessage.content_type != 'text', 1), else_=0)).label('media_count')
        ).join(IDFinderMessage, IDFinderUser.telegram_id == IDFinderMessage.telegram_user_id) \
         .filter(query_filter) \
         .group_by(IDFinderUser.telegram_id, IDFinderUser.first_name) \
         .order_by(text('msg_count DESC')).limit(100).all()

        leaderboard = [
            {"uid": str(row.telegram_id), "name": row.first_name or "Unknown", "msgs": int(row.msg_count), "media": int(row.media_count or 0)}
            for row in leaderboard_query
        ]
        
        sys.stdout.write(f"--- [DEBUG] Leaderboard ready: {len(leaderboard)} entries ---\n")
        sys.stdout.flush()

        # Timeline (Messages per day)
        timeline_query = db.session.query(
            func.date(IDFinderMessage.timestamp).label('date'),
            func.count(IDFinderMessage.id).label('count')
        ).filter(query_filter).group_by('date').order_by('date').all()

        # Make sure timeline has continuous dates for the requested period if filtering by days
        timeline_labels = []
        total_data = []
        
        if days > 0 and year == 0 and month == 0:
            date_map = {fmt_dt(row.date): row.count for row in timeline_query if row.date}
            for i in range(days-1, -1, -1):
                d = now - timedelta(days=i)
                d_str = d.strftime('%d.%m')
                timeline_labels.append(d_str)
                total_data.append(date_map.get(d_str, 0))
        else:
            # For month/year filtering, rely on the data returned directly
            timeline_labels = [fmt_dt(row.date) for row in timeline_query]
            total_data = [row.count for row in timeline_query]

        # Hours distribution
        hours_query = db.session.query(
            extract('hour', IDFinderMessage.timestamp).label('hour'),
            func.count(IDFinderMessage.id).label('count')
        ).filter(query_filter).group_by('hour').all()
        
        busiest_hours = [0] * 24
        for row in hours_query:
            if row.hour is not None:
                busiest_hours[int(row.hour)] = row.count

        # Weekdays distribution
        engine_name = db.engine.dialect.name
        if engine_name == 'mysql':
            dow_expr = func.dayofweek(IDFinderMessage.timestamp)
        else:
            dow_expr = extract('dow', IDFinderMessage.timestamp)

        dow_query = db.session.query(
            dow_expr.label('dow'),
            func.count(IDFinderMessage.id).label('count')
        ).filter(query_filter).group_by('dow').all()

        busiest_days = [0] * 7
        for row in dow_query:
            if row.dow is not None:
                try:
                    val = int(row.dow)
                    if engine_name == 'mysql':
                        py_dow = (val + 5) % 7
                    else:
                        py_dow = (val + 6) % 7
                    busiest_days[py_dow] = row.count
                except: pass

        sys.stdout.write("--- [DEBUG] Everything ready. Rendering template. ---\n")
        sys.stdout.flush()

        return render_template('id_finder_analytics.html', 
                               stats={'total_users': total_users}, 
                               activity={
                                   'timeline': {'labels': timeline_labels, 'total': total_data}, 
                                   'leaderboard': leaderboard, 
                                   'busiest_hours': busiest_hours, 
                                   'busiest_days': busiest_days
                               })
    except Exception as e:
        # LOG AND CRASH gracefully
        err_msg = f"\n--- Analytics Error [{datetime.now()}] ---\n{traceback.format_exc()}\n"
        sys.stderr.write(err_msg)
        error_file = os.path.join(PROJECT_ROOT, "logs", "dashboard_error.log")
        try:
            os.makedirs(os.path.dirname(error_file), exist_ok=True)
            with open(error_file, "a", encoding="utf-8") as f:
                f.write(err_msg)
        except: pass
        raise e

@bp.route('/api/id-finder/user-activity/<int:uid>')
def id_finder_user_activity(uid):
    try:
        try:
            days = int(request.args.get('days') or 7)
        except ValueError:
            days = 7

        now = datetime.utcnow()
        cutoff = now - timedelta(days=days)
        
        timeline_query = db.session.query(
            func.date(IDFinderMessage.timestamp).label('date'),
            func.count(IDFinderMessage.id).label('count')
        ).filter(IDFinderMessage.telegram_user_id == uid, IDFinderMessage.timestamp >= cutoff) \
         .group_by('date').order_by('date').all()

        date_map = {fmt_dt(row.date): row.count for row in timeline_query if row.date}
        
        total_data = []
        for i in range(days-1, -1, -1):
            d_str = (now - timedelta(days=i)).strftime('%d.%m')
            total_data.append(date_map.get(d_str, 0))

        return jsonify({"timeline": total_data})
    except Exception as e:
        err_msg = f"\n--- User Activity Error [{datetime.now()}] ---\n{traceback.format_exc()}\n"
        sys.stderr.write(err_msg)
        error_file = os.path.join(PROJECT_ROOT, "logs", "dashboard_error.log")
        try:
            os.makedirs(os.path.dirname(error_file), exist_ok=True)
            with open(error_file, "a", encoding="utf-8") as f:
                f.write(err_msg)
        except: pass
        raise e

# --- USER MANAGEMENT ---
@bp.route('/users')
@login_required
def manage_users():
    us = User.query.all(); ud = {u.username: {'role': u.role} for u in us}
    return render_template('manage_users.html', users=ud)

@bp.route('/users/add', methods=['POST'])
@login_required
def add_user():
    u, p, r = request.form.get('username'), request.form.get('password'), request.form.get('role', 'user')
    if not u or not p:
        flash('Benutzername und Passwort sind erforderlich.', 'danger')
        return redirect(url_for('dashboard.manage_users'))
        
    if User.query.filter_by(username=u).first():
        flash(f'Benutzername "{u}" existiert bereits.', 'danger')
        return redirect(url_for('dashboard.manage_users'))
        
    try:
        nu = User(username=u, role=r); nu.set_password(p); db.session.add(nu); db.session.commit()
        flash(f'Benutzer "{u}" wurde angelegt.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler beim Anlegen des Benutzers: {e}', 'danger')
        
    return redirect(url_for('dashboard.manage_users'))

@bp.route('/users/delete/<username>', methods=['POST'])
@login_required
def delete_user(username):
    if username == current_user.username:
        flash('Du kannst dich nicht selbst löschen.', 'danger')
        return redirect(url_for('dashboard.manage_users'))
        
    u = User.query.filter_by(username=username).first()
    if not u:
        flash('Benutzer nicht gefunden.', 'danger')
        return redirect(url_for('dashboard.manage_users'))
        
    try:
        db.session.delete(u)
        db.session.commit()
        flash(f'Benutzer "{username}" wurde gelöscht.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler beim Löschen des Benutzers: {e}', 'danger')
        
    return redirect(url_for('dashboard.manage_users'))

@bp.route('/users/edit/<username>', methods=['POST'])
@login_required
def edit_user(username):
    u = User.query.filter_by(username=username).first()
    if not u:
        flash('Benutzer nicht gefunden.', 'danger')
        return redirect(url_for('dashboard.manage_users'))
        
    nu, np, nr = request.form.get('new_username'), request.form.get('new_password'), request.form.get('new_role')
    
    if nu and nu != username:
        if User.query.filter_by(username=nu).first():
            flash(f'Benutzername "{nu}" wird bereits verwendet.', 'danger')
            return redirect(url_for('dashboard.manage_users'))
        u.username = nu
        
    if np: u.set_password(np)
    if nr: u.role = nr
    
    try:
        db.session.commit()
        flash(f'Benutzer "{username}" wurde aktualisiert.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Interner Fehler: {e}', 'danger')
        
    return redirect(url_for('dashboard.manage_users'))

# --- MINECRAFT ---
@bp.route('/minecraft', methods=['GET', 'POST'])
@login_required
def minecraft_status_page():
    s = BotSettings.query.filter_by(bot_name='minecraft').first()
    if not s:
        cfg = {
            "mc_host": "127.0.0.1", "mc_port": 25565, "display_host": "", "display_port": None,
            "chat_id": "", "topic_id": None, "update_seconds": 30, "delete_player_seconds": 8
        }
        s = BotSettings(bot_name='minecraft', config_json=json.dumps(cfg))
        db.session.add(s); db.session.commit()
    
    cfg = json.loads(s.config_json)
    
    if request.method == 'POST':
        # Update settings from form
        cfg['mc_host'] = request.form.get('mc_host', '127.0.0.1')
        cfg['mc_port'] = int(request.form.get('mc_port', 25565))
        cfg['display_host'] = request.form.get('display_host', '')
        cfg['display_port'] = int(request.form.get('display_port', 25565))
        cfg['chat_id'] = request.form.get('chat_id', '')
        cfg['topic_id'] = request.form.get('topic_id') or None
        cfg['update_seconds'] = int(request.form.get('update_seconds', 30))
        cfg['delete_player_seconds'] = int(request.form.get('delete_player_seconds', 8))
        
        s.config_json = json.dumps(cfg)
        db.session.commit()
        flash('Minecraft-Einstellungen gespeichert.', 'success')
        return redirect(url_for('dashboard.minecraft_status_page'))

    # Load Status Cache
    cache_path = os.path.join(PROJECT_ROOT, "bots", "data", "minecraft_status_cache.json")
    status = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                status = json.load(f)
        except: pass

    return render_template('minecraft_status.html', 
                          cfg=cfg, 
                          status=status, 
                          latency_ms=status.get('ping_ms'),
                          motd=status.get('motd'),
                          players_text=status.get('players'),
                          error=status.get('error'))

# --- TIKTOK BOT ---
@bp.route('/tiktok-settings', methods=['GET', 'POST'])
@login_required
def tiktok_settings():
    s = BotSettings.query.filter_by(bot_name='tiktok').first()
    if not s:
        cfg = {
            'target_unique_ids': [], 'watch_hosts': [], 'telegram_chat_id': '', 'telegram_topic_id': '',
            'retry_offline_seconds': 60, 'alert_cooldown_seconds': 1800, 'max_concurrent_lives': 3,
            'is_active': False, 'message_template_self': "🔴 {target} ist LIVE!", 'message_template_presence': "👀 {target} bei @{host}!"
        }
        s = BotSettings(bot_name='tiktok', config_json=json.dumps(cfg)); db.session.add(s); db.session.commit()
    
    cfg = json.loads(s.config_json)
    if request.method == 'POST':
        cfg.update({
            'telegram_chat_id': request.form.get('telegram_chat_id'),
            'telegram_topic_id': request.form.get('telegram_topic_id'),
            'target_unique_ids': [t.strip().lstrip('@') for t in request.form.getlist('target_unique_ids') if t.strip()],
            'watch_hosts': [h.strip().lstrip('@') for h in request.form.get('watch_hosts', '').split(',') if h.strip()],
            'message_template_self': request.form.get('message_template_self'),
            'message_template_presence': request.form.get('message_template_presence'),
            'alert_cooldown_seconds': int(request.form.get('alert_cooldown_seconds', 1800)),
            'max_concurrent_lives': int(request.form.get('max_concurrent_lives', 3))
        })
        s.is_active = cfg.get('is_active', False)
        s.config_json = json.dumps(cfg); db.session.commit(); flash('TikTok-Einstellungen gespeichert.', 'success'); return redirect(url_for('dashboard.tiktok_settings'))

    logs = []
    if os.path.exists(TIKTOK_BOT_LOG_FILE):
        with open(TIKTOK_BOT_LOG_FILE, 'r') as f: logs = f.readlines()[-100:]
    
    ids = BotSettings.query.filter_by(bot_name='id_finder').first()
    cfg['api_token_display'] = json.loads(ids.config_json).get('bot_token', 'Nicht gesetzt') if ids and ids.config_json else 'Nicht gesetzt'
    return render_template('tiktok_settings.html', config=cfg, logs=logs)

@bp.route('/tiktok/clear-logs', methods=['POST'])
@login_required
def tiktok_clear_logs():
    if not safe_clear_log(TIKTOK_BOT_LOG_FILE):
        flash('Logs konnten nicht gelöscht werden (File In Use).', 'warning')
    else:
        flash('Logs erfolgreich gelöscht.', 'success')
    return redirect(url_for('dashboard.tiktok_settings'))

# --- BOT ACTIONS ---
@bp.route('/bot-action/<bot_name>/<action>', methods=['POST'])
@login_required
def bot_action_route(bot_name, action):
    # Master-Bot (ID-Finder) hat als einziges noch echte Prozess-Steuerung
    if bot_name == 'id_finder':
        return master_bot_action(action)

    # Alle anderen Bots (Module) toggeln nur noch ihr "is_active" Flag in der DB
    s = BotSettings.query.filter_by(bot_name=bot_name).first()
    
    # Auto-create if not exists (e.g. for new modules like auto_responder)
    if not s:
        s = BotSettings(bot_name=bot_name, config_json=json.dumps({"is_active": False}), is_active=False)
        db.session.add(s)
        db.session.commit()

    try:
        c = json.loads(s.config_json) if s.config_json else {}
        if action == 'start':
            c['is_active'] = True
            s.is_active = True
            flash(f'{bot_name.capitalize()} Modul aktiviert.', 'success')
        elif action == 'stop':
            c['is_active'] = False
            s.is_active = False
            flash(f'{bot_name.capitalize()} Modul deaktiviert.', 'warning')
        
        s.config_json = json.dumps(c)
        db.session.commit()
    except Exception as e:
        flash(f'Fehler beim Ändern des Modul-Status: {e}', 'danger')
        
    return redirect(request.referrer or url_for('dashboard.index'))

def manage_master_bot_logic(action, is_auto_start=False):
    """
    Kapselt die Logik zum Starten/Stoppen des Master-Bots.
    Kann sowohl aus einer Web-Route als auch beim App-Start (Auto-Start) aufgerufen werden.
    """
    pfile = os.path.join(PROJECT_ROOT, "logs", "main_bot.pid")
    script = os.path.join(PROJECT_ROOT, "bots", "main_bot.py")
    lpath = os.path.join(PROJECT_ROOT, "logs", "main_bot.log")

    def _flash(msg, cat):
        if not is_auto_start:
            try: flash(msg, cat)
            except: pass

    if action == 'start':
        if os.path.exists(pfile):
            try:
                with open(pfile, 'r') as f: pid = int(f.read().strip())
                if is_process_running(pid):
                    print(f"Master-Bot läuft bereits (PID: {pid}). Kein Neustart erforderlich.")
                    _flash('Master-Bot läuft bereits.', 'info')
                    return
            except Exception as e:
                print(f"Fehler beim Prüfen der PID-Datei: {e}")
        
        # Falls Datei existiert aber Prozess NICHT läuft -> Datei löschen für sauberen Start
        if os.path.exists(pfile):
            try: os.remove(pfile)
            except: pass
        
        exe = sys.executable
        venv_win = os.path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe")
        venv_lin = os.path.join(PROJECT_ROOT, ".venv", "bin", "python")
        if os.path.exists(venv_win): exe = venv_win
        elif os.path.exists(venv_lin): exe = venv_lin

        os.makedirs(os.path.dirname(lpath), exist_ok=True)
        
        from dotenv import load_dotenv as load_env_file
        load_env_file(os.path.join(PROJECT_ROOT, '.env'))
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["BOT_PROCESS"] = "1"  # Markierung für Unterprozesse
        
        creationflags = 0
        if os.name == 'nt': creationflags = 0x00000008
            
        with open(lpath, 'a', encoding='utf-8') as lf: 
            proc = subprocess.Popen([exe, script], start_new_session=(os.name != 'nt'), creationflags=creationflags, stdout=lf, stderr=lf, env=env)
        
        with open(pfile, 'w') as f: f.write(str(proc.pid))
        _flash('Master-Bot gestartet.', 'success')
        print(f"Master-Bot gestartet (PID: {proc.pid})")
        
    elif action == 'stop' and os.path.exists(pfile):
        try:
            with open(pfile, 'r') as f: pid = int(f.read().strip())
            if os.name == 'nt':
                # Force kill process tree to avoid ghost processes
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                # Also kill any leftover main_bot.py processes just in case
                subprocess.run(['taskkill', '/F', '/IM', 'python.exe', '/FI', 'WINDOWTITLE eq Bot-Master*'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                os.kill(pid, signal.SIGTERM)
            if os.path.exists(pfile): os.remove(pfile)
            _flash('Master-Bot gestoppt.', 'success')
        except Exception as e:
            print(f"Fehler beim Stoppen vom Master Bot: {e}")
            _flash('Fehler beim Stoppen des Master-Bots.', 'danger')

def master_bot_action(action):
    manage_master_bot_logic(action)
    return redirect(request.referrer or url_for('dashboard.index'))

@bp.route('/api/bot-status')
@login_required
def bot_status_api(): return jsonify(get_bot_status_simple())

# --- PROFANITY FILTER ---
@bp.route('/profanity-filter')
@login_required
def profanity_filter():
    from ..models import ProfanityWord
    words = ProfanityWord.query.order_by(ProfanityWord.word).all()
    s = BotSettings.query.filter_by(bot_name='profanity_filter').first()
    is_running = False
    if s and s.config_json:
        try:
            cfg = json.loads(s.config_json)
            is_running = cfg.get('is_active', False)
        except:
            pass
    return render_template('profanity_filter.html', words=words, is_running=is_running)

@bp.route('/profanity-filter/add', methods=['POST'])
@login_required
def profanity_filter_add():
    from ..models import ProfanityWord
    
    # Check if this is a bulk import from the new textarea
    bulk_words = request.form.get('words_bulk', '')
    if not bulk_words:
        # Fallback to single word input if used
        bulk_words = request.form.get('word', '')
        
    if bulk_words:
        import re
        # Split by commas or newlines
        words_list = re.split(r'[,\n\r]+', bulk_words)
        
        added_count = 0
        skipped_count = 0
        
        for w in words_list:
            clean_word = w.strip().lower()
            if not clean_word:
                continue
                
            if len(clean_word) > 100:
                skipped_count += 1
                continue
                
            exists = ProfanityWord.query.filter_by(word=clean_word).first()
            if not exists:
                db.session.add(ProfanityWord(word=clean_word))
                added_count += 1
            else:
                skipped_count += 1
                
        if added_count > 0:
            db.session.commit()
            flash(f'{added_count} neue(s) Wort/Wörter erfolgreich hinzugefügt.', 'success')
            if skipped_count > 0:
                flash(f'{skipped_count} Wort/Wörter wurden übersprungen (bereits vorhanden oder zu lang).', 'warning')
        elif skipped_count > 0:
            flash(f'Alle eingegebenen Wörter existieren bereits oder sind zu lang.', 'warning')
        else:
            flash('Keine gültigen Wörter gefunden.', 'warning')
            
    return redirect(url_for('dashboard.profanity_filter'))

@bp.route('/profanity-filter/delete/<int:word_id>', methods=['POST'])
@login_required
def profanity_filter_delete(word_id):
    from ..models import ProfanityWord
    w = ProfanityWord.query.get(word_id)
    if w:
        db.session.delete(w)
        db.session.commit()
        flash('Wort gelöscht.', 'info')
    return redirect(url_for('dashboard.profanity_filter'))

@bp.route('/profanity-filter/import-google', methods=['POST'])
@login_required
def profanity_filter_import_google():
    from ..models import ProfanityWord
    import urllib.request
    try:
        url = "https://raw.githubusercontent.com/LDNOOBW/List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words/master/de"
        response = urllib.request.urlopen(url)
        content = response.read().decode('utf-8')
        lines = content.splitlines()
        
        added = 0
        for line in lines:
            w = line.strip().lower()
            if w and len(w) <= 100:
                if not ProfanityWord.query.filter_by(word=w).first():
                    db.session.add(ProfanityWord(word=w, language='de'))
                    added += 1
        db.session.commit()
        flash(f'{added} neue Wörter aus der Google-Liste importiert.', 'success')
    except Exception as e:
        flash(f'Fehler beim Importieren: {e}', 'danger')
        
    return redirect(url_for('dashboard.profanity_filter'))

# --- BIRTHDAY BOT ---
@bp.route('/birthday-settings', methods=['GET', 'POST'])
@login_required
def birthday_settings():
    from ..models import Birthday, BotSettings, IDFinderUser
    
    s = BotSettings.query.filter_by(bot_name='birthday').first()
    if not s:
        cfg = {
            'registration_text': 'Dein Geburtstag ({day}.{month}.) wurde erfolgreich eingetragen!',
            'congratulation_text': 'Herzlichen Glückwunsch zum Geburtstag, {user}!',
            'prompt_text': '🎂 <b>Geburtstags-Bot</b>\n\nWann hast du Geburtstag?\nBitte schreibe es im Format <code>Tag.Monat</code> oder <code>Tag.Monat.Jahr</code>.\n<i>(Beispiel: 15.08. oder 15.08.1990 - das Jahr ist komplett freiwillig!)</i>\n\nWenn du abbrechen möchtest, tippe /cancel.',
            'error_format_text': 'Das war leider das falsche Format.\nBeispiele: `15.08.` oder `15 08 1990`\nVersuche es nochmal oder tippe /cancel.',
            'error_date_text': 'Das ist leider kein echtes Kalenderdatum. Bitte versuche es noch einmal:',
            'cancel_text': 'Geburtstags-Eintragung abgebrochen.',
            'announce_time': '00:01',
            'target_chat_id': '',
            'target_topic_id': '',
            'auto_delete_registration': False
        }
        s = BotSettings(bot_name='birthday', config_json=json.dumps(cfg))
        db.session.add(s)
        db.session.commit()
        
    cfg = json.loads(s.config_json)
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'update_settings':
            cfg['registration_text'] = request.form.get('registration_text')
            cfg['congratulation_text'] = request.form.get('congratulation_text')
            cfg['prompt_text'] = request.form.get('prompt_text')
            cfg['error_format_text'] = request.form.get('error_format_text')
            cfg['error_date_text'] = request.form.get('error_date_text')
            cfg['cancel_text'] = request.form.get('cancel_text')
            cfg['announce_time'] = request.form.get('announce_time')
            cfg['target_chat_id'] = request.form.get('target_chat_id', '').strip()
            cfg['target_topic_id'] = request.form.get('target_topic_id', '').strip()
            cfg['auto_delete_registration'] = request.form.get('auto_delete_registration') == 'on'
            s.config_json = json.dumps(cfg)
            db.session.commit()
            flash('Geburtstags-Einstellungen gespeichert.', 'success')
            
        elif action == 'add_birthday':
            uid = request.form.get('telegram_user_id')
            day = request.form.get('day')
            month = request.form.get('month')
            year = request.form.get('year')
            if uid and day and month:
                existing = Birthday.query.filter_by(telegram_user_id=int(uid)).first()
                if not existing:
                    u = IDFinderUser.query.filter_by(telegram_id=int(uid)).first()
                    name = u.first_name if u else "Unbekannt"
                    username = u.username if u else ""
                    b = Birthday(telegram_user_id=int(uid), day=int(day), month=int(month), year=int(year) if year else None, first_name=name, username=username)
                    db.session.add(b)
                    db.session.commit()
                    flash('Geburtstag hinzugefügt.', 'success')
                else:
                    flash('User hat bereits einen Geburtstag eingetragen.', 'warning')
                    
        elif action == 'update_birthday':
            bid = request.form.get('birthday_id')
            day = request.form.get('day')
            month = request.form.get('month')
            year = request.form.get('year')
            if bid and day and month:
                b = Birthday.query.get(int(bid))
                if b:
                    b.day = int(day)
                    b.month = int(month)
                    b.year = int(year) if year else None
                    db.session.commit()
                    flash('Geburtstag aktualisiert.', 'success')
                    
        elif action == 'delete_birthday':
            bid = request.form.get('birthday_id')
            if bid:
                b = Birthday.query.get(int(bid))
                if b:
                    db.session.delete(b)
                    db.session.commit()
                    flash('Geburtstag gelöscht.', 'success')
                    
        return redirect(url_for('dashboard.birthday_settings'))
        
    birthdays = Birthday.query.order_by(Birthday.month, Birthday.day).all()
    
    # Load avatars
    user_avatars = {}
    for b in birthdays:
        u = IDFinderUser.query.filter_by(telegram_id=b.telegram_user_id).first()
        if u:
            user_avatars[b.telegram_user_id] = u
            
    return render_template('birthday.html', settings=cfg, birthdays=birthdays, user_avatars=user_avatars)

@bp.route('/api/backup/download')
@login_required
def download_backup():
    import os
    from flask import send_file, flash, redirect, url_for
    from flask_login import current_user
    
    if getattr(current_user, 'role', 'user') != 'admin':
        flash('Keine Berechtigung. Nur Administratoren können Backups herunterladen.', 'danger')
        return redirect(url_for('dashboard.index'))
        
    from shared_bot_utils import DB_PATH
    
    if os.path.exists(DB_PATH):
        return send_file(DB_PATH, as_attachment=True, download_name='app_backup.db')
    else:
        flash('Datenbank-Datei nicht gefunden. Nutzen Sie ggf. eine externe MariaDB?', 'danger')
        return redirect(url_for('dashboard.index'))

@bp.route('/api/backup/upload', methods=['POST'])
@login_required
def upload_backup():
    if getattr(current_user, 'role', 'user') != 'admin':
        return jsonify({"success": False, "error": "Keine Berechtigung."}), 403
        
    if 'backup_file' not in request.files:
        return jsonify({"success": False, "error": "Keine Datei hochgeladen."}), 400
        
    file = request.files['backup_file']
    if file.filename == '':
        return jsonify({"success": False, "error": "Keine Datei ausgewählt."}), 400
        
    if not file.filename.endswith('.db'):
        return jsonify({"success": False, "error": "Ungültiges Dateiformat. Nur .db Dateien erlaubt."}), 400
        
    from shared_bot_utils import DB_PATH
    
    try:
        # Erst in temporäre Datei speichern
        temp_path = DB_PATH + ".tmp"
        file.save(temp_path)
        
        # Einfache Validierung: Ist es eine SQLite Datei?
        with open(temp_path, 'rb') as f:
            header = f.read(16)
            if header != b'SQLite format 3\x00':
                os.remove(temp_path)
                return jsonify({"success": False, "error": "Die Datei ist keine gültige SQLite-Datenbank."}), 400
        
        # Backup der aktuellen DB erstellen (Sicherheitshalber)
        if os.path.exists(DB_PATH):
            import shutil
            shutil.copy2(DB_PATH, DB_PATH + ".bak")
            
        # Datenbank ersetzen
        import shutil
        shutil.move(temp_path, DB_PATH)
        
        # Server Neustart triggern (analog zu installer)
        import threading
        import time
        import signal
        
        def restart_server():
            time.sleep(2)
            print("Backup Restore Complete! Restarting server process...")
            os._exit(0)  # Cross-platform restart (devserver.ps1 will auto-restart)
            
        threading.Thread(target=restart_server, daemon=True).start()
        
        return jsonify({"success": True, "message": "Backup erfolgreich wiederhergestellt. Server startet neu..."})
        
    except Exception as e:
        logger.error(f"Error restoring backup: {e}")

@bp.route('/api/event/create', methods=['POST'])
@login_required
def create_event_api():
    title = request.form.get('title')
    description = request.form.get('description')
    chat_id = request.form.get('chat_id')
    should_pin = request.form.get('pin') == 'true'
    image = request.files.get('image')
    
    if not title or not chat_id:
        return jsonify({"success": False, "error": "Titel und Chat-ID sind erforderlich."}), 400
        
    image_path = None
    if image:
        # Simple upload logic (target: static/uploads/events)
        target_dir = os.path.join('web_dashboard', 'app', 'static', 'uploads', 'events')
        os.makedirs(target_dir, exist_ok=True)
        filename = f"{int(time.time())}_{image.filename}"
        image.save(os.path.join(target_dir, filename))
        image_path = f"/static/uploads/events/{filename}"
        
    try:
        from ..models import GroupEvent
        new_event = GroupEvent(
            title=title,
            description=description,
            chat_id=int(chat_id),
            should_pin=should_pin,
            image_path=image_path
        )
        db.session.add(new_event)
        db.session.commit()
        
        # Trigger Bot to post event (Async via background thread)
        from shared_bot_utils import get_bot_token
        token = get_bot_token()
        
        if token:
            async def post_event_task():
                try:
                    from telegram import Bot
                    from telegram.constants import ParseMode
                    from bots.event_bot.event_bot import get_event_markup
                    
                    bot = Bot(token)
                    
                    # Format
                    text = f"📅 **{title}**\n\n{description}\n\n✅ 0 | 🤔 0 | ❌ 0"
                    markup = get_event_markup(new_event.id, {})
                    
                    if image_path:
                        # Full absolute path for bot
                        full_img_path = os.path.abspath(os.path.join(PROJECT_ROOT, 'web_dashboard', 'app', image_path.lstrip('/')))
                        with open(full_img_path, 'rb') as f:
                            posted_msg = await bot.send_photo(
                                chat_id=int(chat_id),
                                photo=f,
                                caption=text,
                                parse_mode=ParseMode.MARKDOWN,
                                reply_markup=markup
                            )
                    else:
                        posted_msg = await bot.send_message(
                            chat_id=int(chat_id),
                            text=text,
                            parse_mode=ParseMode.MARKDOWN,
                            reply_markup=markup
                        )
                        
                    if should_pin:
                        await bot.pin_chat_message(chat_id=int(chat_id), message_id=posted_msg.message_id)
                        
                    # Save message_id for later updates
                    # We need a new session or use the shared flask_app context
                    from shared_bot_utils import get_shared_flask_app
                    f_app = get_shared_flask_app()
                    with f_app.app_context():
                        from web_dashboard.app.models import db as db_ctx, GroupEvent as GE
                        ev = db_ctx.session.get(GE, new_event.id)
                        if ev:
                            ev.message_id = posted_msg.message_id
                            db_ctx.session.commit()
                            
                except Exception as e:
                    logger.error(f"Error posting event to Telegram: {e}")

            def run_async_background(coro):
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(coro)
                loop.close()

            import threading
            threading.Thread(target=run_async_background, args=(post_event_task(),), daemon=True).start()

        return jsonify({"success": True, "message": "Event wurde erstellt und wird im Hintergrund gepostet."})
        
    except Exception as e:
        if 'logger' in globals() or 'logger' in locals():
            logger.error(f"Error creating event: {e}")
        else:
            print(f"Error creating event: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# --- BOT API ROUTES ---
@bp.route('/api/bot/save-config', methods=['POST'])
@login_required
def save_bot_config_api():
    data = request.json
    bot_name = data.get('bot_name')
    config_update = data.get('config')
    
    if not bot_name or config_update is None:
        return jsonify({"success": False, "error": "Missing data"}), 400
        
    s = BotSettings.query.filter_by(bot_name=bot_name).first()
    if not s:
        s = BotSettings(bot_name=bot_name, config_json=json.dumps(config_update))
        db.session.add(s)
    else:
        try:
            current_cfg = json.loads(s.config_json)
        except:
            current_cfg = {}
        current_cfg.update(config_update)
        s.config_json = json.dumps(current_cfg)
        
    db.session.commit()
    return jsonify({"success": True})

@bp.route('/api/bot/stats/<bot_name>', methods=['GET'])
@login_required
def get_bot_stats(bot_name):
    if bot_name == 'report_bot':
        try:
            from ..models import ReportedMessage
            count = ReportedMessage.query.count()
            return jsonify({"success": True, "count": count})
        except:
            return jsonify({"success": False, "error": "Table not found"}), 404
            
    elif bot_name == 'event_bot':
        try:
            from ..models import GroupEvent
            count = GroupEvent.query.count()
            return jsonify({"success": True, "count": count})
        except:
            return jsonify({"success": False, "error": "Table not found"}), 404
            
    return jsonify({"success": False, "error": "Unknown bot"}), 400

@bp.route('/api/bot/toggle', methods=['POST'])
@login_required
def toggle_bot_api():
    data = request.json
    bot_name = data.get('bot_name')
    active = data.get('active', False)
    
    s = BotSettings.query.filter_by(bot_name=bot_name).first()
    if not s:
        cfg = {"is_active": active}
        s = BotSettings(bot_name=bot_name, config_json=json.dumps(cfg))
        db.session.add(s)
    else:
        try:
            cfg = json.loads(s.config_json)
        except:
            cfg = {}
        cfg['is_active'] = active
        s.config_json = json.dumps(cfg)
        
    db.session.commit()
    return jsonify({"success": True})

# --- REPORT BOT SETTINGS ---

@bp.route('/report-settings', methods=['GET', 'POST'])
@login_required
def report_settings():
    from ..models import ReportedMessage
    config_setting = BotSettings.query.filter_by(bot_name='report_bot').first()
    config = json.loads(config_setting.config_json) if config_setting and config_setting.config_json else {}
    
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'save_config':
            new_config = {
                "target_chat_id": request.form.get('target_chat_id'),
                "target_topic_id": request.form.get('target_topic_id'),
                "is_active": config.get('is_active', False)
            }
            if not config_setting:
                config_setting = BotSettings(bot_name='report_bot')
                db.session.add(config_setting)
            config_setting.config_json = json.dumps(new_config)
            db.session.commit()
            flash('Konfiguration gespeichert!', 'success')
            return redirect(url_for('dashboard.report_settings'))
            
        elif action == 'clear_reports':
            ReportedMessage.query.delete()
            db.session.commit()
            flash('Alle Berichte wurden gelöscht.', 'info')
            return redirect(url_for('dashboard.report_settings'))

    reports = ReportedMessage.query.order_by(ReportedMessage.timestamp.desc()).all()
    return render_template('report_settings.html', config=config, reports=reports)

# --- EVENT PLANNER SETTINGS ---

@bp.route('/event-settings', methods=['GET', 'POST'])
@login_required
def event_settings():
    from ..models import GroupEvent
    config_setting = BotSettings.query.filter_by(bot_name='event_bot').first()
    config = json.loads(config_setting.config_json) if config_setting and config_setting.config_json else {}
    
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'delete_event':
            event_id = request.form.get('event_id')
            event = GroupEvent.query.get(event_id)
            if event:
                db.session.delete(event)
                db.session.commit()
                flash('Event wurde gelöscht.', 'info')
            return redirect(url_for('dashboard.event_settings'))

    events = GroupEvent.query.order_by(GroupEvent.created_at.desc()).all()
    return render_template('event_settings.html', config=config, events=events)
