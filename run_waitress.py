import os
import sys
from waitress import serve

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from web_dashboard.app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 9002))
    print(f"🚀 Dashboard wird professionell gehostet auf http://localhost:{port}")
    print("Nutze Strg+C zum Beenden.")
    serve(app, host='0.0.0.0', port=port, threads=4)
