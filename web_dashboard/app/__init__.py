from flask import Flask, redirect, url_for, request
from .models import db, User 
from flask_login import LoginManager
from dotenv import load_dotenv
from .config import Config
from flask_apscheduler import APScheduler
import os
import json
import logging
from .utils import datetimeformat

def create_app(test_config=None):
    load_dotenv()
    
    app = Flask(__name__, instance_relative_config=True)
    
    if test_config:
        app.config.from_mapping(test_config)
    else:
        app.config.from_object(Config)

    db.init_app(app)
    
    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(User, int(user_id))
        except Exception as e:
            print(f"Error loading user from DB: {e}")
            return None
    
    app.jinja_env.filters['datetimeformat'] = datetimeformat
    
    # Blueprints registrieren
    from .routes import dashboard, auth, api, install, sync
    app.register_blueprint(auth.bp)
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(api.bp)
    app.register_blueprint(install.bp)
    app.register_blueprint(sync.bp)
    
    @app.context_processor
    def inject_sync_state():
        try:
            from .live_bot import get_sync_state
            import time
            state = get_sync_state()
            trial_remaining_hours = 0
            if state.get('mode') == 'TRIAL':
                expiry = state.get('trial_expiry', 0)
                now = int(time.time())
                if expiry > now:
                    trial_remaining_hours = int((expiry - now) / 3600)
            return dict(sync_state=state, trial_remaining_hours=trial_remaining_hours)
        except Exception:
            return dict(sync_state={}, trial_remaining_hours=0)
            
    # Check for installation
    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    INSTANCE_DIR = os.path.join(PROJECT_ROOT, 'instance')
    INSTALL_LOCK = os.path.join(INSTANCE_DIR, 'installed.lock')

    @app.before_request
    def check_for_install():
        from .live_bot import is_halted, get_sync_state, activate_live_sync, push_heartbeat
        from flask import render_template, request, redirect, session
        
        # 1. Lock Screen check (System wurde gesperrt)
        if is_halted():
            if request.endpoint and (request.endpoint.startswith('static.') or request.endpoint == 'sync.activate_web'):
                return
                
            error_msg = session.pop('activation_error', None)
            return render_template('system_error.html', error_msg=error_msg), 403
            
        # 2. Setup check
        import os
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        INSTALL_LOCK = os.path.join(project_root, 'instance', 'installed.lock')
        if not os.path.exists(INSTALL_LOCK):
            # Only allow access to setup endpoints
            allowed_endpoints = ['install.index', 'install.setup', 'install.test_token', 'install.get_group_id', 'install.check_db']
            allowed_endpoints += ['install.restore', 'install.validate_backup']
            allowed_endpoints += ['install.track_interaction']
            if request.endpoint and request.endpoint not in allowed_endpoints and not request.endpoint.startswith('static.'):
                return redirect(url_for('install.index'))

    with app.app_context():
        # INITIALISIERUNG NUR WENN INSTALLIERT
        # Andernfalls stürzt die App beim Start mit SQLAlchemy-Fehlern ab,
        # wenn in der .env noch eine fehlerhafte oder alte Datenbank steht.
        if os.path.exists(INSTALL_LOCK):
            try:
                db.create_all()
                # Migration: Neue Spalten hinzufügen falls nicht vorhanden
                # (db.create_all() erstellt nur neue Tabellen, keine neuen Spalten!)
                try:
                    db.session.execute(db.text("ALTER TABLE invite_application ADD COLUMN profile_message_id BIGINT"))
                    db.session.commit()
                    print("Migration: profile_message_id hinzugefügt.")
                except Exception:
                    db.session.rollback()  # Spalte existiert bereits
                try:
                    db.session.execute(db.text("ALTER TABLE invite_application ADD COLUMN profile_chat_id BIGINT"))
                    db.session.commit()
                    print("Migration: profile_chat_id hinzugefügt.")
                except Exception:
                    db.session.rollback()  # Spalte existiert bereits
                if not User.query.filter_by(username='admin').first():
                    admin = User(username='admin', role='admin')
                    admin.set_password('admin') 
                    db.session.add(admin)
                    db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"CRITICAL DB Error during app context: {e}")
                print("Database appears unreachable. Please check your DB credentials or server status.")
                # REMOVED: Automatic deletion of INSTALL_LOCK. 
                # This is a security risk as it opens the setup page to anyone.

    # Root-Route leitet direkt zum Dashboard weiter
    @app.route('/')
    def root():
        return redirect(url_for('dashboard.index'))

    # Scheduler initialisieren (nur wenn installiert, sonst crasht er wegen fehlender DB!)
    if os.path.exists(INSTALL_LOCK):
        scheduler = APScheduler()
        scheduler.init_app(app)
        scheduler.start()
        
        # Auto-Update Job registrieren (läuft alle 6 Stunden)
        from .updater_task import check_and_auto_update
        scheduler.add_job(id='auto_update_job', func=check_and_auto_update, trigger='interval', hours=6, args=[app])

    # Start the Live Bot polling thread
    import threading
    def run_sync_loop():
        import time
        from .live_bot import run_background_sync
        time.sleep(5) # Give the server time to start
        while True:
            try:
                run_background_sync()
            except Exception as e:
                print(f"Background Sync Error: {e}")
            time.sleep(10) # Poll every 10 seconds

    threading.Thread(target=run_sync_loop, daemon=True).start()

    return app
