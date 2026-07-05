# Start ReceptApp (backend + frontend)
# Run from C:\ReceptApp

$ErrorActionPreference = 'Stop'

Write-Host "Starting backend..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", `
  "cd C:\ReceptApp\backend; `$env:ANTHROPIC_API_KEY='YOUR_KEY_HERE'; .\venv\Scripts\uvicorn main:app --host 0.0.0.0 --port 8000 --reload"

Start-Sleep 2

Write-Host "Starting frontend..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", `
  "cd C:\ReceptApp\frontend; npm run dev"

Write-Host "App running at http://localhost:3001" -ForegroundColor Cyan
