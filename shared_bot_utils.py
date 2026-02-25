import os
import sys
import json
from sqlalchemy import create_engine, text, inspect

# Pfade bestimmen
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
WEB_DASHBOARD_DIR = os.path.join(PROJECT_ROOT, 'web_dashboard')
INSTANCE_DIR = os.path.join(PROJECT_ROOT, 'instance')
DB_PATH = os.path.join(INSTANCE_DIR, 'app.db')

from dotenv import load_dotenv

# Env laden - expliziter Pfad zum Root
ENV_FILE = os.path.join(PROJECT_ROOT, '.env')
sys.stderr.write(f"DEBUG: Loading env from {ENV_FILE} - Exists: {os.path.exists(ENV_FILE)}\n")
if os.path.exists(ENV_FILE):
    load_dotenv(ENV_FILE, override=True) # Override to be sure

def get_db_url():
    """Gibt die konfigurierte Datenbank-URL zurück oder fällt auf SQLite zurück."""
    db_url = os.environ.get('DATABASE_URL')
    if db_url:
        # Pymysql-Parameter für UTF-8 sicherstellen
        if "mysql" in db_url and "charset=utf8mb4" not in db_url:
            separator = "&" if "?" in db_url else "?"
            db_url += f"{separator}charset=utf8mb4"
        return db_url
    
    # Fallback SQLite (Konsistent mit Docker/Windows Pfaden)
    # Bevorzugte Pfade: /app/instance/app.db oder ./instance/app.db
    if not os.path.exists(INSTANCE_DIR):
        os.makedirs(INSTANCE_DIR, exist_ok=True)
    return f"sqlite:///{DB_PATH}"

def get_bot_config(bot_name):
    """
    Lädt die Konfiguration für einen Bot aus der Datenbank.
    Gibt ein leeres Dictionary zurück, falls keine Config existiert.
    """
    try:
        url = get_db_url()
        # Fallback zum Verhindern von Abstürzen wenn DB noch nicht bereit
        if not os.path.exists(DB_PATH) and url.startswith("sqlite"):
            return {}

        engine = create_engine(url)
        with engine.connect() as conn:
            # Tabelle prüfen bevor Query
            if not inspect(engine).has_table("bot_settings"):
                return {}
                
            result = conn.execute(
                text("SELECT config_json FROM bot_settings WHERE bot_name = :name"),
                {"name": bot_name}
            ).fetchone()
            
            if result and result[0]:
                return json.loads(result[0])
            else:
                return {}
    except Exception as e:
        sys.stderr.write(f"ERROR loading config for {bot_name}: {str(e)}\n")
        return {}

def get_bot_token():
    """Zentrale Stelle für den Bot-Token. Priorisiert ENV vor DB."""
    # 1. Check ENV (am wichtigsten für Docker)
    env_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if env_token:
        return env_token
    
    # 2. Check DB ('id_finder' gilt als Master-Bot Config)
    config = get_bot_config('id_finder')
    return config.get('bot_token')

def get_env_var(key, default=None):
    return os.environ.get(key, default)

def is_bot_active(bot_name):
    """Prüft direkt via SQL, ob das Modul im Dashboard aktiviert ist."""
    config = get_bot_config(bot_name)
    return config.get('is_active', False)
