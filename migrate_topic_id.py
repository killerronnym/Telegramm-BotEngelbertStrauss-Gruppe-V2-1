import os
import sys
from sqlalchemy import create_engine, text

# Add parent dir to path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.append(PROJECT_ROOT)

from shared_bot_utils import get_db_url

def migrate():
    url = get_db_url()
    print(f"Connecting to: {url}")
    engine = create_engine(url)
    
    with engine.connect() as conn:
        print("Checking for topic_id column in birthday table...")
        try:
            # Versuche Spalte hinzuzufügen
            conn.execute(text("ALTER TABLE birthday ADD COLUMN topic_id BIGINT"))
            conn.commit()
            print("Successfully added topic_id column.")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print("Column topic_id already exists.")
            else:
                print(f"Error: {e}")

if __name__ == "__main__":
    migrate()
