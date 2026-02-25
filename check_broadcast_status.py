
import os
import sys
import json
from sqlalchemy import create_engine, text

PROJECT_ROOT = r'c:\Users\Ronny M PC\Documents\Bot T'
sys.path.append(PROJECT_ROOT)

from shared_bot_utils import get_db_url

def check_broadcasts():
    url = get_db_url()
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT id, status, scheduled_at, text FROM broadcast ORDER BY created_at DESC LIMIT 5"))
            print("Recent Broadcasts:")
            for row in result:
                print(f"ID: {row[0]}, Status: {row[1]}, Scheduled: {row[2]}, Text: {row[3][:50]}...")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_broadcasts()
