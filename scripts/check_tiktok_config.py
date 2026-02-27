
import os
import json
from sqlalchemy import create_engine, text

# Remote MySQL URL from .env
DB_URL = "mysql+pymysql://Drago:Ronny22092020%40@rinno.myds.me:3306/TelecombotDrago?charset=utf8mb4"

def run_diag():
    engine = create_engine(DB_URL)
    with engine.connect() as conn:
        print("--- TIKTOK BOT SETTINGS ---")
        settings = conn.execute(text("SELECT bot_name, is_active, config_json FROM bot_settings WHERE bot_name='tiktok'")).fetchone()
        if settings:
            print(f"TikTok Active (Dashboard): {settings[1]}")
            config = json.loads(settings[2]) if settings[2] else {}
            print(json.dumps(config, indent=2))
        else:
            print("TikTok settings NOT FOUND")

if __name__ == "__main__":
    run_diag()
