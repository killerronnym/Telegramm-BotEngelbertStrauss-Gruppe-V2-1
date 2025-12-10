
from dashboard.app import app, initialize_users, start_background_processes, shutdown_background_processes
import atexit
import os

if __name__ == '__main__':
    # Sicherstellen, dass Hintergrundprozesse beim Beenden gestoppt werden
    atexit.register(shutdown_background_processes)
    
    # Initialisierung durchführen
    initialize_users()
    start_background_processes()
    
    # Port dynamisch aus der Umgebungsvariable lesen, Standard ist 8080
    port = int(os.environ.get('PORT', 8080))
    
    # App starten
    app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False)
