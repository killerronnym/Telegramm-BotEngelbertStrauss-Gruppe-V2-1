from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(20), default='user')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class BotSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bot_name = db.Column(db.String(50), unique=True, nullable=False)
    config_json = db.Column(db.Text, nullable=False)  # JSON-String speichern
    is_active = db.Column(db.Boolean, default=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Broadcast(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text)
    topic_id = db.Column(db.String(50)) 
    send_mode = db.Column(db.String(20), default='standard')
    media_path = db.Column(db.String(255))
    media_type = db.Column(db.String(20)) # image, video
    scheduled_at = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='pending') # pending, sent, failed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    pin_message = db.Column(db.Boolean, default=False)
    silent_send = db.Column(db.Boolean, default=False)

class TopicMapping(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    topic_id = db.Column(db.BigInteger, unique=True, nullable=False)
    topic_name = db.Column(db.String(100), nullable=False)

# --- ID Finder Bot Models ---

class IDFinderAdmin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.BigInteger, unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    permissions_json = db.Column(db.Text, default='{}') # JSON string of permissions
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def permissions(self):
        try:
            return json.loads(self.permissions_json)
        except:
            return {}

    @permissions.setter
    def permissions(self, value):
        self.permissions_json = json.dumps(value)

class IDFinderUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.BigInteger, unique=True, nullable=False)
    username = db.Column(db.String(100))
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    language_code = db.Column(db.String(10))
    is_bot = db.Column(db.Boolean, default=False)
    avatar_file_id = db.Column(db.String(255)) # Added for avatar support
    first_contact = db.Column(db.DateTime, default=datetime.utcnow)
    last_contact = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship to messages
    messages = db.relationship('IDFinderMessage', backref='user', lazy=True, cascade="all, delete-orphan")

class IDFinderMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    telegram_user_id = db.Column(db.BigInteger, db.ForeignKey('id_finder_user.telegram_id'), nullable=False)
    message_id = db.Column(db.BigInteger)
    chat_id = db.Column(db.BigInteger)
    message_thread_id = db.Column(db.BigInteger)
    chat_type = db.Column(db.String(50)) # private, group, supergroup, channel
    text = db.Column(db.Text)
    content_type = db.Column(db.String(50), default='text') # text, photo, video, etc.
    file_id = db.Column(db.String(255)) # Added for media support
    is_command = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
