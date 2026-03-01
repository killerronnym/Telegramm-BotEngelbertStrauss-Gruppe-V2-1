import sqlite3
import json
import os

db_path = 'instance/app.db'
if not os.path.exists(db_path):
    print(f"ERROR: {db_path} not found")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute('SELECT config_json FROM bot_settings WHERE bot_name = "id_finder"')
row = cursor.fetchone()

if row:
    print("--- ID FINDER CONFIG ---")
    print(row[0])
    try:
        cfg = json.loads(row[0])
        token = cfg.get('bot_token')
        if token:
            print(f"TOKEN FOUND: {token[:5]}...{token[-5:]}")
        else:
            print("TOKEN IS EMPTY OR MISSING IN JSON")
    except Exception as e:
        print(f"JSON ERROR: {e}")
else:
    print("ID_FINDER NOT FOUND IN DB")

conn.close()
