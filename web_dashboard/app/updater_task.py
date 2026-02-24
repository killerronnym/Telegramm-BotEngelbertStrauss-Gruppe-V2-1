import json
import logging
from .models import db, BotSettings
from web_dashboard.updater import Updater
import os

log = logging.getLogger(__name__)

def check_and_auto_update(app):
    with app.app_context():
        try:
            # 1. Systemeinstellungen laden
            settings = BotSettings.query.filter_by(bot_name='system').first()
            if not settings:
                # Falls keine System-Settings da sind: Default erstellen (Auto-Update AUS)
                settings = BotSettings(
                    bot_name='system',
                    config_json=json.dumps({
                        'auto_update_enabled': False,
                        'last_check_at': None
                    })
                )
                db.session.add(settings)
                db.session.commit()
            
            config = json.loads(settings.config_json)
            
            # 2. Prüfen, ob Auto-Update überhaupt aktiv ist
            if not config.get('auto_update_enabled', False):
                log.info("Auto-Update ist deaktiviert.")
                return

            # 3. Updater initialisieren (Pfade wie in api.py)
            WEB_DASHBOARD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            PROJECT_ROOT = os.path.dirname(WEB_DASHBOARD_DIR)
            VERSION_FILE = os.path.join(PROJECT_ROOT, "version.json")
            
            updater = Updater(
                repo_owner="killerronnym",
                repo_name="Telegramm-BotEngelbertStrauss-Gruppe-V2-1",
                current_version_file=VERSION_FILE,
                project_root=PROJECT_ROOT
            )

            # 4. Check auf Update
            log.info("Prüfe automatisch auf Software-Updates...")
            info = updater.check_for_update()
            
            # Zeitstempel des Checks speichern
            from datetime import datetime
            config['last_check_at'] = datetime.now().isoformat()
            settings.config_json = json.dumps(config)
            db.session.commit()

            if info.get('update_available'):
                log.info(f"Neues Update gefunden: v{info['latest_version']}. Starte automatische Installation...")
                updater.install_update(
                    info['zipball_url'], 
                    info['latest_version'], 
                    info['published_at']
                )
            else:
                log.info("Software ist auf dem neuesten Stand.")
                
        except Exception as e:
            log.error(f"Fehler im Auto-Update Task: {e}")
