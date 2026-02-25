
import sqlite3
import os
import json

db_path = r'c:\Users\Ronny M PC\Documents\Bot T\instance\app.db'

def fix_schema():
    print(f"Connecting to database at {db_path}...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Add missing columns to broadcast table
    cursor.execute("PRAGMA table_info(broadcast)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'media_files' not in columns:
        print("Adding column 'media_files' to 'broadcast'...")
        cursor.execute("ALTER TABLE broadcast ADD COLUMN media_files TEXT")
    
    if 'spoiler' not in columns:
        print("Adding column 'spoiler' to 'broadcast'...")
        cursor.execute("ALTER TABLE broadcast ADD COLUMN spoiler BOOLEAN DEFAULT 0")

    # 2. Initialize id_finder settings if missing
    cursor.execute("SELECT id, config_json FROM bot_settings WHERE bot_name = 'id_finder'")
    row = cursor.fetchone()
    
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

    if not row:
        print("Initializing 'id_finder' settings...")
        cursor.execute(
            "INSERT INTO bot_settings (bot_name, config_json, is_active, updated_at) VALUES (?, ?, ?, datetime('now'))",
            ('id_finder', json.dumps(default_config), 1)
        )
    else:
        print("'id_finder' settings already exist. Updating 'is_active' to True if not already.")
        config = json.loads(row[1])
        if not config.get('is_active'):
            config['is_active'] = True
            cursor.execute(
                "UPDATE bot_settings SET config_json = ?, is_active = 1, updated_at = datetime('now') WHERE bot_name = 'id_finder'",
                (json.dumps(config),)
            )

    conn.commit()
    conn.close()
    print("Database fixes applied successfully.")

if __name__ == "__main__":
    fix_schema()
