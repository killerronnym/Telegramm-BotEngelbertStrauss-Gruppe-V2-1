
import os
import json
from sqlalchemy import create_engine, text

# Remote MySQL URL from .env
DB_URL = "mysql+pymysql://Drago:Ronny22092020%40@rinno.myds.me:3306/TelecombotDrago?charset=utf8mb4"

def run_diag():
    engine = create_engine(DB_URL)
    with engine.connect() as conn:
        print("--- BOT SETTINGS ---")
        settings = conn.execute(text("SELECT bot_name, is_active, config_json FROM bot_settings WHERE bot_name='id_finder'")).fetchone()
        if settings:
            print(f"ID-Finder Active: {settings[1]}")
            config = json.loads(settings[2]) if settings[2] else {}
            print(f"Main Group ID: {config.get('main_group_id')}")
        else:
            print("ID-Finder settings NOT FOUND")

        print("\n--- RECENT BROADCASTS (Last 10) ---")
        now_db = conn.execute(text("SELECT UTC_TIMESTAMP()")).scalar()
        print(f"Current DB UTC Time: {now_db}")
        
        broadcasts = conn.execute(text("SELECT id, text, scheduled_at, status FROM broadcast ORDER BY created_at DESC LIMIT 10")).fetchall()
        for b in broadcasts:
            print(f"ID: {b[0]} | Text: {b[1]} | Scheduled (UTC): {b[2]} | Status: {b[3]}")
    
if __name__ == "__main__":
    run_diag()
