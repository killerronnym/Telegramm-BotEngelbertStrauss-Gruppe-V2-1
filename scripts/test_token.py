import os
import sys
import requests

# Setup Project Root for imports
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from shared_bot_utils import get_bot_token, get_shared_flask_app
from web_dashboard.app.models import IDFinderMessage, db

try:
    with get_shared_flask_app().app_context():
        print("Recent DB Messages:")
        for msg in IDFinderMessage.query.order_by(IDFinderMessage.timestamp.desc()).limit(5).all():
            try:
                print(f" - {msg.timestamp} | {msg.chat_type} | {msg.text}")
            except:
                print(f" - {msg.timestamp} | {msg.chat_type} | [Encoding Error]")
except Exception as e:
    print(f"DB Error: {e}")

token = get_bot_token()
if token:
    print(f"Token begins with: {token[:10]}...")
    # Check bot info
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getMe")
        print(f"Bot info: {r.json()}")
        r = requests.get(f"https://api.telegram.org/bot{token}/getWebhookInfo")
        print(f"Webhook Info: {r.json()}")
    except Exception as e:
        print(f"Telegram API Error: {e}")
else:
    print("Token: None")
