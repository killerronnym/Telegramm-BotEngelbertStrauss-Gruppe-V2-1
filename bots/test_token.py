import os
from shared_bot_utils import get_bot_token, get_shared_flask_app
from web_dashboard.app.models import IDFinderMessage, db
import requests

with get_shared_flask_app().app_context():
    print("Recent DB Messages:")
    for msg in IDFinderMessage.query.order_by(IDFinderMessage.timestamp.desc()).limit(10).all():
        print(f" - {msg.timestamp} | {msg.chat_type} | {msg.text}")

token = get_bot_token()
print(f"Token begins with: {token[:10] if token else 'None'}...")

# Check webhook info
r = requests.get(f"https://api.telegram.org/bot{token}/getWebhookInfo")
print(f"Webhook Info: {r.json()}")
