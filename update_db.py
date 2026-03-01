from web_dashboard.app import create_app, db
from sqlalchemy import text
import sys

def upgrade_database():
    app = create_app()
    with app.app_context():
        try:
            # Versuche, die Spalte "year" zur Tabelle "birthday" hinzuzufügen
            db.session.execute(text('ALTER TABLE birthday ADD COLUMN year INTEGER'))
            db.session.commit()
            print("Erfolgreich: Die Spalte 'year' wurde zur Tabelle 'birthday' hinzugefügt.")
        except Exception as e:
            error_str = str(e).lower()
            if "duplicate column" in error_str or "already exist" in error_str:
                print("Hinweis: Die Spalte 'year' existiert bereits in der Tabelle 'birthday'.")
            else:
                db.session.rollback()
                print(f"Ein Fehler ist aufgetreten: {e}")
                sys.exit(1)

if __name__ == '__main__':
    upgrade_database()
