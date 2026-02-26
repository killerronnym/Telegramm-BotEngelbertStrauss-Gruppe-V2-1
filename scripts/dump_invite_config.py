
import os
import sys
import json
from sqlalchemy import create_engine, text

PROJECT_ROOT = r'c:\Users\Ronny M PC\Documents\Bot T'
sys.path.append(PROJECT_ROOT)

from shared_bot_utils import get_db_url

def dump_invite_config():
    engine = create_engine(get_db_url())
    with engine.connect() as conn:
        result = conn.execute(text("SELECT config_json FROM bot_settings WHERE bot_name='invite'")).fetchone()
        if result:
            config = json.loads(result[0])
            print(json.dumps(config, indent=2))
        else:
            print("No invite config found")

if __name__ == "__main__":
    dump_invite_config()
