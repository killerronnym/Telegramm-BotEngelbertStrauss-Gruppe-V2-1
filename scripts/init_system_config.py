
import os
import sys
import json
from sqlalchemy import create_engine, text

# Pfade bestimmen
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from shared_bot_utils import get_db_url

def init_system():
    db_url = get_db_url()
    print(f"Initializing System Config in DB: {db_url.split('@')[-1] if '@' in db_url else db_url}")
    engine = create_engine(db_url)
    
    try:
        with engine.connect() as conn:
            # Prüfen ob schon da
            result = conn.execute(
                text("SELECT id FROM bot_settings WHERE bot_name='system'")
            ).fetchone()
            
            config = {
                'auto_update_enabled': True,
                'last_check_at': None
            }
            
            if result:
                print("System-Config existiert bereits. Setze auto_update_enabled auf True...")
                conn.execute(
                    text("UPDATE bot_settings SET config_json = :cfg, is_active = 1 WHERE bot_name = 'system'"),
                    {"cfg": json.dumps(config)}
                )
            else:
                print("Erstelle neue System-Config mit Auto-Update AKTIVIERT...")
                conn.execute(
                    text("INSERT INTO bot_settings (bot_name, config_json, is_active) VALUES ('system', :cfg, 1)"),
                    {"cfg": json.dumps(config)}
                )
            
            conn.commit()
            print("SUCCESS: Auto-Update System wurde erfolgreich initialisiert und AKTIVIERT!")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    init_system()
