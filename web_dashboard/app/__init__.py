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
    
    template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src'))
    
    app = Flask(__name__, instance_relative_config=True, template_folder=template_dir)
    
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
        return User.query.get(int(user_id))
    
    app.jinja_env.filters['datetimeformat'] = datetimeformat
    
    # Blueprints registrieren
    from .routes import dashboard, auth, api, install
    app.register_blueprint(auth.bp)
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(api.bp)
    app.register_blueprint(install.bp)
    
    # Check for installation
    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    INSTANCE_DIR = os.path.join(PROJECT_ROOT, 'instance')
    INSTALL_LOCK = os.path.join(INSTANCE_DIR, 'installed.lock')

    @app.before_request
    def check_for_install():
        if os.path.exists(INSTALL_LOCK):
            return
        # Allow access to install blueprint and static files
        if request.blueprint == 'install' or request.endpoint == 'static' or request.path.startswith('/static/'):
            return
        return redirect(url_for('install.index'))

    with app.app_context():
        try:
            db.create_all()
            # Initialer Admin nur erstellen, wenn wir nicht im Setup-Modus sind oder explizit gewünscht
            # In der neuen Version übernimmt der Installer das
            if os.path.exists(INSTALL_LOCK):
                if not User.query.filter_by(username='admin').first():
                    admin = User(username='admin', role='admin')
                    admin.set_password('admin') 
                    db.session.add(admin)
                    db.session.commit()
        except Exception as e:
            print(f"DB Error during app context: {e}")

    # Root-Route leitet direkt zum Dashboard weiter
    @app.route('/')
    def root():
        return redirect(url_for('dashboard.index'))

    # Scheduler initialisieren
    scheduler = APScheduler()
    scheduler.init_app(app)
    scheduler.start()
    
    # Auto-Update Job registrieren (läuft alle 6 Stunden)
    from .updater_task import check_and_auto_update
    scheduler.add_job(id='auto_update_job', func=check_and_auto_update, trigger='interval', hours=6, args=[app])

    # --- MASTER-BOT AUTO-START (Nach Update/Container-Restart) ---
    # Recursion Guard: Do not auto-start if we are already inside a bot process
    if not os.environ.get("BOT_PROCESS"):
        with app.app_context():
            from web_dashboard.app.models import BotSettings
            from web_dashboard.app.routes.dashboard import manage_master_bot_logic
            
            # Wir prüfen, ob der ID-Finder (Master) als aktiv markiert ist
            s = BotSettings.query.filter_by(bot_name='id_finder').first()
            if s:
                try:
                    c = json.loads(s.config_json)
                    if c.get('is_active'):
                        # Wir rufen die Start-Logik auf. Diese prüft intern bereits, 
                        # ob der Prozess evtl. schon läuft (via PID-File).
                        print("Master-Bot Auto-Start wird ausgelöst...")
                        manage_master_bot_logic('start', is_auto_start=True)
                except Exception as e:
                    print(f"Fehler beim Master-Bot Auto-Start: {e}")

    return app
