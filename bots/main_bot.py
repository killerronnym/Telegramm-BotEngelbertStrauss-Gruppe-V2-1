import os
import sys

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
from web_dashboard.app import create_app, db
from shared_bot_utils import get_db_url, is_bot_active, get_bot_token

# Setup Logging
os.makedirs("bots", exist_ok=True)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bots/main_bot.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

logger.info(f"--- BOT STARTUP ATTEMPT (PID: {os.getpid()}) ---")

# Recursion Guard
os.environ["BOT_PROCESS"] = "1"

# Konfiguration laden
load_dotenv(os.path.join(BASE_DIR, '.env'))

# Flask Setup für DB Querys ausserhalb von Requests
flask_app = create_app({'SQLALCHEMY_DATABASE_URI': get_db_url()})

import bots.id_finder_bot.id_finder_bot as id_finder_plugin
import bots.invite_bot.invite_bot as invite_plugin
import bots.tiktok_bot.tiktok_bot as tiktok_plugin
import bots.quiz_bot.quiz_bot as quiz_plugin
import bots.umfrage_bot.umfrage_bot as umfrage_plugin
import bots.outfit_bot.outfit_bot as outfit_plugin

async def main_post_init(app: Application) -> None:
    logger.info("🚀 Master-Bot initialisiert. Startvorgang läuft...")

async def main_post_shutdown(app: Application) -> None:
    logger.info("🛑 Master-Bot wurde beendet und heruntergefahren.")

_keep_lock_alive = None

def main():
    global _keep_lock_alive
    
    # --- Prozess-Lock prüfen ---
    lock_file_path = os.path.join(BASE_DIR, "bots", "main_bot.lock")
    try:
        lock_file = open(lock_file_path, "w")
        if os.name == 'nt' and msvcrt:
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        elif fcntl:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            logger.warning("⚠️ Kein Locking-Mechanismus verfügbar (msvcrt/fcntl fehlt).")
            
        _keep_lock_alive = lock_file
    except (IOError, ImportError):
        logger.error(f"❌ Eine andere Instanz des Bots läuft bereits (Lock auf {lock_file_path}). Beende PID {os.getpid()}...")
        sys.exit(1)

    token = get_bot_token()
    if not token:
        logger.critical("❌ Kein Bot-Token gefunden (weder in ENV 'TELEGRAM_BOT_TOKEN' noch in DB)! Bot wird beendet.")
        sys.exit(1)

    logger.info("Starte ApplicationBuilder...")
    persistence = PicklePersistence(filepath=os.path.join(BASE_DIR, "bots", "persistence.pickle"))
    app = ApplicationBuilder().token(token).persistence(persistence)
    app = app.post_init(main_post_init).post_shutdown(main_post_shutdown).build()

    # --- HIER CORE/MASTER HANDLER HINZUFÜGEN ---
    async def master_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("✅ Master-Bot ist online und überwacht Module.")
    app.add_handler(CommandHandler("masterping", master_ping))

    # --- EINBINDUNG DER MANAGER ---
    logger.info("Lade Module-Handler...")
    
    # ID Finder (Master Logic)
    if hasattr(id_finder_plugin, 'get_handlers'):
        for h in id_finder_plugin.get_handlers(): app.add_handler(h)
    if hasattr(id_finder_plugin, 'get_track_handler'):
        app.add_handler(id_finder_plugin.get_track_handler(), group=1)
    if hasattr(id_finder_plugin, 'setup_jobs'):
        id_finder_plugin.setup_jobs(app.job_queue)
        
    # --- HANDLER REGISTRIERUNG ---
    main_handlers = []
    fallback_handlers = []

    # Invite Bot
    if hasattr(invite_plugin, 'get_handlers'):
        main_handlers.extend(invite_plugin.get_handlers())
    if hasattr(invite_plugin, 'get_fallback_handlers'):
        fallback_handlers.extend(invite_plugin.get_fallback_handlers())

    # Outfit Bot
    if hasattr(outfit_plugin, 'get_handlers'):
        for h in outfit_plugin.get_handlers():
            main_handlers.append(h)

    # Quiz Bot
    if hasattr(quiz_plugin, 'setup_jobs'):
        quiz_plugin.setup_jobs(app.job_queue)
        
    # Umfrage Bot
    if hasattr(umfrage_plugin, 'setup_jobs'):
        umfrage_plugin.setup_jobs(app.job_queue)

    # TikTok Bot (Hintergrund-Dienst)
    if hasattr(tiktok_plugin, 'setup_jobs'):
        tiktok_plugin.setup_jobs(app.job_queue)

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

    logger.info("Starte globales Polling für alle Module...")
    # Polling starten
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
