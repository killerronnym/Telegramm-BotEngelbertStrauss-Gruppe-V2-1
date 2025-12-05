import logging
import os
import json
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- Setup ------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# --- Konfiguration ----------------------------------------------
CONFIG_FILE = 'id_finder_config.json'

def load_config():
    """Lädt die Konfiguration aus der JSON-Datei."""
    default_config = {
        "is_enabled": False,
        "bot_token": ""
    }
    if not os.path.exists(CONFIG_FILE):
        return default_config
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return default_config

# --- Befehls-Handler --------------------------------------------
async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sendet eine Nachricht mit der Chat-ID und der Topic-ID."""
    chat_id = update.message.chat.id
    message_thread_id = update.message.message_thread_id

    response_text = f"📄 **ID-Informationen**\n\n"
    response_text += f"🔹 **Group-ID (chat.id):**\n`{chat_id}`\n\n"

    if message_thread_id:
        response_text += f"🔸 **Topic-ID (message_thread_id):**\n`{message_thread_id}`"
    else:
        response_text += "🔸 **Topic-ID (message_thread_id):**\n_Dieser Chat ist kein Thema (Topic)._"

    await update.message.reply_text(response_text, parse_mode='Markdown')

# --- Bot Start --------------------------------------------------
if __name__ == "__main__":
    config = load_config()
    BOT_TOKEN = config.get("bot_token")
    is_enabled = config.get("is_enabled", False)

    if not BOT_TOKEN or not is_enabled:
        logger.info("ID-Finder-Bot ist nicht aktiviert oder BOT_TOKEN fehlt in id_finder_config.json. Wird nicht gestartet.")
    else:
        app = ApplicationBuilder().token(BOT_TOKEN).build()
        app.add_handler(CommandHandler("id", get_id))

        logger.info("🤖 ID-Finder-Bot läuft…")
        app.run_polling()
