
import os
import sys
import json
from sqlalchemy import create_engine, text, inspect

# Pfade bestimmen
PROJECT_ROOT = r'c:\Users\Ronny M PC\Documents\Bot T'
sys.path.append(PROJECT_ROOT)

from shared_bot_utils import get_db_url

def apply_fixes():
    url = get_db_url()
    print(f"Active Database URL: {url}")
    
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            # 1. Update broadcast table
            print("Checking 'broadcast' table...")
            columns = [col['name'] for col in inspect(engine).get_columns('broadcast')]
            
            if 'media_files' not in columns:
                print("Adding 'media_files' to 'broadcast'...")
                conn.execute(text("ALTER TABLE broadcast ADD COLUMN media_files TEXT"))
            
            if 'spoiler' not in columns:
                print("Adding 'spoiler' to 'broadcast'...")
                # SQLite and MySQL handle BOOLEAN/TINYINT slightly differently but this should work
                conn.execute(text("ALTER TABLE broadcast ADD COLUMN spoiler BOOLEAN DEFAULT 0"))

            # 2. Check id_finder settings
            print("Checking 'id_finder' settings...")
            result = conn.execute(
                text("SELECT config_json FROM bot_settings WHERE bot_name = 'id_finder'")
            ).fetchone()

            default_config = {
                'bot_token': os.environ.get('TELEGRAM_BOT_TOKEN', ''),
                'admin_group_id': 0,
                'main_group_id': 0,
                'admin_log_topic_id': 0,
                'delete_commands': False,
                'bot_message_cleanup_seconds': 0,
                'message_logging_enabled': True,
                'message_logging_ignore_commands': True,
                'message_logging_groups_only': False,
                'max_warnings': 3,
                'punishment_type': 'none',
                'mute_duration': 24,
                'cleanup_notification_seconds': 60,
                'warning_bot_name': 'id_finder',
                'is_active': True
            }

            if not result:
                print("Inserting 'id_finder' settings...")
                conn.execute(
                    text("INSERT INTO bot_settings (bot_name, config_json, is_active, updated_at) VALUES (:name, :config, 1, :now)"),
                    {'name': 'id_finder', 'config': json.dumps(default_config), 'now': '2026-01-01 00:00:00'} # datetime might be DB specific, using string
                )
            else:
                print("'id_finder' settings exist.")
                config = json.loads(result[0])
                if not config.get('is_active'):
                    config['is_active'] = True
                    conn.execute(
                        text("UPDATE bot_settings SET config_json = :config, is_active = 1 WHERE bot_name = 'id_finder'"),
                        {'config': json.dumps(config)}
                    )
            
            conn.commit()
            print("Fixes applied successfully.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    apply_fixes()
