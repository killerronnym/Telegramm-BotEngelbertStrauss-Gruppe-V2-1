import logging
import os
import json
from functools import wraps
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.error import TelegramError

# --- Setup & Konfiguration ------------------------------------
# ... (logging, config loading etc. as before)

def get_reply_parameters(config, update: Update):
    """Ermittelt, wohin eine Antwortnachricht gesendet werden soll."""
    log_topic_id = config.get('log_topic_id')
    if log_topic_id:
        return {
            "chat_id": config.get('main_group_id'),
            "message_thread_id": log_topic_id
        }
    else:
        return {
            "chat_id": update.effective_chat.id,
            "message_thread_id": update.effective_message.message_thread_id if update.effective_message else None
        }

# --- Befehls-Handler mit neuer Antwortlogik --------------------

@check_permission("warn") # (Beispiel, alle Befehle müssen so angepasst werden)
async def warn_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config = load_config()
    target_user, args = await get_target_user(update, context)
    
    # ... (Logik zum Verwarnen des Benutzers)

    reply_params = get_reply_parameters(config, update)
    response_text = f"⚠️ **{target_user.full_name}** wurde verwarnt."
    
    try:
        await context.bot.send_message(text=response_text, **reply_params)
    except TelegramError as e:
        logger.error(f"Konnte Bestätigungsnachricht nicht senden: {e}")
        # Fallback: Versuche, im ursprünglichen Chat zu antworten, falls das Senden an den Topic fehlschlägt
        if 'message_thread_id' in reply_params:
            try:
                await update.message.reply_text(f"Konnte Log nicht in Topic posten, aber Aktion war erfolgreich: {response_text}")
            except TelegramError:
                pass

# ... (Alle anderen Befehls-Handler werden nach diesem Muster umgebaut)

# --- Main Bot Logic -------------------------------------------
if __name__ == "__main__":
    # ... (Bot Start-Logik)
    pass
