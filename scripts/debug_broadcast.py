
from web_dashboard.app.models import db, BotSettings, Broadcast
from flask import Flask
import json
import os

app = Flask(__name__)
# Absolute path to the database
db_path = r'c:\Users\Ronny M PC\Documents\Bot T\instance\app.db'
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

with app.app_context():
    print("--- ID Finder Bot Settings ---")
    s = BotSettings.query.filter_by(bot_name='id_finder').first()
    if s:
        print(f"Config: {s.config_json}")
        config = json.loads(s.config_json)
        print(f"Is active (from config): {config.get('is_active')}")
    else:
        print("No settings found for id_finder")

    print("\n--- Pending Broadcasts ---")
    pending = Broadcast.query.filter_by(status='pending').all()
    print(f"Found {len(pending)} pending broadcasts")
    for b in pending:
        print(f"ID: {b.id}, Scheduled: {b.scheduled_at}, Topic: {b.topic_id}")

    print("\n--- Broadcast status counts ---")
    from sqlalchemy import func
    counts = db.session.query(Broadcast.status, func.count(Broadcast.id)).group_by(Broadcast.status).all()
    for status, count in counts:
        print(f"{status}: {count}")
