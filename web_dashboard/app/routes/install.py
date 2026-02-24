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
        db_url = f"sqlite:///{os.path.join(PROJECT_ROOT, 'instance', 'app.db')}"
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
    admin_user = data.get('admin_user')
    admin_pass = data.get('admin_pass')

    try:
        # Update .env file
        env_path = os.path.join(PROJECT_ROOT, '.env')
        with open(env_path, 'a') as f:
            f.write(f"\nDATABASE_URL={db_url}\n")
        
        # Reload env and re-init DB
        os.environ['DATABASE_URL'] = db_url
        
        with current_app.app_context():
            db.create_all()
            if not User.query.filter_by(username=admin_user).first():
                admin = User(username=admin_user, role='admin')
                admin.set_password(admin_pass)
                db.session.add(admin)
                db.session.commit()

        # Create lock file
        os.makedirs(os.path.dirname(INSTALL_LOCK), exist_ok=True)
        with open(INSTALL_LOCK, 'w') as f:
            f.write(f"Installed on {os.uname() if hasattr(os, 'uname') else 'Windows'}")

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
