from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json

db = SQLAlchemy()

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255))
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
    media_path = db.Column(db.String(255))  # legacy single-file
    media_type = db.Column(db.String(20))   # image, video
    media_files = db.Column(db.Text)        # JSON list of paths for multi-image
    spoiler = db.Column(db.Boolean, default=False)
    scheduled_at = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='pending')  # pending, sent, failed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    pin_message = db.Column(db.Boolean, default=False)
    silent_send = db.Column(db.Boolean, default=False)

class TopicMapping(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    topic_id = db.Column(db.BigInteger, unique=True, nullable=False)
    topic_name = db.Column(db.String(100), nullable=False)

# --- Auto-Responder Models ---
class AutoReplyRule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    trigger_type = db.Column(db.String(20), nullable=False) # 'command' or 'keyword'
    trigger_text = db.Column(db.String(255), nullable=False)
    response_text = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    avatar_file_id = db.Column(db.String(255))
    first_contact = db.Column(db.DateTime, default=datetime.utcnow)
    last_contact = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship to messages
    messages = db.relationship('IDFinderMessage', backref='user', lazy=True, cascade="all, delete-orphan")
    # Relationship to warnings
    warnings = db.relationship('IDFinderWarning', backref='user', lazy=True, cascade="all, delete-orphan")

class IDFinderMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    telegram_user_id = db.Column(db.BigInteger, db.ForeignKey('id_finder_user.telegram_id'), nullable=False)
    message_id = db.Column(db.BigInteger)
    chat_id = db.Column(db.BigInteger)
    message_thread_id = db.Column(db.BigInteger)
    chat_type = db.Column(db.String(50)) # private, group, supergroup, channel
    text = db.Column(db.Text)
    content_type = db.Column(db.String(50), default='text') # text, photo, video, etc.
    file_id = db.Column(db.String(255))
    is_command = db.Column(db.Boolean, default=False)
    is_deleted = db.Column(db.Boolean, default=False)
    deletion_reason = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class IDFinderWarning(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    telegram_user_id = db.Column(db.BigInteger, db.ForeignKey('id_finder_user.telegram_id'), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    admin_id = db.Column(db.BigInteger)
    message_db_id = db.Column(db.Integer, db.ForeignKey('id_finder_message.id'))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class AutoCleanupTask(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.BigInteger, nullable=False)
    message_id = db.Column(db.BigInteger, nullable=False)
    cleanup_at = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='pending') # pending, done

# --- Birthday Bot Models ---
class Birthday(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    telegram_user_id = db.Column(db.BigInteger, unique=True, nullable=False)
    chat_id = db.Column(db.BigInteger) # The group where it was registered
    username = db.Column(db.String(100))
    first_name = db.Column(db.String(100))
    day = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# --- Invite Bot Models ---

class InviteApplication(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    telegram_user_id = db.Column(db.BigInteger, unique=True, nullable=False)
    username = db.Column(db.String(100))
    full_name = db.Column(db.String(100))
    answers_json = db.Column(db.Text, default='{}')
    status = db.Column(db.String(20), default='pending') # pending, accepted, rejected, completed
    message_ids_json = db.Column(db.Text, default='[]') # Optional: um gesendete Bewerbungs-Nachrichten später editieren zu können
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def answers(self):
        try: return json.loads(self.answers_json)
        except: return {}

    @answers.setter
    def answers(self, value):
        self.answers_json = json.dumps(value)

class InviteLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    telegram_user_id = db.Column(db.BigInteger, nullable=False)
    username = db.Column(db.String(100))
    action = db.Column(db.String(255), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# --- Admin Permissions Definition ---
AVAILABLE_PERMISSIONS = {
    "Moderation": {
        "can_warn": "Nutzer verwarnen",
        "can_mute": "Nutzer stummschalten",
        "can_kick": "Nutzer kicken",
        "can_ban": "Nutzer bannen",
        "can_delete": "Nachrichten löschen"
    },
    "Management": {
        "can_broadcast": "Broadcasts senden",
        "can_manage_topics": "Topics verwalten",
        "can_view_logs": "Logs einsehen"
    },
    "System": {
        "is_superadmin": "Vollzugriff (Superadmin)",
        "can_manage_admins": "Andere Admins verwalten"
    }
}

# --- Profanity Filter Models ---
class ProfanityWord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    word = db.Column(db.String(100), unique=True, nullable=False)
    language = db.Column(db.String(10), default='custom') # 'de', 'en', 'custom'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

