
import os
import sys
import json
from sqlalchemy import create_engine, text

PROJECT_ROOT = r'c:\Users\Ronny M PC\Documents\Bot T'
sys.path.append(PROJECT_ROOT)

from shared_bot_utils import get_db_url

def dump():
    url = get_db_url()
    print(f"Active Database URL: {url}")
    
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT bot_name, config_json FROM bot_settings"))
            for row in result:
                print(f"--- {row[0]} ---")
                print(row[1])
                print()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    dump()
