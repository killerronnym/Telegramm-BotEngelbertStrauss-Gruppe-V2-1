import sys
import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

from web_dashboard.app.models import db, BotSettings
from shared_bot_utils import get_shared_flask_app

app = get_shared_flask_app()

def enable_invite():
    with app.app_context():
        s = BotSettings.query.filter_by(bot_name='invite').first()
        if not s:
            print("Settings not found.")
            return

        cfg = json.loads(s.config_json)
        cfg['is_enabled'] = True
        s.config_json = json.dumps(cfg, ensure_ascii=True)
        s.is_active = True
        db.session.commit()
        print("Invite Bot has been successfully re-enabled in the database.")

if __name__ == '__main__':
    enable_invite()
