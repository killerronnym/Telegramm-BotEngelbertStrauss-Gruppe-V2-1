import sys
import os
import json
import requests
from dotenv import load_dotenv

PROJECT_ROOT = r"c:\Users\Ronny M PC\Documents\Bot T"
sys.path.append(PROJECT_ROOT)
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

# I need a valid file_id. I'll pick one from the DB or just test the logic.
# I will use the bot_token from id_finder settings.

def test_fetch(file_id):
    from web_dashboard.app.models import BotSettings
    from flask import Flask
    from web_dashboard.app.models import db
    
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL")
    db.init_app(app)
    
    with app.app_context():
        settings = BotSettings.query.filter_by(bot_name='id_finder').first()
        config = json.loads(settings.config_json)
        bot_token = config.get('bot_token')
        
        print(f"Using Bot Token: {bot_token[:10]}...")
        
        # Get file info
        res = requests.get(f"https://api.telegram.org/bot{bot_token}/getFile", params={'file_id': file_id})
        print(f"getFile Response: {res.status_code}")
        print(f"Data: {res.json()}")

if __name__ == "__main__":
    # If I don't have a file_id, I can't test much.
    # But I can at least check if the bot_token is valid.
    test_fetch("dummy_id") # This will fail but show if we can connect
