
import os
import sys
import json
from flask import Flask

# Pfade bestimmen
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from web_dashboard.app import create_app
from web_dashboard.app.models import db, BotSettings

def diagnose():
    app = create_app()
    with app.app_context():
        try:
            print("--- Testing Database ---")
            s = BotSettings.query.filter_by(bot_name='invite').first()
            if s:
                print(f"Invite Bot Settings found. JSON length: {len(s.config_json)}")
                cfg = json.loads(s.config_json)
                print(f"JSON parsed successfully. Keys: {list(cfg.keys())}")
            else:
                print("Invite Bot Settings NOT found in DB!")
            
            print("\n--- Testing Template Rendering ---")
            from flask import render_template
            # Dummy context
            ctx = {
                'config': cfg if 'cfg' in locals() else {},
                'is_invite_running': False,
                'user_interaction_logs': [],
                'invite_bot_logs': []
            }
            try:
                # We need a request context for url_for to work
                with app.test_request_context():
                    html = render_template("bot_settings.html", **ctx)
                    print(f"Template rendered successfully! (Length: {len(html)})")
            except Exception as e:
                print(f"TEMPLATE ERROR: {e}")
                import traceback
                traceback.print_exc()
                
        except Exception as e:
            print(f"GENERAL ERROR: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    diagnose()
