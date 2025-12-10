
from dashboard.app import app
import os

if __name__ == '__main__':
    # Port dynamisch aus der Umgebungsvariable lesen, Standard ist 8080
    port = int(os.environ.get('PORT', 8080))
    
    # App starten
    app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False)
