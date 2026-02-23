from flask import Blueprint, jsonify, request, send_file
from ..models import db, BotSettings, IDFinderMessage, IDFinderUser, TopicMapping
import os
import re
from datetime import datetime
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
            'avatar_url': f"/api/avatar/{m.telegram_user_id}"
        })
    
    return jsonify(messages)

@bp.route('/avatar/<int:user_id>')
def get_avatar(user_id):
    """
    Holt das Profilbild des Nutzers von Telegram oder aus dem Cache.
    """
    avatar_path = os.path.join(AVATAR_CACHE_DIR, f"{user_id}.jpg")
    
    # 1. Wenn Bild im Cache ist, gib es zurück
    if os.path.exists(avatar_path):
        return send_file(avatar_path, mimetype='image/jpeg')
    
    # 2. Wenn nicht, frage Bot-Token ab
    settings = BotSettings.query.filter_by(bot_name='id_finder').first()
    if not settings: return jsonify({'error': 'No settings'}), 404
    config = json.loads(settings.config_json)
    bot_token = config.get('bot_token')
    
    try:
        # User Profilbilder abfragen
        res = requests.get(f"https://api.telegram.org/bot{bot_token}/getUserProfilePhotos", params={'user_id': user_id, 'limit': 1})
        data = res.json()
        
        if data.get('ok') and data['result']['total_count'] > 0:
            file_id = data['result']['photos'][0][-1]['file_id']
            
            # File Path holen
            file_info = requests.get(f"https://api.telegram.org/bot{bot_token}/getFile", params={'file_id': file_id}).json()
            if file_info.get('ok'):
                file_path = file_info['result']['file_path']
                # Bild herunterladen
                img_res = requests.get(f"https://api.telegram.org/file/bot{bot_token}/{file_path}")
                if img_res.status_code == 200:
                    with open(avatar_path, 'wb') as f:
                        f.write(img_res.content)
                    return send_file(io.BytesIO(img_res.content), mimetype='image/jpeg')
    except Exception as e:
        print(f"Error fetching avatar: {e}")

    # Fallback: Platzhalter Bild (z.B. UI Avatars)
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
    
    settings = BotSettings.query.filter_by(bot_name='id_finder').first()
    config = json.loads(settings.config_json) if settings else {}
    bot_token = config.get('bot_token')
    
    if not bot_token:
        return jsonify({'success': False, 'error': 'Bot Token fehlt'}), 500

    # 1. In Telegram löschen
    delete_url = f"https://api.telegram.org/bot{bot_token}/deleteMessage"
    requests.post(delete_url, json={'chat_id': msg.chat_id, 'message_id': msg.message_id})
    
    # 2. Öffentliche Nachricht im Topic
    if send_public:
        public_text = f"🚫 Nachricht gelöscht.\n👤 Nutzer: {msg.telegram_user_id}\n⚖️ Grund: {reason}"
        send_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        requests.post(send_url, json={
            'chat_id': msg.chat_id,
            'message_thread_id': msg.message_thread_id,
            'text': public_text
        })
        
    # 3. Private Nachricht über gewählten Bot
    if send_private:
        warning_bot_name = config.get('warning_bot_name', 'invite')
        warning_settings = BotSettings.query.filter_by(bot_name=warning_bot_name).first()
        if warning_settings:
            w_config = json.loads(warning_settings.config_json)
            w_token = w_config.get('bot_token')
            if w_token:
                private_text = f"Hallo, deine Nachricht in der Gruppe wurde gelöscht.\n\nGrund: {reason}"
                requests.post(f"https://api.telegram.org/bot{w_token}/sendMessage", json={
                    'chat_id': msg.telegram_user_id,
                    'text': private_text
                })

    # 4. Aus DB löschen
    db.session.delete(msg)
    db.session.commit()
    
    return jsonify({'success': True})
