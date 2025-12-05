#!/bin/sh
source .venv/bin/activate
export FLASK_APP=app
export FLASK_DEBUG=1
# Setzt PORT auf 8080, falls es nicht bereits gesetzt ist
PORT=${PORT:-8080}
python -m flask run --port $PORT
