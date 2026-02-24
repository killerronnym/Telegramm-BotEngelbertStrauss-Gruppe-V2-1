from flask import Flask, redirect, url_for
from .models import db, User 
from flask_login import LoginManager
from dotenv import load_dotenv
from .config import Config
from flask_apscheduler import APScheduler
import os
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
    from .routes import dashboard, auth, api
    app.register_blueprint(auth.bp)
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(api.bp)
    
    with app.app_context():
        try:
            db.create_all()
            # Initialen Admin erstellen, falls nicht vorhanden (für neue Installationen)
            if not User.query.filter_by(username='admin').first():
                admin = User(username='admin', role='admin')
                admin.set_password('admin') # Standardpasswort "admin"
                db.session.add(admin)
                db.session.commit()
                print("Initialer Admin-Account 'admin' / 'admin' erstellt.")
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

    return app
