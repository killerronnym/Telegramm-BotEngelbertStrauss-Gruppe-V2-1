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

# Wir stellen sicher, dass alle notwendigen Ordner existieren und beschreibbar sind
mkdir -p bots logs instance data web_dashboard/app/static/uploads

# Berechtigungen setzen (wichtig für den Updater im Container)
echo "Setting permissions for data directories..."
chmod -R 777 logs instance data

echo "Starting Gunicorn Flask server..."
# Wir stellen sicher, dass die Datenbank bereit ist (Create All)
python -c "from web_dashboard.app import create_app, db; app=create_app(); with app.app_context(): db.create_all()"

# Gunicorn mit --preload starten, damit Signale zuverlässiger an den Master gehen
exec gunicorn --bind 0.0.0.0:9002 --workers 2 --timeout 120 --access-logfile - --error-logfile - "web_dashboard.app:create_app()"
