import sys
import os
import json
import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
from shared_bot_utils import is_bot_active, get_shared_flask_app

# Navigation to root
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from web_dashboard.app.models import AutoReplyRule

# Logger setup
logger = logging.getLogger("AutoResponderBot")
logger.setLevel(logging.INFO)

# Check if bot is globally active
def is_bot_active_local() -> bool:
    try:
        from shared_bot_utils import is_bot_active
        return is_bot_active('auto_responder')
    except Exception as e:
        logger.error(f"Error checking if auto_responder is active: {e}")
        return False

# Reusable app instance for database querying
def get_app():
    return get_shared_flask_app()

def fetch_active_rules():
    """Liest alle aktiven AutoReplyRules aus der Datenbank."""
    app = get_app()
    if not app:
        return []
    with app.app_context():
        try:
            return AutoReplyRule.query.filter_by(is_active=True).all()
        except Exception as e:
            logger.error(f"Fehler beim Laden der Regeln aus der DB: {e}")
            return []

async def handle_dynamic_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fängt alle Commands ab und prüft, ob eine Regel dafür existiert."""
    if not update.message or not is_bot_active_local():
        return
        
    command_text = update.message.text.split()[0].lower() # z.B. "/ping"
    
    rules = fetch_active_rules()
    for rule in rules:
        if rule.trigger_type == 'command' and rule.trigger_text.lower() == command_text:
            try:
                await update.message.reply_text(rule.response_text)
                logger.info(f"Auto-Antwort auf Befehl gesendet: {command_text}")
                return
            except Exception as e:
                logger.error(f"Fehler beim Senden der Command-Antwort: {e}")

async def handle_dynamic_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prüft Textnachrichten auf hinterlegte Schlüsselwörter."""
    if not update.message or not update.message.text or not is_bot_active_local():
        return
        
    message_text = update.message.text.lower()
    
    rules = fetch_active_rules()
    for rule in rules:
        if rule.trigger_type == 'keyword':
            # Einfacher Substring-Match: Keyword muss irgendwo im Text vorkommen
            if rule.trigger_text.lower() in message_text:
                try:
                    await update.message.reply_text(rule.response_text)
                    logger.info(f"Auto-Antwort auf Keyword gesendet: '{rule.trigger_text}'")
                    # Break after the first match to avoid spamming multiple responses
                    return
                except Exception as e:
                    logger.error(f"Fehler beim Senden der Keyword-Antwort: {e}")

def get_handlers():
    """Gibt die Handler zurück, die main_bot.py registrieren soll."""
    h1 = CommandHandler(filters=filters.COMMAND, callback=handle_dynamic_command)
    # Filter: TEXT but NOT commands
    h2 = MessageHandler(filters.TEXT & (~filters.COMMAND), handle_dynamic_keyword)
    return [h1, h2]

def get_fallback_handlers():
    return []

def setup_jobs(job_queue):
    pass
