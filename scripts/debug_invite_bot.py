
import os
import sys
import json
from sqlalchemy import create_engine, text

PROJECT_ROOT = r'c:\Users\Ronny M PC\Documents\Bot T'
sys.path.append(PROJECT_ROOT)

from shared_bot_utils import get_db_url

def check_db():
    url = get_db_url()
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            print("--- Recent Apps ---")
            result = conn.execute(text("SELECT telegram_user_id, username, status, created_at FROM invite_application ORDER BY created_at DESC LIMIT 10"))
            for row in result:
                print(row)
            
            print("\n--- Recent Logs ---")
            result = conn.execute(text("SELECT telegram_user_id, username, action, created_at FROM invite_log ORDER BY created_at DESC LIMIT 20"))
            for row in result:
                uid, user, action, created = row
                # Safe print
                safe_action = str(action)[:50].replace('\n', ' ')
                print(f"{uid} | {user} | {safe_action} | {created}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_db()
