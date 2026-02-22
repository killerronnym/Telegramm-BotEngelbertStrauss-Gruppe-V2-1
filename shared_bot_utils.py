import os
import sys
import json
from sqlalchemy import create_engine, text, inspect

# Pfade bestimmen
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
WEB_DASHBOARD_DIR = os.path.join(PROJECT_ROOT, 'web_dashboard')
# Correctly point to the instance directory in the project root
INSTANCE_DIR = os.path.join(PROJECT_ROOT, 'instance')
DB_PATH = os.path.join(INSTANCE_DIR, 'app.db')

# Sicherstellen, dass das 'instance'-Verzeichnis existiert
# print(f"DEBUG: Ensuring instance directory exists: {INSTANCE_DIR}")
if not os.path.exists(INSTANCE_DIR):
    os.makedirs(INSTANCE_DIR)
    # print(f"DEBUG: Created instance directory: {INSTANCE_DIR}")

# Datenbank initialisieren, falls nicht vorhanden
# print(f"DEBUG: Checking for database at: {DB_PATH}")
if not os.path.exists(DB_PATH):
    try:
        engine = create_engine(f'sqlite:///{DB_PATH}')
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS bot_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_name TEXT UNIQUE NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT FALSE,
                    config_json TEXT NOT NULL
                );
            """))
            conn.commit()
        print(f"Info: Datenbank und bot_settings Tabelle unter {DB_PATH} initialisiert.")
    except Exception as e:
        print(f"FEHLER: Konnte Datenbank oder Tabelle nicht initialisieren: {e}")

def get_bot_config(bot_name):
    """
    Lädt die Konfiguration für einen Bot aus der SQLite-Datenbank.
    Gibt ein leeres Dictionary zurück, falls keine Config existiert.
    """
    # print(f"DEBUG: Attempting to get config for bot: {bot_name} from DB_PATH: {DB_PATH}")
    try:
        engine = create_engine(f'sqlite:///{DB_PATH}')
        with engine.connect() as conn:
            inspector = inspect(engine)
            if not inspector.has_table("bot_settings"):
                print(f"WARNUNG: bot_settings Tabelle fehlt in {DB_PATH}. Erstelle sie.")
                conn.execute(text("""
                    CREATE TABLE bot_settings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        bot_name TEXT UNIQUE NOT NULL,
                        is_active BOOLEAN NOT NULL DEFAULT FALSE,
                        config_json TEXT NOT NULL
                    );
                """))
                conn.commit()

            result = conn.execute(
                text("SELECT config_json FROM bot_settings WHERE bot_name = :name"),
                {"name": bot_name}
            ).fetchone()
            
            if result and result[0]:
                # print(f"DEBUG: Config found for {bot_name}.")
                return json.loads(result[0])
            else:
                # print(f"DEBUG: No config found for {bot_name}. Returning empty dict.")
                return {}
    except Exception as e:
        print(f"FEHLER: Beim Laden der Config für {bot_name}: {e}")
        return {}

def get_env_var(key, default=None):
    """
    Lädt eine Umgebungsvariable (z.B. aus .env).
    """
    return os.environ.get(key, default)
