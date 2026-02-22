from flask import Blueprint, jsonify, request
from ..models import db, BotSettings
import os
import re

bp = Blueprint('api', __name__, url_prefix='/api')

# Korrekter Pfad zur Log-Datei im Projekt-Root
# __file__ is web_dashboard/app/routes/api.py
# 1. dirname -> routes, 2. -> app, 3. -> web_dashboard
WEB_DASHBOARD_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 4. dirname -> project root
PROJECT_ROOT = os.path.dirname(WEB_DASHBOARD_DIR)
USER_INTERACTION_LOG_FILE = os.path.join(PROJECT_ROOT, "user_interactions.log") 

@bp.route('/bots')
def bots_list():
    bots = BotSettings.query.all()
    return jsonify([{'name': bot.bot_name, 'active': bot.is_active} for bot in bots])

@bp.route('/live-messages')
def get_live_messages():
    """
    Liest die Benutzerinteraktionen-Logdatei und gibt die Nachrichten als JSON zurück.
    """
    messages = []
    log_pattern = re.compile(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - User ID: (\d+) - Username: @(.*?) - Message: (.*)"
    )

    if not os.path.exists(USER_INTERACTION_LOG_FILE):
        return jsonify([])

    try:
        with open(USER_INTERACTION_LOG_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                match = log_pattern.match(line.strip())
                if match:
                    timestamp_str, user_id, username, text = match.groups()
                    messages.append({
                        'ts_str': timestamp_str,
                        'user_id': user_id,
                        'username': username,
                        'full_name': username, # Fallback, da wir den vollen Namen hier nicht haben
                        'text': text,
                        'is_private_interaction': True # Kennzeichen für Bot-Nachrichten
                    })
    except Exception as e:
        print(f"Error reading or parsing log file: {e}")
        return jsonify({"error": "Could not read log file"}), 500

    # Neueste Nachrichten zuerst
    return jsonify(sorted(messages, key=lambda x: x['ts_str'], reverse=True))
