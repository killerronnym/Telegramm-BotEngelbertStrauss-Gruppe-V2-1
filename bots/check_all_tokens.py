import json
from shared_bot_utils import get_shared_flask_app
from web_dashboard.app.models import db, BotSettings
import requests

app = get_shared_flask_app()
with app.app_context():
    settings = BotSettings.query.all()
    for s in settings:
        cfg = json.loads(s.config_json)
        token = cfg.get('bot_token', '')
        if token:
            try:
                me = requests.get(f"https://api.telegram.org/bot{token}/getMe").json()
                username = me.get("result", {}).get("username", "Unknown")
                print(f"{s.bot_name}: {username} ({token[:10]}...)")
            except Exception as e:
                print(f"{s.bot_name}: Error {e}")
        else:
            print(f"{s.bot_name}: No token configured.")
