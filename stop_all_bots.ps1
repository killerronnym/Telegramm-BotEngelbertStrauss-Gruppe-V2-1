# Stop all running bots via PID files
$pidFolder = Join-Path $PSScriptRoot "logs"
$pidFiles = Get-ChildItem $pidFolder -Filter "*.pid" | Where-Object { $_.Name -ne "web_server.pid" }

foreach ($pf in $pidFiles) {
    $rawPid = (Get-Content $pf.FullName -ErrorAction SilentlyContinue).Trim()
    if ($rawPid) {
        Write-Host "Stopping $($pf.Name): PID $rawPid"
        taskkill /F /T /PID $rawPid 2>$null
        Remove-Item $pf.FullName -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "Alle Bots gestoppt."
