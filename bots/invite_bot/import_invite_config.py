import sys
import os
import json

# Add project root to path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from web_dashboard.app.models import db, BotSettings
from shared_bot_utils import get_shared_flask_app

app = get_shared_flask_app()

def import_config():
    config_path = os.path.join(os.path.dirname(__file__), 'invite_bot_config.json')
    if not os.path.exists(config_path):
        print(f"Error: {config_path} not found.")
        return

    with open(config_path, 'r', encoding='utf-8') as f:
        new_config = json.load(f)

    with app.app_context():
        s = BotSettings.query.filter_by(bot_name='invite').first()
        if not s:
            print("Creating new BotSettings entry for 'invite'...")
            s = BotSettings(bot_name='invite')
            db.session.add(s)

        s.config_json = json.dumps(new_config, ensure_ascii=True)
        s.is_active = True
        db.session.commit()
        print("Invite Bot configuration has been successfully imported and enabled.")

if __name__ == '__main__':
    import_config()
