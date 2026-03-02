from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, current_app
from ..models import db, User
import os
import json
from sqlalchemy import text
from ..config import Config
from urllib.parse import quote_plus

bp = Blueprint('install', __name__, url_prefix='/install')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
INSTALL_LOCK = os.path.join(PROJECT_ROOT, 'instance', 'installed.lock')

@bp.route('/')
def index():
    if os.path.exists(INSTALL_LOCK):
        return redirect(url_for('dashboard.index'))
    return render_template('install.html')

@bp.route('/check-db', methods=['POST'])
def check_db():
    data = request.json
    db_type = data.get('db_type')
    
    if db_type == 'sqlite':
        from shared_bot_utils import DB_PATH
        db_url = f"sqlite:///{DB_PATH}"
    else:
        host = data.get('host')
        port = data.get('port')
        user = quote_plus(data.get('user', ''))
        password = quote_plus(data.get('password', ''))
        dbname = data.get('dbname')
        db_url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{dbname}?charset=utf8mb4"

    try:
        from sqlalchemy import create_engine
        engine = create_engine(db_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return jsonify({"success": True, "db_url": db_url})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@bp.route('/setup', methods=['POST'])
def setup():
    if os.path.exists(INSTALL_LOCK):
        return jsonify({"success": False, "error": "Already installed"})

    data = request.json
    db_url = data.get('db_url')
    db_type = data.get('db_type')
    admin_user = data.get('admin_user')
    admin_pass = data.get('admin_pass')

    if db_type == 'sqlite':
        from shared_bot_utils import DB_PATH
        db_url = f"sqlite:///{DB_PATH}"

    try:
        # Update .env file
        env_path = os.path.join(PROJECT_ROOT, '.env')
        lines = []
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                lines = f.readlines()
        
        # Bestehende DATABASE_URL entfernen und neu hinzufügen
        new_lines = [l for l in lines if not l.startswith("DATABASE_URL=")]
        if not any(l.strip() == "" for l in new_lines[-1:]): # Neue Zeile falls nötig
             new_lines.append("\n")
        new_lines.append(f"DATABASE_URL={db_url}\n")
        
        with open(env_path, 'w') as f:
            f.writelines(new_lines)
        
        # Initialize tables using a direct SQLAlchemy engine to avoid Flask-SQLAlchemy using the old cached .env engine
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        engine = create_engine(db_url)
        db.metadata.create_all(engine)
        
        Session = sessionmaker(bind=engine)
        session = Session()
        
        if not session.query(User).filter_by(username=admin_user).first():
            admin = User(username=admin_user, role='admin')
            admin.set_password(admin_pass)
            session.add(admin)
            session.commit()
        
        session.close()

        # Create lock file
        os.makedirs(os.path.dirname(INSTALL_LOCK), exist_ok=True)
        with open(INSTALL_LOCK, 'w') as f:
            f.write(f"Installed on {os.uname() if hasattr(os, 'uname') else 'Windows'}")

        # Restart Container logic (Triggered with slight delay so the UI gets a success response)
        # Senden eines Signals an den Gunicorn-Hauptprozess (PPID) oder den eigenen Prozess (PID)
        # Dadurch beendet sich das Script und Docker startet den Container (`restart unless-stopped`) neu
        import threading
        import time
        import signal
        def restart_server():
            time.sleep(2)
            print("Setup Complete! Triggering container restart...")
            # Versuche, Gunicorn (Parent Process) zu beenden
            try:
                os.kill(os.getppid(), signal.SIGTERM)
            except:
                pass
            # Fallback: Sich selbst beenden
            os.kill(os.getpid(), signal.SIGTERM)
            
        threading.Thread(target=restart_server, daemon=True).start()

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
@bp.route('/restore', methods=['POST'])
def restore():
    if os.path.exists(INSTALL_LOCK):
        return jsonify({"success": False, "error": "Bereits installiert"})

    if 'backup_file' not in request.files:
        return jsonify({"success": False, "error": "Keine Datei hochgeladen"}), 400
        
    file = request.files['backup_file']
    if file.filename == '':
        return jsonify({"success": False, "error": "Keine Datei ausgewählt"}), 400
        
    from shared_bot_utils import DB_PATH
    
    try:
        # Ordner für DB sicherstellen
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        
        # Direkt speichern (Installer Pfad ist sicher da noch nichts läuft)
        file.save(DB_PATH)
        
        # Validierung
        with open(DB_PATH, 'rb') as f:
            header = f.read(16)
            if header != b'SQLite format 3\x00':
                return jsonify({"success": False, "error": "Ungültige SQLite Datei"}), 400

        # Lock-File erstellen
        os.makedirs(os.path.dirname(INSTALL_LOCK), exist_ok=True)
        with open(INSTALL_LOCK, 'w') as f:
            f.write(f"Restored from backup on {os.uname() if hasattr(os, 'uname') else 'Windows'}")

        # Restart
        import threading
        import time
        import signal
        def restart_server():
            time.sleep(2)
            os.kill(os.getpid(), signal.SIGTERM)
            
        threading.Thread(target=restart_server, daemon=True).start()

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
