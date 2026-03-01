import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

import socket
from datetime import datetime

# Setup Project Root for imports
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

import json
import logging
import asyncio

try:
    import msvcrt
except ImportError:
    msvcrt = None
try:
    import fcntl
except ImportError:
    fcntl = None

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, Application, PicklePersistence
from web_dashboard.app import db
from shared_bot_utils import get_db_url, is_bot_active, get_bot_token, get_shared_flask_app

# Setup Logging
os.makedirs(os.path.join(BASE_DIR, "logs"), exist_ok=True)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler(os.path.join(BASE_DIR, "logs", "main_bot.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

hostname = socket.gethostname()
start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
logger.info(f"--- BOT IDENTITY: Host={hostname} | Start={start_time} | PID={os.getpid()} ---")

# Recursion Guard
os.environ["BOT_PROCESS"] = "1"

# Konfiguration laden
load_dotenv(os.path.join(BASE_DIR, '.env'))

# Flask Setup für DB Querys ausserhalb von Requests (Singleton aus utils nutzen)
flask_app = get_shared_flask_app()

import bots.id_finder_bot.id_finder_bot as id_finder_plugin
import bots.invite_bot.invite_bot as invite_plugin
import bots.tiktok_bot.tiktok_bot as tiktok_plugin
import bots.quiz_bot.quiz_bot as quiz_plugin
import bots.umfrage_bot.umfrage_bot as umfrage_plugin
import bots.outfit_bot.outfit_bot as outfit_plugin
import bots.auto_responder_bot.auto_responder_bot as auto_responder_plugin
import bots.profanity_bot.profanity_bot as profanity_plugin
import bots.birthday_bot.birthday_bot as birthday_plugin

async def main_post_init(app: Application) -> None:
    bot_info = await app.bot.get_me()
    logger.info(f"🚀 Master-Bot @{bot_info.username} initialisiert. Host: {socket.gethostname()}")

async def main_post_shutdown(app: Application) -> None:
    logger.info("🛑 Master-Bot wurde beendet und heruntergefahren.")

_keep_lock_alive = None

async def update_heartbeat(context: ContextTypes.DEFAULT_TYPE):
    """Aktualisiert einen Zeitstempel in der DB, damit das Dashboard weiß, dass der Bot lebt."""
    try:
        from web_dashboard.app.models import BotSettings
        with flask_app.app_context():
            s = BotSettings.query.filter_by(bot_name='id_finder').first()
            if s:
                cfg = json.loads(s.config_json) if s.config_json else {}
                cfg['last_heartbeat'] = datetime.now().isoformat()
                s.config_json = json.dumps(cfg)
                db.session.commit()
    except Exception as e:
        logger.error(f"Heartbeat Fehler: {e}")

def main():
    global _keep_lock_alive
    
    # --- Prozess-Lock prüfen ---
    lock_file_path = os.path.join(BASE_DIR, "logs", "main_bot.lock")
    try:
        lock_file = open(lock_file_path, "w")
        if os.name == 'nt' and msvcrt:
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        elif fcntl:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            logger.warning("⚠️ Kein Locking-Mechanismus verfügbar (msvcrt/fcntl fehlt).")
            
        _keep_lock_alive = lock_file
        
        # --- PID-File für Dashboard schreiben ---
        pid_file_path = os.path.join(BASE_DIR, "logs", "main_bot.pid")
        os.makedirs(os.path.dirname(pid_file_path), exist_ok=True)
        with open(pid_file_path, "w") as f:
            f.write(str(os.getpid()))
            
        import atexit
        def remove_pid():
            if os.path.exists(pid_file_path):
                try: os.remove(pid_file_path)
                except: pass
        atexit.register(remove_pid)

    except (IOError, ImportError):
        logger.error(f"❌ Andere Instanz läuft bereits (Lock auf {lock_file_path}). Host: {socket.gethostname()} | PID: {os.getpid()}")
        sys.exit(1)

    token = get_bot_token()
    if not token:
        logger.critical("❌ Kein Bot-Token gefunden (weder in ENV 'TELEGRAM_BOT_TOKEN' noch in DB)! Bot wird beendet.")
        sys.exit(1)

    logger.info("Starte ApplicationBuilder...")
    persistence = PicklePersistence(filepath=os.path.join(BASE_DIR, "instance", "persistence.pickle"))
    app = ApplicationBuilder().token(token).persistence(persistence)
    app = app.post_init(main_post_init).post_shutdown(main_post_shutdown).build()

    # --- HIER CORE/MASTER HANDLER HINZUFÜGEN ---
    async def master_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("✅ Master-Bot ist online und überwacht Module.")
    app.add_handler(CommandHandler("masterping", master_ping))

    # --- EINBINDUNG DER MANAGER ---
    # --- HANDLER REGISTRIERUNG ---
    main_handlers = []
    fallback_handlers = []

    # Safe registration helper
    def register_plugin(plugin, name):
        try:
            # ID Finder (Master Logic) - hat spezielle Struktur
            if name == "id_finder":
                if hasattr(plugin, 'get_handlers'):
                    for h in plugin.get_handlers(): app.add_handler(h)
                if hasattr(plugin, 'get_track_handler'):
                    app.add_handler(plugin.get_track_handler(), group=1)
                if hasattr(plugin, 'setup_jobs'):
                    plugin.setup_jobs(app.job_queue)
                return

            # Standard Module
            if hasattr(plugin, 'get_handlers'):
                for h in plugin.get_handlers():
                    main_handlers.append(h)
            
            if hasattr(plugin, 'get_fallback_handlers'):
                fallback_handlers.extend(plugin.get_fallback_handlers())
            
            if hasattr(plugin, 'setup_jobs'):
                plugin.setup_jobs(app.job_queue)
            
            logger.info(f"✅ Modul '{name}' erfolgreich geladen.")
        except Exception as e:
            logger.error(f"❌ Fehler beim Laden von Modul '{name}': {e}")

    register_plugin(birthday_plugin, "birthday")
    register_plugin(id_finder_plugin, "id_finder")
    register_plugin(invite_plugin, "invite")
    register_plugin(outfit_plugin, "outfit")
    register_plugin(quiz_plugin, "quiz")
    register_plugin(umfrage_plugin, "umfrage")
    register_plugin(tiktok_plugin, "tiktok")
    register_plugin(auto_responder_plugin, "auto_responder")
    register_plugin(profanity_plugin, "profanity_filter")

    # 1. Alle Haupt-Handler registrieren (Gruppe 0)
    for h in main_handlers:
        if isinstance(h, tuple):
            app.add_handler(h[0], group=h[1])
        else:
            app.add_handler(h)

    # 2. Alle Fallback-Handler registrieren (Gruppe 0 - am Ende!)
    for h in fallback_handlers:
        if isinstance(h, tuple):
            app.add_handler(h[0], group=h[1])
        else:
            app.add_handler(h)

    # Heartbeat alle 60 Sekunden
    app.job_queue.run_repeating(update_heartbeat, interval=60, first=5)

    logger.info("Starte globales Polling für alle Module...")
    # Polling mit Retry bei Conflict (hilfreich bei Docker Restarts)
    retry_count = 0
    while True:
        try:
            app.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)
            break # Normaler Exit
        except Exception as e:
            if "Conflict" in str(e):
                retry_count += 1
                logger.warning(f"⚠️ Telegram Conflict (Instanz läuft noch?). Retry {retry_count} in 10s...")
                import time
                time.sleep(10)
            else:
                logger.critical(f"💥 Kritischer Fehler im Polling: {e}")
                raise e

if __name__ == "__main__":
    main()
