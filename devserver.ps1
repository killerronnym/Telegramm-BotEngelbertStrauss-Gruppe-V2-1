# Bot Dashboard Startup Script with Auto-Restart
Write-Host "Bot Dashboard wird gestartet..." -ForegroundColor Cyan

while ($true) {
    if (Test-Path ".venv\Scripts\Activate.ps1") {
        . .venv\Scripts\Activate.ps1
    }
    
    Write-Host "Starte Flask-Server auf Port 9002..." -ForegroundColor Green
    flask --app web_dashboard.app run --port 9002 --debug
    
    Write-Host "Server wurde beendet. Neustart in 5 Sekunden..." -ForegroundColor Yellow
    Start-Sleep -Seconds 5
}
