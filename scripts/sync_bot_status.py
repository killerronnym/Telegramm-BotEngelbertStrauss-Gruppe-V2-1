
import os
import sys
import json
from sqlalchemy import create_engine, text

# Pfade bestimmen
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from shared_bot_utils import get_db_url

def sync():
    db_url = get_db_url()
    print(f"Syncing DB: {db_url.split('@')[-1] if '@' in db_url else db_url}")
    engine = create_engine(db_url)
    
    try:
        with engine.connect() as conn:
            # Alle Einstellungen holen
            rows = conn.execute(
                text("SELECT bot_name, config_json, is_active FROM bot_settings")
            ).fetchall()
            
            for row in rows:
                bot_name = row[0]
                config = json.loads(row[1]) if row[1] else {}
                current_active_col = bool(row[2])
                
                # Status aus JSON ermitteln
                json_active = config.get('is_active', False)
                
                if json_active != current_active_col:
                    print(f"Syncing {bot_name}: Column {current_active_col} -> JSON {json_active}")
                    conn.execute(
                        text("UPDATE bot_settings SET is_active = :val WHERE bot_name = :name"),
                        {"val": 1 if json_active else 0, "name": bot_name}
                    )
            
            conn.commit()
            print("SUCCESS: Alle Bot-Status wurden synchronisiert!")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    sync()
