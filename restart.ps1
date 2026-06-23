# restart.ps1 — free port 8000 (kill any running server) and start a fresh one.
# Usage:  ./restart.ps1      (Ctrl+C stops it; run again to restart after a prompt edit)

Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue |
    ForEach-Object {
        Write-Host ("Stopping old server (PID " + $_.OwningProcess + ")...")
        Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
    }
Start-Sleep -Milliseconds 500
Write-Host "Starting server on http://127.0.0.1:8000 ..."
python -m uvicorn antenna_reader.web:app --port 8000
