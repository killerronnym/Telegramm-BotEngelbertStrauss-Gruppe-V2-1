
import os
import sys
import asyncio
import logging

# Setup Project Root for imports
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from telegram import Bot
from telegram.error import TelegramError
from shared_bot_utils import get_bot_token

async def check_access(chat_id):
    token = get_bot_token()
    if not token:
        print("Fehler: Kein Token gefunden.")
        return

    bot = Bot(token)
    try:
        me = await bot.get_me()
        print(f"Bot-Info: @{me.username} (ID: {me.id})")
        
        chat = await bot.get_chat(chat_id)
        print(f"Chat gefunden: {chat.title} (Type: {chat.type})")
        
        member = await bot.get_chat_member(chat_id, me.id)
        print(f"Status in der Gruppe: {member.status}")
        
        if member.status in ['administrator', 'creator']:
            print("Berechtigungen:")
            print(f" - Einladungslinks erstellen: {member.can_invite_users}")
        else:
            print("WARNUNG: Der Bot ist KEIN Administrator in dieser Gruppe!")
            
    except TelegramError as e:
        print(f"❌ Fehler beim Zugriff auf Chat {chat_id}: {e}")

if __name__ == "__main__":
    target_id = -1002206300882
    asyncio.run(check_access(target_id))
