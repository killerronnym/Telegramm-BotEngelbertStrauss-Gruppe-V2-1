
import os
import sys
import json
from sqlalchemy import create_engine, text

# Pfade bestimmen
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from shared_bot_utils import get_db_url

def check():
    db_url = get_db_url()
    print(f"Checking DB: {db_url.split('@')[-1] if '@' in db_url else db_url}")
    engine = create_engine(db_url)
    
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT config_json FROM bot_settings WHERE bot_name='invite'")
            ).fetchone()
            
            if result and result[0]:
                config = json.loads(result[0])
                print(f"Main Chat ID: {config.get('main_chat_id')}")
                print(f"Whitelist Enabled: {config.get('whitelist_enabled')}")
                print(f"Whitelist Approval Chat ID: {config.get('whitelist_approval_chat_id')}")
            else:
                print("No config found for 'invite'")
                
            # Also check pending applications
            apps = conn.execute(text("SELECT id, telegram_user_id, status, answers_json FROM invite_applications WHERE status='pending'")).fetchall()
            print(f"\nPending Applications: {len(apps)}")
            for app in apps:
                ans = json.loads(app.answers_json) if app.answers_json else {}
                print(f"  ID: {app.id}, User: {app.telegram_user_id}, Target Chat: {ans.get('target_chat_id')}")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check()
