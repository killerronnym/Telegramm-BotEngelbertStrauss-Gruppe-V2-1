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
        # INITIALISIERUNG NUR WENN INSTALLIERT
        # Andernfalls stürzt die App beim Start mit SQLAlchemy-Fehlern ab,
        # wenn in der .env noch eine fehlerhafte oder alte Datenbank steht.
        if os.path.exists(INSTALL_LOCK):
            try:
                db.create_all()
                if not User.query.filter_by(username='admin').first():
                    admin = User(username='admin', role='admin')
                    admin.set_password('admin') 
                    db.session.add(admin)
                    db.session.commit()
            except Exception as e:
                print(f"CRITICAL DB Error during app context: {e}")
                print("Database appears unreachable. Entering Rescue Mode by deleting INSTALL_LOCK...")
                try:
                    os.remove(INSTALL_LOCK)
                except:
                    pass

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

    return app
