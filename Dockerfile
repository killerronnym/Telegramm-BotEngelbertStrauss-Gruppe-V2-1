FROM python:3.11-slim

WORKDIR /app

# Systemabhängigkeiten installieren (falls nötig, z.B. für gcc)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Requirements kopieren und installieren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Den gesamten Projektcode kopieren
COPY . .

# Ausführrechte für Skripte setzen
RUN chmod +x scripts/setup.sh scripts/init_db.py

# Port für das Dashboard freigeben
EXPOSE 5000

# Startbefehl (wird später durch entrypoint.sh ersetzt/ergänzt)
CMD ["python", "web_dashboard/app.py"]
