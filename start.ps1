# Starts the API (port 8000) and the React dev server (port 5173) in their own windows.
# First run: create the venv and install packages (see README).
$root = $PSScriptRoot
Start-Process powershell -ArgumentList '-NoExit', '-Command', "cd '$root\backend'; `$env:SECRET_KEY='dev-only-local-key'; .venv\Scripts\python.exe -m uvicorn app.main:app --reload"
Start-Process powershell -ArgumentList '-NoExit', '-Command', "cd '$root\frontend'; npm run dev"
Write-Host 'API: http://localhost:8000/docs   App: http://localhost:5173'
