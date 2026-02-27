import os
import sys

# Navigation to root
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from web_dashboard.app import create_app, db
from shared_bot_utils import get_db_url

def upgrade_db():
    print("Starte DB Upgrade für Auto-Responder...")
    app = create_app({'SQLALCHEMY_DATABASE_URI': get_db_url()})
    
    with app.app_context():
        try:
            print(f"Connecting to database: {get_db_url()}")
            db.create_all()
            print("Erfolgreich: Alle Tabellen (inklusive AutoReplyRule) wurden erstellt/geprüft.")
        except Exception as e:
            print(f"Fehler beim DB Upgrade: {e}")

if __name__ == '__main__':
    upgrade_db()
