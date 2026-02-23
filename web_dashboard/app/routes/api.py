from flask import Blueprint, jsonify, request, send_file, redirect
from ..models import db, BotSettings, IDFinderMessage, IDFinderUser, TopicMapping, IDFinderWarning, AutoCleanupTask
import os
import re
from datetime import datetime, timedelta
import requests
import json
import io

bp = Blueprint('api', __name__, url_prefix='/api')

# Pfade
WEB_DASHBOARD_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROJECT_ROOT = os.path.dirname(WEB_DASHBOARD_DIR)
USER_INTERACTION_LOG_FILE = os.path.join(PROJECT_ROOT, "user_interactions.log") 
AVATAR_CACHE_DIR = os.path.join(WEB_DASHBOARD_DIR, "app", "static", "avatars")
os.makedirs(AVATAR_CACHE_DIR, exist_ok=True)

@bp.route('/bots')
def bots_list():
    bots = BotSettings.query.all()
    return jsonify([{'name': bot.bot_name, 'active': bot.is_active} for bot in bots])

@bp.route('/live-messages')
def get_live_messages():
    topic_id = request.args.get('topic_id')
    
    query = IDFinderMessage.query
    if topic_id and topic_id != 'all':
        try:
            query = query.filter(IDFinderMessage.message_thread_id == int(topic_id))
        except: pass
        
    db_messages = query.order_by(IDFinderMessage.timestamp.desc()).limit(100).all()
    
    messages = []
    for m in db_messages:
        user = IDFinderUser.query.filter_by(telegram_id=m.telegram_user_id).first()
        topic = TopicMapping.query.filter_by(topic_id=m.message_thread_id).first()
        
        warning_count = IDFinderWarning.query.filter_by(telegram_user_id=m.telegram_user_id).count()
        
        messages.append({
            'id': m.id,
            'message_id': m.message_id,
            'chat_id': m.chat_id,
            'thread_id': m.message_thread_id,
            'topic_name': topic.topic_name if topic else f"Topic {m.message_thread_id}",
            'ts_str': m.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'user_id': m.telegram_user_id,
            'username': user.username if user else str(m.telegram_user_id),
            'full_name': f"{user.first_name or ''} {user.last_name or ''}".strip() if user else "Unbekannt",
            'text': m.text,
            'chat_type': m.chat_type,
            'is_private_interaction': False,
            'avatar_url': f"/api/avatar/{m.telegram_user_id}",
            'is_deleted': m.is_deleted,
            'deletion_reason': m.deletion_reason,
            'warning_count': warning_count
        })
    
    return jsonify(messages)

@bp.route('/avatar/<int:user_id>')
def get_avatar(user_id):
    avatar_path = os.path.join(AVATAR_CACHE_DIR, f"{user_id}.jpg")
    if os.path.exists(avatar_path):
        return send_file(avatar_path, mimetype='image/jpeg')
    
    settings = BotSettings.query.filter_by(bot_name='id_finder').first()
    if not settings: return jsonify({'error': 'No settings'}), 404
    config = json.loads(settings.config_json)
    bot_token = config.get('bot_token')
    
    if not bot_token:
        return redirect(f"https://ui-avatars.com/api/?name={user_id}&background=random")

    try:
        res = requests.get(f"https://api.telegram.org/bot{bot_token}/getUserProfilePhotos", params={'user_id': user_id, 'limit': 1})
        data = res.json()
        if data.get('ok') and data['result']['total_count'] > 0:
            file_id = data['result']['photos'][0][-1]['file_id']
            file_info = requests.get(f"https://api.telegram.org/bot{bot_token}/getFile", params={'file_id': file_id}).json()
            if file_info.get('ok'):
                file_path = file_info['result']['file_path']
                img_res = requests.get(f"https://api.telegram.org/file/bot{bot_token}/{file_path}")
                if img_res.status_code == 200:
                    with open(avatar_path, 'wb') as f:
                        f.write(img_res.content)
                    return send_file(io.BytesIO(img_res.content), mimetype='image/jpeg')
    except: pass
    return redirect(f"https://ui-avatars.com/api/?name={user_id}&background=random")

@bp.route('/topics')
def get_topics():
    topics = TopicMapping.query.all()
    return jsonify([{'id': t.topic_id, 'name': t.topic_name} for t in topics])

@bp.route('/moderation/delete', methods=['POST'])
def delete_message():
    data = request.json
    msg_db_id = data.get('id')
    reason = data.get('reason', 'Kein Grund angegeben')
    send_public = data.get('send_public', True)
    send_private = data.get('send_private', True)
    
    msg = IDFinderMessage.query.get(msg_db_id)
    if not msg:
        return jsonify({'success': False, 'error': 'Nachricht nicht gefunden'}), 404
    
    user = IDFinderUser.query.filter_by(telegram_id=msg.telegram_user_id).first()
    
    settings = BotSettings.query.filter_by(bot_name='id_finder').first()
    config = json.loads(settings.config_json) if settings else {}
    bot_token = config.get('bot_token')
    
    if not bot_token:
        return jsonify({'success': False, 'error': 'Bot Token fehlt'}), 500

    # Verwarnung in DB speichern
    new_warning = IDFinderWarning(
        telegram_user_id=msg.telegram_user_id,
        reason=reason,
        message_db_id=msg.id
    )
    db.session.add(new_warning)
    
    warning_count = IDFinderWarning.query.filter_by(telegram_user_id=msg.telegram_user_id).count() + 1
    max_warnings = config.get('max_warnings', 3)

    # 1. In Telegram löschen
    requests.post(f"https://api.telegram.org/bot{bot_token}/deleteMessage", json={'chat_id': msg.chat_id, 'message_id': msg.message_id})
    
    # 2. Öffentliche Nachricht im Topic
    if send_public:
        user_mention = f"@{user.username}" if user and user.username else f"<b>{user.first_name if user else msg.telegram_user_id}</b>"
        public_text = (
            f"🚫 <b>Nachricht gelöscht</b>\n\n"
            f"👤 Nutzer: {user_mention}\n"
            f"⚖️ Grund: {reason}\n"
            f"⚠️ Verwarnung: {warning_count}/{max_warnings}"
        )
        res = requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json={
            'chat_id': msg.chat_id,
            'message_thread_id': msg.message_thread_id,
            'text': public_text,
            'parse_mode': 'HTML'
        }).json()
        
        # Cleanup Task planen, falls konfiguriert
        cleanup_seconds = config.get('cleanup_notification_seconds', 60)
        if cleanup_seconds > 0 and res.get('ok'):
            cleanup_task = AutoCleanupTask(
                chat_id=msg.chat_id,
                message_id=res['result']['message_id'],
                cleanup_at=datetime.utcnow() + timedelta(seconds=cleanup_seconds)
            )
            db.session.add(cleanup_task)
        
    # 3. Private Nachricht über gewählten Bot
    if send_private:
        warning_bot_name = config.get('warning_bot_name', 'invite')
        warning_settings = BotSettings.query.filter_by(bot_name=warning_bot_name).first()
        if warning_settings:
            w_config = json.loads(warning_settings.config_json)
            w_token = w_config.get('bot_token')
            if w_token:
                private_text = (
                    f"Hallo, deine Nachricht in der Gruppe wurde gelöscht.\n\n"
                    f"Grund: {reason}\n"
                    f"Du hast nun {warning_count} von {max_warnings} Verwarnungen."
                )
                requests.post(f"https://api.telegram.org/bot{w_token}/sendMessage", json={
                    'chat_id': msg.telegram_user_id,
                    'text': private_text
                })

    msg.is_deleted = True
    msg.deletion_reason = reason
    db.session.commit()
    
    return jsonify({'success': True})

@bp.route('/moderation/settings', methods=['POST'])
def save_mod_settings():
    data = request.json
    settings = BotSettings.query.filter_by(bot_name='id_finder').first()
    if settings:
        config = json.loads(settings.config_json)
        config['max_warnings'] = int(data.get('max_warnings', 3))
        config['cleanup_notification_seconds'] = int(data.get('cleanup_notification_seconds', 60))
        config['warning_bot_name'] = data.get('warning_bot_name', 'invite')
        settings.config_json = json.dumps(config)
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False}), 404
