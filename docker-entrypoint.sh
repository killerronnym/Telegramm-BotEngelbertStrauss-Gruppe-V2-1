#!/bin/bash
# Updated: 2026-02-26 21:22

set -e

echo "--- Starting Bot Engine v2 Entrypoint ---"

# Navigieren zum App-Verzeichnis
cd /app

# Prüfen auf neue Abhängigkeiten
if [ -f "requirements.txt" ]; then
    echo "Checking for dependency updates..."
    pip install --no-cache-dir -r requirements.txt
fi

# Datenbank-Migrationen oder andere Vorbereitungen könnten hier stehen
# python manage.py db upgrade

echo "Starting Gunicorn Flask server and Master-Bot..."
# Wir stellen sicher, dass die Datenbank bereit ist (Create All)
python -c "
from web_dashboard.app import create_app, db
app=create_app()
with app.app_context():
    db.create_all()
"

# Master-Bot im Hintergrund starten
echo "Launching Master-Bot in background..."
python bots/main_bot.py &
BOT_PID=$!
mkdir -p logs
echo $BOT_PID > logs/main_bot.pid

# Dashboard im Vordergrund (bindet an Port 9003)
echo "Launching Gunicorn on port 9003..."
gunicorn --bind 0.0.0.0:9003 --workers 2 --timeout 120 --access-logfile - --error-logfile - "web_dashboard.app:create_app()" &
WEB_PID=$!

# Trap: Wenn der Container gestoppt wird, beenden wir beide Prozesse sauber
cleanup() {
    echo "Stopping processes..."
    kill $BOT_PID $WEB_PID 2>/dev/null || true
    exit 0
}
trap cleanup SIGINT SIGTERM

# WICHTIG: Wir warten NUR auf Gunicorn ($WEB_PID).
# Falls der Bot stirbt (z.B. wegen fehlendem Token), bleibt der Webserver am Leben,
# damit der User im Installer / Dashboard alles konfigurieren kann.
echo "Monitoring Gunicorn (PID: $WEB_PID)..."
wait $WEB_PID

# Falls Gunicorn stoppt, reißen wir den Bot mit in den Abgrund und beenden den Container
kill $BOT_PID 2>/dev/null || true
exit 1
