#!/bin/bash
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
python -c "from web_dashboard.app import create_app, db; app=create_app(); with app.app_context(): db.create_all()"

# Master-Bot im Hintergrund starten
python bots/main_bot.py &
BOT_PID=$!

# Dashboard im Vordergrund (exec ersetzt die Shell, also brauchen wir hier KEIN exec wenn wir PIDs managen wollen)
# Aber wir können gunicorn starten und per trap auf Signale reagieren.
# Alternativ: Gunicorn im Hintergrund und wait.
gunicorn --bind 0.0.0.0:9003 --workers 2 --timeout 120 --access-logfile - --error-logfile - "web_dashboard.app:create_app()" &
WEB_PID=$!

# Trap für sauberes Beenden beider Prozesse
trap "kill $BOT_PID $WEB_PID; exit 0" SIGINT SIGTERM

# Warten auf einen der Prozesse
wait -n

# Wenn einer stirbt, beenden wir den anderen auch (damit Docker den Container neu startet)
kill $BOT_PID $WEB_PID 2>/dev/null
exit 1
