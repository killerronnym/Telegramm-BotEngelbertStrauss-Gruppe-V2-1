from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, session
from flask_login import login_required, current_user
import os
import json
import subprocess
import sys
import signal
from datetime import datetime, timedelta
from sqlalchemy import func
from werkzeug.utils import secure_filename
from ..models import db, BotSettings, Broadcast, TopicMapping, User, IDFinderAdmin, IDFinderUser, IDFinderMessage, AVAILABLE_PERMISSIONS

# Wir definieren den Blueprint explizit
bp = Blueprint('dashboard', __name__)

# Pfade berechnen
CURRENT_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_FILE_DIR, '../../..'))
BASE_DIR = os.path.join(PROJECT_ROOT, 'web_dashboard')

# Bot PID Files
INVITE_BOT_PID_FILE = os.path.join(BASE_DIR, "invite_bot.pid")
ID_FINDER_BOT_PID_FILE = os.path.join(BASE_DIR, "id_finder_bot.pid")
TIKTOK_BOT_PID_FILE = os.path.join(BASE_DIR, "tiktok_bot.pid")
QUIZ_BOT_PID_FILE = os.path.join(BASE_DIR, "quiz_bot.pid")
UMFRAGE_BOT_PID_FILE = os.path.join(BASE_DIR, "umfrage_bot.pid")
OUTFIT_BOT_PID_FILE = os.path.join(BASE_DIR, "outfit_bot.pid")

# Log Files
INVITE_BOT_LOG_FILE = os.path.join(BASE_DIR, "invite_bot.log")
ID_FINDER_BOT_LOG_FILE = os.path.join(PROJECT_ROOT, "bots", "id_finder_bot", "id_finder_bot.log")
TIKTOK_BOT_LOG_FILE = os.path.join(PROJECT_ROOT, "bots", "tiktok_bot", "tiktok_bot.log")
QUIZ_BOT_LOG_FILE = os.path.join(PROJECT_ROOT, "bots", "quiz_bot", "quiz_bot.log")
UMFRAGE_BOT_LOG_FILE = os.path.join(PROJECT_ROOT, "bots", "umfrage_bot", "umfrage_bot.log")
OUTFIT_BOT_LOG_FILE = os.path.join(PROJECT_ROOT, "bots", "outfit_bot", "outfit_bot.log")

def is_process_running(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

def safe_clear_log(filepath):
    if not os.path.exists(filepath): return True
    try:
        os.remove(filepath)
        return True
    except Exception as e:
        print(f"Error clearing log {filepath}: {e}")
        return False

def get_master_pid():
    pfile = os.path.join(PROJECT_ROOT, "bots", "main_bot.pid")
    if os.path.exists(pfile):
        try:
            with open(pfile, 'r') as f: return int(f.read().strip())
        except: return None
    return None

def get_bot_status_simple():
    status = {
        "invite": {"running": False}, "quiz": {"running": False}, 
        "umfrage": {"running": False}, "outfit": {"running": False}, 
        "id_finder": {"running": False}, "tiktok": {"running": False}
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
            if s.bot_name in status and s.bot_name != 'id_finder':
                if s.config_json:
                    c = json.loads(s.config_json)
                    status[s.bot_name]["running"] = c.get('is_active', False)
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
    s.config_json = json.dumps(cfg); db.session.commit(); flash('Texte gespeichert.', 'success')
    return redirect(url_for('dashboard.bot_settings'))

@bp.route('/bot-settings/add-field', methods=['POST'])
@login_required
def add_field():
    s = BotSettings.query.filter_by(bot_name='invite').first()
    cfg = json.loads(s.config_json); fields = cfg.setdefault('form_fields', [])
    fields.append({'id': request.form.get('field_id'), 'emoji': request.form.get('emoji', '🔹'), 'display_name': request.form.get('display_name', ''), 'label': request.form.get('label', ''), 'type': request.form.get('type', 'text'), 'required': 'required' in request.form, 'enabled': True})
    s.config_json = json.dumps(cfg); db.session.commit(); return redirect(url_for('dashboard.bot_settings'))

@bp.route('/bot-settings/edit-field', methods=['POST'])
@login_required
def edit_field():
    s = BotSettings.query.filter_by(bot_name='invite').first()
    cfg = json.loads(s.config_json); fid = request.form.get('field_id')
    for f in cfg.get('form_fields', []):
        if f['id'] == fid: f.update({'emoji': request.form.get('emoji'), 'display_name': request.form.get('display_name'), 'label': request.form.get('label'), 'type': request.form.get('type'), 'required': 'required' in request.form, 'enabled': 'enabled' in request.form})
    s.config_json = json.dumps(cfg); db.session.commit(); return redirect(url_for('dashboard.bot_settings'))

@bp.route('/bot-settings/delete-field', methods=['POST'])
@login_required
def delete_field():
    s = BotSettings.query.filter_by(bot_name='invite').first()
    cfg = json.loads(s.config_json); fid = request.form.get('field_id')
    cfg['form_fields'] = [f for f in cfg.get('form_fields', []) if f['id'] != fid]
    s.config_json = json.dumps(cfg); db.session.commit(); return redirect(url_for('dashboard.bot_settings'))

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
                aq_path = os.path.join(PROJECT_ROOT, "bots", "quiz_bot", "quizfragen_gestellt.json")
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
    aq_path = os.path.join(PROJECT_ROOT, "bots", "quiz_bot", "quizfragen_gestellt.json")
    
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
    tfile = os.path.join(PROJECT_ROOT, "bots", "quiz_bot", "send_now.tmp")
    with open(tfile, 'w') as f: f.write('1')
    flash('Trigger gesendet. Der Bot wird die Frage in Kürze senden.', 'info')
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
                up_path = os.path.join(PROJECT_ROOT, "bots", "umfrage_bot", "umfragen_gestellt.json")
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
    up_path = os.path.join(PROJECT_ROOT, "bots", "umfrage_bot", "umfragen_gestellt.json")
    
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
    tfile = os.path.join(PROJECT_ROOT, "bots", "umfrage_bot", "send_now.tmp")
    with open(tfile, 'w') as f: f.write('1')
    flash('Trigger gesendet.', 'info')
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
    data_path = os.path.join(PROJECT_ROOT, "bots", "outfit_bot", "outfit_bot_data.json")
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
    lpath = os.path.join(BASE_DIR, "critical_errors.log")
    if os.path.exists(lpath):
        with open(lpath, 'r') as f: logs = f.readlines()
    return render_template("critical_errors.html", critical_logs=logs)

@bp.route('/critical-errors/clear', methods=['POST'])
@login_required
def clear_critical_errors():
    lpath = os.path.join(BASE_DIR, "critical_errors.log")
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
    admin_group_id = request.form.get('admin_group_id', '').strip()
    main_group_id = request.form.get('main_group_id', '').strip()
    admin_log_topic_id = request.form.get('admin_log_topic_id', '').strip()
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

    query_filter = True
    base_query = IDFinderMessage.query
    
    # Handle time filtering
    now = datetime.utcnow()
    if year > 0 and month > 0:
        query_filter = (db.extract('year', IDFinderMessage.timestamp) == year) & (db.extract('month', IDFinderMessage.timestamp) == month)
    elif year > 0:
        query_filter = db.extract('year', IDFinderMessage.timestamp) == year
    elif days > 0:
        cutoff = now - timedelta(days=days)
        query_filter = IDFinderMessage.timestamp >= cutoff

    total_users = IDFinderUser.query.count()

    # Leaderboard
    leaderboard_query = db.session.query(
        IDFinderUser.telegram_id,
        IDFinderUser.first_name,
        func.count(IDFinderMessage.id).label('msg_count'),
        func.sum(db.case((IDFinderMessage.content_type != 'text', 1), else_=0)).label('media_count')
    ).join(IDFinderMessage, IDFinderUser.telegram_id == IDFinderMessage.telegram_user_id) \
     .filter(query_filter) \
     .group_by(IDFinderUser.telegram_id, IDFinderUser.first_name) \
     .order_by(db.text('msg_count DESC')).limit(100).all()

    leaderboard = [
        {"uid": str(row.telegram_id), "name": row.first_name or "Unknown", "msgs": int(row.msg_count), "media": int(row.media_count or 0)}
        for row in leaderboard_query
    ]

    # Timeline (Messages per day)
    timeline_query = db.session.query(
        func.date(IDFinderMessage.timestamp).label('date'),
        func.count(IDFinderMessage.id).label('count')
    ).filter(query_filter).group_by('date').order_by('date').all()

    # Make sure timeline has continuous dates for the requested period if filtering by days
    timeline_labels = []
    total_data = []
    
    if days > 0 and year == 0 and month == 0:
        date_map = {row.date.strftime('%d.%m'): row.count for row in timeline_query if row.date}
        for i in range(days-1, -1, -1):
            d = now - timedelta(days=i)
            d_str = d.strftime('%d.%m')
            timeline_labels.append(d_str)
            total_data.append(date_map.get(d_str, 0))
    else:
        # For month/year filtering, rely on the data returned directly
        timeline_labels = [row.date.strftime('%d.%m') if row.date else 'Unknown' for row in timeline_query]
        total_data = [row.count for row in timeline_query]

    # Hours distribution
    # Using generic cast since extract('hour') is cross-compatible 
    hours_query = db.session.query(
        db.extract('hour', IDFinderMessage.timestamp).label('hour'),
        func.count(IDFinderMessage.id).label('count')
    ).filter(query_filter).group_by('hour').all()
    
    busiest_hours = [0] * 24
    for row in hours_query:
        if row.hour is not None:
            busiest_hours[int(row.hour)] = row.count

    # Weekdays distribution
    # Extract 'dow' is not supported in MySQL/MariaDB.
    engine_name = db.engine.dialect.name
    if engine_name == 'mysql':
        # MySQL/MariaDB: DAYOFWEEK returns 1 (Sun) to 7 (Sat)
        dow_expr = func.dayofweek(IDFinderMessage.timestamp)
    else:
        # SQLite: 0 (Sun) to 6 (Sat)
        dow_expr = db.extract('dow', IDFinderMessage.timestamp)

    dow_query = db.session.query(
        dow_expr.label('dow'),
        func.count(IDFinderMessage.id).label('count')
    ).filter(query_filter).group_by('dow').all()

    busiest_days = [0] * 7
    for row in dow_query:
        if row.dow is not None:
            if engine_name == 'mysql':
                # Shift MySQL 1-7 (Sun-Sat) to 0-6 (Mon-Sun)
                py_dow = (int(row.dow) + 5) % 7
            else:
                # Shift SQLite 0-6 (Sun-Sat) to 0-6 (Mon-Sun)
                py_dow = (int(row.dow) + 6) % 7
            busiest_days[py_dow] = row.count

    return render_template('id_finder_analytics.html', 
                           stats={'total_users': total_users}, 
                           activity={
                               'timeline': {'labels': timeline_labels, 'total': total_data}, 
                               'leaderboard': leaderboard, 
                               'busiest_hours': busiest_hours, 
                               'busiest_days': busiest_days
                           })

@bp.route('/api/id-finder/user-activity/<int:uid>')
def id_finder_user_activity(uid):
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

    date_map = {row.date.strftime('%d.%m'): row.count for row in timeline_query if row.date}
    
    total_data = []
    for i in range(days-1, -1, -1):
        d_str = (now - timedelta(days=i)).strftime('%d.%m')
        total_data.append(date_map.get(d_str, 0))

    return jsonify({"timeline": total_data})

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
    if s:
        try:
            c = json.loads(s.config_json)
            if action == 'start':
                c['is_active'] = True
                flash(f'{bot_name.capitalize()} Modul aktiviert.', 'success')
            elif action == 'stop':
                c['is_active'] = False
                flash(f'{bot_name.capitalize()} Modul deaktiviert.', 'warning')
            
            s.config_json = json.dumps(c)
            db.session.commit()
        except Exception as e:
            flash(f'Fehler beim Ändern des Modul-Status: {e}', 'danger')
    else:
        flash(f'Bot-Einstellungen für {bot_name} nicht gefunden.', 'danger')
        
    return redirect(request.referrer or url_for('dashboard.index'))

def master_bot_action(action):
    pfile = os.path.join(PROJECT_ROOT, "bots", "main_bot.pid")
    script = os.path.join(PROJECT_ROOT, "bots", "main_bot.py")
    lpath = os.path.join(PROJECT_ROOT, "bots", "main_bot.log")
    
    if action == 'start':
        if os.path.exists(pfile):
            try:
                with open(pfile, 'r') as f: pid = int(f.read().strip())
                if is_process_running(pid):
                    flash('Master-Bot läuft bereits.', 'warning')
                    return redirect(request.referrer or url_for('dashboard.index'))
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
        
        creationflags = 0
        if os.name == 'nt': creationflags = 0x00000008
            
        with open(lpath, 'a', encoding='utf-8') as lf: 
            proc = subprocess.Popen([exe, script], start_new_session=(os.name != 'nt'), creationflags=creationflags, stdout=lf, stderr=lf, env=env)
        with open(pfile, 'w') as f: f.write(str(proc.pid))
        flash('Master-Bot gestartet.', 'success')
        
    elif action == 'stop' and os.path.exists(pfile):
        try:
            with open(pfile, 'r') as f: pid = int(f.read().strip())
            if os.name == 'nt':
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                os.kill(pid, signal.SIGTERM)
            os.remove(pfile)
            flash('Master-Bot gestoppt.', 'success')
        except Exception as e:
            print(f"Fehler beim Stoppen vom Master Bot (PID: {pid}): {e}")
            flash('Fehler beim Stoppen des Master-Bots.', 'danger')
            
    return redirect(request.referrer or url_for('dashboard.index'))

@bp.route('/api/bot-status')
@login_required
def bot_status_api(): return jsonify(get_bot_status_simple())
