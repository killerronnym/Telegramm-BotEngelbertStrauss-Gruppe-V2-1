
import os
import sys
import json
from sqlalchemy import create_engine, text

PROJECT_ROOT = r'c:\Users\Ronny M PC\Documents\Bot T'
sys.path.append(PROJECT_ROOT)

from shared_bot_utils import get_db_url

def fix_tiktok_settings():
    url = get_db_url()
    # print(f"Active Database URL: {url}") # avoid encoding error
    
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT config_json FROM bot_settings WHERE bot_name = 'tiktok'")).fetchone()
            
            if result:
                config = json.loads(result[0])
                
                # Update with correct values
                # main_chat_id from invite: -1003159560874
                # topic_id from invite: 3807
                config['telegram_chat_id'] = "-1003159560874"
                config['telegram_topic_id'] = "3807"
                
                conn.execute(
                    text("UPDATE bot_settings SET config_json = :config WHERE bot_name = 'tiktok'"),
                    {'config': json.dumps(config)}
                )
                conn.commit()
                print("TikTok settings updated successfully.")
            else:
                print("TikTok settings not found in database.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fix_tiktok_settings()
