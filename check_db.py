import sys
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Add project root to sys.path
PROJECT_ROOT = r"c:\Users\Ronny M PC\Documents\Bot T"
sys.path.append(PROJECT_ROOT)

# Load env
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")
load_dotenv(ENV_FILE)

db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("DATABASE_URL not found in .env")
    sys.exit(1)

# Pymysql-Parameter für UTF-8 sicherstellen
if "mysql" in db_url and "charset=utf8mb4" not in db_url:
    separator = "&" if "?" in db_url else "?"
    db_url += f"{separator}charset=utf8mb4"

print(f"Connecting to: {db_url.split('@')[-1] if '@' in db_url else 'SQLite/Local'}")

try:
    engine = create_engine(db_url)
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT id, telegram_user_id, content_type, file_id, text, timestamp FROM id_finder_message ORDER BY id DESC LIMIT 10")
        ).fetchall()
        
        print("\nLast 10 messages:")
        for row in result:
            print(row)
except Exception as e:
    print(f"Error: {e}")
