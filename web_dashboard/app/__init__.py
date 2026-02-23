from flask import Flask, redirect, url_for
from .models import db, User # User weiterhin für db.create_all() und init_db.py
from dotenv import load_dotenv
from .config import Config
import os
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

    return app
