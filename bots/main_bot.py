import os
import sys
import json
import logging
import asyncio

# Setup Project Root for imports
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, Application
from web_dashboard.app import create_app, db
from shared_bot_utils import get_db_url, is_bot_active

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

# Konfiguration laden
load_dotenv(os.path.join(BASE_DIR, '.env'))

# Flask Setup für DB Querys ausserhalb von Requests
flask_app = create_app({'SQLALCHEMY_DATABASE_URI': get_db_url()})

from shared_bot_utils import is_bot_active, get_bot_token

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

def main():
    token = get_bot_token()
    if not token:
        logger.critical("❌ Kein Bot-Token gefunden (weder in ENV 'TELEGRAM_BOT_TOKEN' noch in DB)! Bot wird beendet.")
        sys.exit(1)

    logger.info("Starte ApplicationBuilder...")
    app = ApplicationBuilder().token(token)
    app = app.post_init(main_post_init).post_shutdown(main_post_shutdown).build()

    # --- HIER CORE/MASTER HANDLER HINZUFÜGEN ---
    # Beispielhafter Master Ping-Handler
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
        
    # Invite Bot
    if hasattr(invite_plugin, 'get_handlers'):
        for h in invite_plugin.get_handlers(): app.add_handler(h)
        
    # TikTok Bot (Hintergrund-Dienst)
    if hasattr(tiktok_plugin, 'setup_jobs'):
        tiktok_plugin.setup_jobs(app.job_queue)
        
    # Quiz Bot
    if hasattr(quiz_plugin, 'setup_jobs'):
        quiz_plugin.setup_jobs(app.job_queue)
        
    # Umfrage Bot
    if hasattr(umfrage_plugin, 'setup_jobs'):
        umfrage_plugin.setup_jobs(app.job_queue)

    # Outfit Bot
    if hasattr(outfit_plugin, 'get_handlers'):
        for h in outfit_plugin.get_handlers(): app.add_handler(h)
    if hasattr(outfit_plugin, 'setup_jobs'):
        outfit_plugin.setup_jobs(app.job_queue)

    logger.info("Starte globales Polling für alle Module...")
    # Polling starten
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
