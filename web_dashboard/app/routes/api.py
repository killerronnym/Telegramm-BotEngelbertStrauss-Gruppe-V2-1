from flask import Blueprint, jsonify, request, send_file, redirect, url_for
from ..models import db, BotSettings, IDFinderMessage, IDFinderUser, TopicMapping, IDFinderWarning, AutoCleanupTask
# Absolute import to avoid ModuleNotFoundError
from web_dashboard.updater import Updater
import os
import re
from datetime import datetime, timedelta
import requests
import json
import io
import traceback

bp = Blueprint('api', __name__, url_prefix='/api')

# Pfade
WEB_DASHBOARD_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROJECT_ROOT = os.path.dirname(WEB_DASHBOARD_DIR)
USER_INTERACTION_LOG_FILE = os.path.join(PROJECT_ROOT, "logs", "user_interactions.log") 
AVATAR_CACHE_DIR = os.path.join(WEB_DASHBOARD_DIR, "app", "static", "avatars")
MEDIA_CACHE_DIR = os.path.join(WEB_DASHBOARD_DIR, "app", "static", "media")
VERSION_FILE = os.path.join(PROJECT_ROOT, "version.json")
os.makedirs(AVATAR_CACHE_DIR, exist_ok=True)
os.makedirs(MEDIA_CACHE_DIR, exist_ok=True)

# Updater initialisieren mit deinen GitHub-Daten
updater = Updater(
    repo_owner="killerronnym",
    repo_name="Telegramm-BotEngelbertStrauss-Gruppe-V2-1",
    current_version_file=VERSION_FILE,
    project_root=PROJECT_ROOT
)

@bp.route('/update/check')
def update_check():
    info = updater.check_for_update()
    return jsonify(info)

@bp.route('/update/install', methods=['POST'])
def update_install():
    data = request.json
    if not data or 'url' not in data:
        return jsonify({"success": False, "error": "No URL"}), 400
    updater.install_update(data['url'], data['version'], data['published_at'])
    return jsonify({"success": True})

@bp.route('/update/status')
def update_status():
    return jsonify(updater.get_status())

@bp.route('/bots')
def bots_list():
    try:
        bots = BotSettings.query.all()
        return jsonify([{'name': bot.bot_name, 'active': bot.is_active} for bot in bots])
    except Exception as e:
        print(f"Error in bots_list: {e}")
        return jsonify([])

@bp.route('/live-messages')
def get_live_messages():
    try:
        topic_id = request.args.get('topic_id')
        query = IDFinderMessage.query
        if topic_id and topic_id != 'all':
            try: query = query.filter(IDFinderMessage.message_thread_id == int(topic_id))
            except: pass
        db_messages = query.order_by(IDFinderMessage.timestamp.desc()).limit(50).all()
        messages = []
        for m in db_messages:
            try:
                user = IDFinderUser.query.filter_by(telegram_id=m.telegram_user_id).first()
                topic = TopicMapping.query.filter_by(topic_id=m.message_thread_id).first() if m.message_thread_id else None
                warning_count = IDFinderWarning.query.filter_by(telegram_user_id=m.telegram_user_id).count()
                ts_iso = m.timestamp.isoformat() if m.timestamp else ""
                messages.append({
                    'id': m.id, 'message_id': m.message_id or 0, 'chat_id': m.chat_id or 0, 'thread_id': m.message_thread_id or 0,
                    'topic_name': str(topic.topic_name) if topic else (f"Topic {m.message_thread_id}" if m.message_thread_id else "Hauptchat"),
                    'ts_str': ts_iso, 'user_id': int(m.telegram_user_id),
                    'username': str(user.username) if user and user.username else str(m.telegram_user_id),
                    'full_name': str(f"{user.first_name or ''} {user.last_name or ''}".strip() if user else "Unbekannt"),
                    'text': str(m.text or ""), 'chat_type': str(m.chat_type or "unknown"),
                    'avatar_url': f"/api/avatar/{m.telegram_user_id}", 'is_deleted': bool(m.is_deleted),
                    'deletion_reason': str(m.deletion_reason or ""), 'warning_count': int(warning_count),
                    'content_type': str(m.content_type or 'text'),
                    'file_id': str(m.file_id or ''),
                })

            except: continue
        return jsonify(messages)
    except Exception as e:
        traceback.print_exc()
        return jsonify([])

@bp.route('/moderation/get-settings')
def get_mod_settings():
    try:
        settings = BotSettings.query.filter_by(bot_name='id_finder').first()
        if settings:
            config = json.loads(settings.config_json)
            return jsonify({'max_warnings': config.get('max_warnings', 3), 'cleanup_notification_seconds': config.get('cleanup_notification_seconds', 60), 'warning_bot_name': config.get('warning_bot_name', 'invite'), 'punishment_type': config.get('punishment_type', 'none'), 'mute_duration': config.get('mute_duration', 24)})
    except: pass
    return jsonify({'max_warnings': 3, 'cleanup_notification_seconds': 60, 'warning_bot_name': 'invite', 'punishment_type': 'none', 'mute_duration': 24})

@bp.route('/media/<file_id>')
def get_media(file_id):
    try:
        # Check if we have it in cache - look for any file starting with file_id
        if os.path.exists(MEDIA_CACHE_DIR):
            for filename in os.listdir(MEDIA_CACHE_DIR):
                if filename.startswith(file_id + "."):
                    file_path = os.path.join(MEDIA_CACHE_DIR, filename)
                    ext = filename.split('.')[-1].lower()
                    if ext == 'webp': mimetype = 'image/webp'
                    elif ext in ['jpg', 'jpeg']: mimetype = 'image/jpeg'
                    elif ext == 'png': mimetype = 'image/png'
                    elif ext == 'gif': mimetype = 'image/gif'
                    elif ext in ['mp4', 'm4v']: mimetype = 'video/mp4'
                    elif ext == 'webm': mimetype = 'video/webm'
                    elif ext in ['mov', 'qt']: mimetype = 'video/quicktime'
                    elif ext in ['avi']: mimetype = 'video/x-msvideo'
                    elif ext in ['mpeg', 'mpg']: mimetype = 'video/mpeg'
                    elif ext in ['ogg', 'oga', 'ogv']: mimetype = 'application/ogg'
                    elif ext in ['mp3']: mimetype = 'audio/mpeg'
                    elif ext in ['opus']: mimetype = 'audio/ogg'
                    elif ext in ['wav']: mimetype = 'audio/wav'
                    elif ext == 'tgs': mimetype = 'application/x-tgsticker'
                    else: mimetype = f'image/{ext}'
                    return send_file(file_path, mimetype=mimetype)
        
        # If not in cache, download from Telegram
        settings = BotSettings.query.filter_by(bot_name='id_finder').first()
        if not settings: return jsonify({'error': 'Master-Setting nicht gefunden'}), 404
        config = json.loads(settings.config_json); bot_token = config.get('bot_token')
        if not bot_token: return jsonify({'error': 'Master-Token fehlt in DB'}), 404
        
        # Get file info
        file_info_res = requests.get(f"https://api.telegram.org/bot{bot_token}/getFile", params={'file_id': file_id}, timeout=5)
        file_info = file_info_res.json()
        
        if file_info.get('ok'):
            remote_path = file_info['result']['file_path']
            # Extract extension
            ext = remote_path.split('.')[-1].lower() if '.' in remote_path else 'jpg'
            local_path = os.path.join(MEDIA_CACHE_DIR, f"{file_id}.{ext}")
            
            # Download file
            img_res = requests.get(f"https://api.telegram.org/file/bot{bot_token}/{remote_path}", timeout=10)
            if img_res.status_code == 200:
                with open(local_path, 'wb') as f: f.write(img_res.content)
                if ext == 'webp': mimetype = 'image/webp'
                elif ext in ['jpg', 'jpeg']: mimetype = 'image/jpeg'
                elif ext == 'png': mimetype = 'image/png'
                elif ext == 'gif': mimetype = 'image/gif'
                elif ext in ['mp4', 'm4v']: mimetype = 'video/mp4'
                elif ext == 'webm': mimetype = 'video/webm'
                elif ext in ['mov', 'qt']: mimetype = 'video/quicktime'
                elif ext in ['avi']: mimetype = 'video/x-msvideo'
                elif ext in ['mpeg', 'mpg']: mimetype = 'video/mpeg'
                elif ext in ['ogg', 'oga', 'ogv']: mimetype = 'application/ogg'
                elif ext in ['mp3']: mimetype = 'audio/mpeg'
                elif ext in ['opus']: mimetype = 'audio/ogg'
                elif ext in ['wav']: mimetype = 'audio/wav'
                elif ext == 'tgs': mimetype = 'application/x-tgsticker'
                else: mimetype = f'image/{ext}'
                return send_file(io.BytesIO(img_res.content), mimetype=mimetype)
    except Exception as e:
        print(f"Error in get_media: {e}")
    return jsonify({'error': 'Media not found'}), 404

@bp.route('/avatar/<int:user_id>')
def get_avatar(user_id):
    try:
        avatar_path = os.path.join(AVATAR_CACHE_DIR, f"{user_id}.jpg")
        if os.path.exists(avatar_path): return send_file(avatar_path, mimetype='image/jpeg')
        settings = BotSettings.query.filter_by(bot_name='id_finder').first()
        if not settings: return redirect(f"https://ui-avatars.com/api/?name={user_id}&background=random")
        config = json.loads(settings.config_json); bot_token = config.get('bot_token')
        if not bot_token: return redirect(f"https://ui-avatars.com/api/?name={user_id}&background=random")
        res = requests.get(f"https://api.telegram.org/bot{bot_token}/getUserProfilePhotos", params={'user_id': user_id, 'limit': 1}, timeout=3); data = res.json()
        if data.get('ok') and data['result']['total_count'] > 0:
            file_id = data['result']['photos'][0][-1]['file_id']
            file_info = requests.get(f"https://api.telegram.org/bot{bot_token}/getFile", params={'file_id': file_id}, timeout=3).json()
            if file_info.get('ok'):
                file_path = file_info['result']['file_path']
                img_res = requests.get(f"https://api.telegram.org/file/bot{bot_token}/{file_path}", timeout=5)
                if img_res.status_code == 200:
                    with open(avatar_path, 'wb') as f: f.write(img_res.content)
                    return send_file(io.BytesIO(img_res.content), mimetype='image/jpeg')
    except: pass
    return redirect(f"https://ui-avatars.com/api/?name={user_id}&background=random")

@bp.route('/topics')
def get_topics():
    try:
        topics = TopicMapping.query.all()
        return jsonify([{'id': t.topic_id, 'name': t.topic_name} for t in topics])
    except: return jsonify([])

@bp.route('/moderation/delete', methods=['POST'])
def delete_message():
    try:
        data = request.json; msg_db_id = data.get('id'); reason = data.get('reason', 'Kein Grund angegeben'); send_public = data.get('send_public', True); send_private = data.get('send_private', True)
        msg = IDFinderMessage.query.get(msg_db_id)
        if not msg: return jsonify({'success': False, 'error': 'Nachricht nicht gefunden'}), 404
        user = IDFinderUser.query.filter_by(telegram_id=msg.telegram_user_id).first(); settings = BotSettings.query.filter_by(bot_name='id_finder').first(); config = json.loads(settings.config_json) if settings else {}; bot_token = config.get('bot_token')
        if not bot_token: return jsonify({'success': False, 'error': 'Bot Token fehlt'}), 500
        new_warning = IDFinderWarning(telegram_user_id=msg.telegram_user_id, reason=reason, message_db_id=msg.id); db.session.add(new_warning); db.session.commit()
        warning_count = IDFinderWarning.query.filter_by(telegram_user_id=msg.telegram_user_id).count(); max_warnings = int(config.get('max_warnings', 3)); punishment_type = config.get('punishment_type', 'none'); mute_duration = int(config.get('mute_duration', 24))
        requests.post(f"https://api.telegram.org/bot{bot_token}/deleteMessage", json={'chat_id': msg.chat_id, 'message_id': msg.message_id}, timeout=5)
        action_taken_text = ""
        if warning_count >= max_warnings:
            if punishment_type == 'mute': until_date = int((datetime.utcnow() + timedelta(hours=mute_duration)).timestamp()); requests.post(f"https://api.telegram.org/bot{bot_token}/restrictChatMember", json={'chat_id': msg.chat_id, 'user_id': msg.telegram_user_id, 'permissions': {'can_send_messages': False}, 'until_date': until_date}, timeout=5); action_taken_text = f"\n🔇 <b>Nutzer für {mute_duration}h stummgeschaltet.</b>"
            elif punishment_type == 'kick': requests.post(f"https://api.telegram.org/bot{bot_token}/banChatMember", json={'chat_id': msg.chat_id, 'user_id': msg.telegram_user_id}, timeout=5); requests.post(f"https://api.telegram.org/bot{bot_token}/unbanChatMember", json={'chat_id': msg.chat_id, 'user_id': msg.telegram_user_id, 'only_if_banned': True}, timeout=5); action_taken_text = f"\n👞 <b>Nutzer aus der Gruppe geworfen.</b>"
            elif punishment_type == 'ban': requests.post(f"https://api.telegram.org/bot{bot_token}/banChatMember", json={'chat_id': msg.chat_id, 'user_id': msg.telegram_user_id}, timeout=5); action_taken_text = f"\n🔨 <b>Nutzer permanent gebannt.</b>"
        if send_public:
            user_mention = f"@{user.username}" if user and user.username else f"<b>{user.first_name if user else msg.telegram_user_id}</b>"
            public_text = (f"🚫 <b>Nachricht gelöscht</b>\n\n👤 Nutzer: {user_mention}\n⚖️ Grund: {reason}\n⚠️ Verwarnung: {warning_count}/{max_warnings}{action_taken_text}")
            res = requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json={'chat_id': msg.chat_id, 'message_thread_id': msg.message_thread_id, 'text': public_text, 'parse_mode': 'HTML'}, timeout=5).json()
            cleanup_seconds = int(config.get('cleanup_notification_seconds', 60))
            if cleanup_seconds > 0 and res.get('ok'): db.session.add(AutoCleanupTask(chat_id=msg.chat_id, message_id=res['result']['message_id'], cleanup_at=datetime.utcnow() + timedelta(seconds=cleanup_seconds)))
        if send_private:
            warning_bot_name = config.get('warning_bot_name', 'invite'); warning_settings = BotSettings.query.filter_by(bot_name=warning_bot_name).first()
            if warning_settings:
                # SSoT: Wir nutzen den Master-Token vom id_finder, es sei denn wir wollen wirklich 
                # einen separaten Bot. Aber da alles konsolidiert werden soll:
                w_token = bot_token 
                if w_token:
                    private_text = (f"Hallo, deine Nachricht in der Gruppe wurde gelöscht.\n\nGrund: {reason}\nDu hast nun {warning_count} von {max_warnings} Verwarnungen.")
                    if action_taken_text: private_text += f"\nKonsequenz: {action_taken_text.replace('<b>', '').replace('</b>', '')}"
                    requests.post(f"https://api.telegram.org/bot{w_token}/sendMessage", json={'chat_id': msg.telegram_user_id, 'text': private_text}, timeout=5)
        msg.is_deleted = True; msg.deletion_reason = reason; db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route('/moderation/settings', methods=['POST'])
def save_mod_settings():
    try:
        data = request.json; settings = BotSettings.query.filter_by(bot_name='id_finder').first()
        if settings:
            config = json.loads(settings.config_json); config['max_warnings'] = int(data.get('max_warnings', 3)); config['cleanup_notification_seconds'] = int(data.get('cleanup_notification_seconds', 60)); config['warning_bot_name'] = data.get('warning_bot_name', 'invite'); config['punishment_type'] = data.get('punishment_type', 'none'); config['mute_duration'] = int(data.get('mute_duration', 24)); settings.config_json = json.dumps(config); db.session.commit()
            return jsonify({'success': True})
    except: pass
    return jsonify({'success': False}), 400

@bp.route('/moderation/warnings/delete/<int:warning_id>', methods=['POST'])
def delete_warning(warning_id):
    try:
        data = request.json or {}
        chat_id = data.get('chat_id')
        thread_id = data.get('thread_id')
        send_public = data.get('send_public', False)
        send_private = data.get('send_private', False)
        
        warning = IDFinderWarning.query.get(warning_id)
        if not warning: return jsonify({'success': False}), 404
        
        user_id = warning.telegram_user_id
        user = IDFinderUser.query.filter_by(telegram_id=user_id).first()
        
        db.session.delete(warning)
        db.session.commit()
        
        # Notifications
        if send_public or send_private:
            settings = BotSettings.query.filter_by(bot_name='id_finder').first()
            config = json.loads(settings.config_json) if settings else {}
            bot_token = config.get('bot_token')
            
            if bot_token:
                user_name = f"@{user.username}" if user and user.username else f"<b>{user.first_name if user else user_id}</b>"
                
                if send_public and chat_id:
                    public_text = f"ℹ️ Eine Verwarnung für {user_name} wurde zurückgesetzt!"
                    res = requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", 
                                  json={'chat_id': chat_id, 'message_thread_id': thread_id, 'text': public_text, 'parse_mode': 'HTML'}, timeout=5).json()
                    
                    cleanup_seconds = int(config.get('cleanup_notification_seconds', 60))
                    if cleanup_seconds > 0 and res.get('ok'):
                        db.session.add(AutoCleanupTask(
                            chat_id=chat_id, 
                            message_id=res['result']['message_id'], 
                            cleanup_at=datetime.utcnow() + timedelta(seconds=cleanup_seconds)
                        ))
                        db.session.commit()
                
                if send_private:
                    # SSoT: Nutze Master-Token
                    w_token = bot_token
                    if w_token:
                        private_text = "Hallo, eine deiner Verwarnungen wurde zurückgesetzt."
                        requests.post(f"https://api.telegram.org/bot{w_token}/sendMessage", 
                                      json={'chat_id': user_id, 'text': private_text}, timeout=5)

        return jsonify({'success': True})
    except Exception as e:
        print(f"Error deleting warning: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route('/moderation/warnings/clear/<int:user_id>', methods=['POST'])
def clear_all_warnings(user_id):
    try:
        data = request.json or {}
        chat_id = data.get('chat_id')
        thread_id = data.get('thread_id')
        send_public = data.get('send_public', False)
        send_private = data.get('send_private', False)
        
        user = IDFinderUser.query.filter_by(telegram_id=user_id).first()
        
        IDFinderWarning.query.filter_by(telegram_user_id=user_id).delete()
        db.session.commit()
        
        # Notifications
        if send_public or send_private:
            settings = BotSettings.query.filter_by(bot_name='id_finder').first()
            config = json.loads(settings.config_json) if settings else {}
            bot_token = config.get('bot_token')
            
            if bot_token:
                user_name = f"@{user.username}" if user and user.username else f"<b>{user.first_name if user else user_id}</b>"
                
                if send_public and chat_id:
                    public_text = f"✅ Alle Verwarnungen für {user_name} wurden zurückgesetzt!"
                    res = requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", 
                                  json={'chat_id': chat_id, 'message_thread_id': thread_id, 'text': public_text, 'parse_mode': 'HTML'}, timeout=5).json()
                    
                    cleanup_seconds = int(config.get('cleanup_notification_seconds', 60))
                    if cleanup_seconds > 0 and res.get('ok'):
                        db.session.add(AutoCleanupTask(
                            chat_id=chat_id, 
                            message_id=res['result']['message_id'], 
                            cleanup_at=datetime.utcnow() + timedelta(seconds=cleanup_seconds)
                        ))
                        db.session.commit()
                
                if send_private:
                    # SSoT: Nutze Master-Token
                    w_token = bot_token
                    if w_token:
                        private_text = "Hallo, deine Verwarnungen wurden alle zurückgesetzt."
                        requests.post(f"https://api.telegram.org/bot{w_token}/sendMessage", 
                                      json={'chat_id': user_id, 'text': private_text}, timeout=5)

        return jsonify({'success': True})
    except Exception as e:
        print(f"Error clearing warnings: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route('/system/settings')
def get_system_settings():
    try:
        settings = BotSettings.query.filter_by(bot_name='system').first()
        if settings:
            return jsonify(json.loads(settings.config_json))
    except: pass
    return jsonify({'auto_update_enabled': False, 'last_check_at': None})

@bp.route('/system/settings/save', methods=['POST'])
def save_system_settings():
    try:
        data = request.json
        settings = BotSettings.query.filter_by(bot_name='system').first()
        if not settings:
            settings = BotSettings(bot_name='system', config_json='{}')
            db.session.add(settings)
        
        config = json.loads(settings.config_json) if settings.config_json else {}
        
        if 'auto_update_enabled' in data:
            config['auto_update_enabled'] = bool(data['auto_update_enabled'])
            
        settings.config_json = json.dumps(config)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400
