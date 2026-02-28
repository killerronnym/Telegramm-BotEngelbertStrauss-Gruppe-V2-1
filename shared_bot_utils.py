import os
import sys
import json
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import URL

# --- Globals & Engine Cache ---
_ENGINE_CACHE = {}
_SHARED_FLASK_APP = None

def get_engine(url):
    """Gibt eine gecachte SQLAlchemy-Engine für die URL zurück."""
    if url not in _ENGINE_CACHE:
        _ENGINE_CACHE[url] = create_engine(url, pool_pre_ping=True)
    return _ENGINE_CACHE[url]

# Basispfade bestimmen
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
WEB_DASHBOARD_DIR = os.path.join(PROJECT_ROOT, 'web_dashboard')
INSTANCE_DIR = os.path.join(PROJECT_ROOT, 'instance')
DB_PATH = os.path.join(INSTANCE_DIR, 'app.db')

# Env laden - expliziter Pfad zum Root
ENV_FILE = os.path.join(PROJECT_ROOT, '.env')
print(f"DEBUG: Loading env from {ENV_FILE} - Exists: {os.path.exists(ENV_FILE)}")
if os.path.exists(ENV_FILE):
    load_dotenv(ENV_FILE, override=True) # Override to be sure

def get_db_url():
    """Gibt die konfigurierte Datenbank-URL zurück oder fällt auf SQLite zurück."""
    # 1. Discrete Environment Variables (Best Practice für URLs mit Sonderzeichen)
    db_name = os.environ.get('DB_NAME')
    db_user = os.environ.get('DB_USER') # Added this line as it was missing
    db_host = os.environ.get('DB_HOST') # Added this line as it was missing
    
    if db_user and db_host and db_name:
        db_password = os.environ.get('DB_PASSWORD')
        db_port = os.environ.get('DB_PORT')
        db_driver = os.environ.get('DB_DRIVER', 'mysql+pymysql')
        
        query = {"charset": "utf8mb4"} if "mysql" in db_driver else {}
            
        url_obj = URL.create(
            drivername=db_driver,
            username=db_user,
            password=db_password,
            host=db_host,
            port=int(db_port) if db_port else None,
            database=db_name,
            query=query
        )
        return str(url_obj)

    # 2. Fallback DATABASE_URL
    db_url = os.environ.get('DATABASE_URL')
    if db_url:
        if "mysql" in db_url and "charset=utf8mb4" not in db_url:
            separator = "&" if "?" in db_url else "?"
            db_url += f"{separator}charset=utf8mb4"
        return db_url
    
    # 3. Fallback SQLite
    if not os.path.exists(INSTANCE_DIR):
        os.makedirs(INSTANCE_DIR, exist_ok=True)
    return f"sqlite:///{DB_PATH}"

def get_bot_config(bot_name):
    """Optimiertes Laden der Bot-Konfiguration."""
    try:
        url = get_db_url()
        if url.startswith("sqlite") and not os.path.exists(DB_PATH):
            return {}

        engine = get_engine(url)
        with engine.connect() as conn:
            # Tabelle prüfen bevor Query (optional, kann entfernt werden, wenn Tabelle immer existiert)
            if not inspect(engine).has_table("bot_settings"):
                return {}
                
            result = conn.execute(
                text("SELECT config_json FROM bot_settings WHERE bot_name = :name"),
                {"name": bot_name}
            ).fetchone()
            
            if result and result[0]:
                return json.loads(result[0])
    except Exception as e:
        sys.stderr.write(f"ERROR: get_bot_config({bot_name}): {e}\n")
    return {}

def get_bot_token():
    """Zentrale Stelle für den Bot-Token. Priorisiert ENV vor DB."""
    # 1. Check ENV
    env_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if env_token and env_token.strip():
        return env_token.strip()

    # 2. Check DB (ID Finder / Master Bot)
    try:
        config = get_bot_config("id_finder")
        return config.get("bot_token")
    except:
        return None

def get_env_var(key, default=None):
    return os.environ.get(key, default)

def is_bot_active(bot_name):
    """Effiziente Prüfung des Aktiv-Status."""
    try:
        url = get_db_url()
        if url.startswith("sqlite") and not os.path.exists(DB_PATH):
            return False

        engine = get_engine(url)
        with engine.connect() as conn:
            # Tabelle prüfen bevor Query
            if not inspect(engine).has_table("bot_settings"):
                return False
                
            result = conn.execute(
                text("SELECT config_json, is_active FROM bot_settings WHERE bot_name = :name"),
                {"name": bot_name}
            ).fetchone()
            
            if not result:
                return False
                
            # First check if there's a config_json that defines the active state
            if result[0]:
                try:
                    cfg = json.loads(result[0])
                    if 'is_active' in cfg:
                        return bool(cfg['is_active'])
                except:
                    pass
                    
            # Fallback to the database column
            return bool(result[1]) if result[1] is not None else False
            
    except Exception as e:
        sys.stderr.write(f"ERROR checking active status for {bot_name}: {e}\n")
        return False

def get_shared_flask_app():
    """Gibt eine geteilte Flask-App für DB-Queries zurück (Singleton)."""
    global _SHARED_FLASK_APP
    if _SHARED_FLASK_APP is None:
        # Import hier um zirkuläre Abhängigkeiten zu vermeiden
        from web_dashboard.app import create_app
        _SHARED_FLASK_APP = create_app()
    return _SHARED_FLASK_APP
