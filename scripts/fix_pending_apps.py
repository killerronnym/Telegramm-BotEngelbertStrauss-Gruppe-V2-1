
import os
import sys
import json
import traceback

# Pfade bestimmen
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from shared_bot_utils import get_db_url, get_bot_config
from sqlalchemy import create_engine, text

def fix():
    print("--- Start Application Fix ---")
    
    db_url = get_db_url()
    engine = create_engine(db_url)
    
    config = get_bot_config('invite')
    correct_chat_id = config.get('main_chat_id')
    
    if not correct_chat_id:
        print("Fehler: Keine Hauptgruppen-ID in der Bot-Konfiguration gefunden!")
        return

    print(f"Ziel: Alle 'pending' Anträge auf Chat ID {correct_chat_id} setzen.")

    try:
        with engine.connect() as conn:
            # Alle pending Anträge holen
            result = conn.execute(
                text("SELECT id, answers_json FROM invite_applications WHERE status = 'pending'")
            ).fetchall()

            count = 0
            for row in result:
                app_id = row[0]
                answers = json.loads(row[1]) if row[1] else {}
                
                # ID korrigieren
                answers['target_chat_id'] = correct_chat_id
                
                conn.execute(
                    text("UPDATE invite_applications SET answers_json = :ans WHERE id = :id"),
                    {"ans": json.dumps(answers), "id": app_id}
                )
                count += 1
            
            conn.commit()
            print(f"SUCCESS: {count} Anträge wurden korrigiert!")
            
    except Exception as e:
        print(f"ERROR: {str(e)}")
        traceback.print_exc()

if __name__ == "__main__":
    fix()
