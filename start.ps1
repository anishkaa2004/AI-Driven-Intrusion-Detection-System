# Start AI-IDS (backend + dashboard) on Windows with one command.
#
#   .\start.ps1            start backend and dashboard
#   .\start.ps1 -Demo      also replay demo attack traffic every 30 s
#   .\start.ps1 -Agent     also run the monitoring agent (device must be enrolled first)
#
# Press Ctrl+C to stop everything. Logs are written to .\logs\.
# If PowerShell refuses to run scripts, run once:
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
param(
    [switch]$Demo,
    [switch]$Agent
)
# Native tools (python, npm) report failures via exit codes, checked explicitly below.
$ErrorActionPreference = "Continue"

$Root = $PSScriptRoot
Set-Location $Root
$Py = Join-Path $Root ".venv\Scripts\python.exe"
$Logs = Join-Path $Root "logs"
$BackendPort = 8000
$FrontendPort = 5173

function Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Warn($msg) { Write-Host "!!  $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "xx  $msg" -ForegroundColor Red; exit 1 }

function Test-PortBusy($port) {
    $c = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    return [bool]$c
}

function Test-Url($url) {
    try { Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2 | Out-Null; return $true }
    catch { return $false }
}

# ---------------------------------------------------------------- checks
$sysPython = Get-Command python -ErrorAction SilentlyContinue
if (-not $sysPython) { $sysPython = Get-Command py -ErrorAction SilentlyContinue }
if (-not $sysPython) { Fail "Python not found. Install Python 3.12+ from python.org (tick 'Add python.exe to PATH')." }
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { Fail "npm not found. Install Node.js LTS from nodejs.org." }
foreach ($p in @($BackendPort, $FrontendPort)) {
    if (Test-PortBusy $p) { Fail "Port $p is already in use. Close the program using it and try again." }
}

# ------------------------------------------------------- first-time setup
if (-not (Test-Path $Py)) {
    Step "Creating Python virtual environment"
    & $sysPython.Source -m venv .venv
    if ($LASTEXITCODE -ne 0) { Fail "Could not create the virtual environment." }
}
& $Py -c "import sys; assert sys.version_info >= (3, 12)" 2>$null
if ($LASTEXITCODE -ne 0) { Fail "Python 3.12 or newer is required. Delete the .venv folder after installing a newer Python." }

& $Py -c "import fastapi, sklearn, psutil" 2>$null
if ($LASTEXITCODE -ne 0) {
    Step "Installing Python packages (a few minutes the first time)"
    & $Py -m pip install -q -r backend\requirements.txt -r agent\requirements.txt
    if ($LASTEXITCODE -ne 0) { Fail "pip install failed." }
}
if (-not (Test-Path "frontend\node_modules")) {
    Step "Installing dashboard packages (npm install)"
    Push-Location frontend; & npm.cmd install --silent; $ok = $LASTEXITCODE; Pop-Location
    if ($ok -ne 0) { Fail "npm install failed." }
}
if (-not (Test-Path "backend\.env")) {
    Step "Creating backend\.env with a new secret key"
    $key = & $Py -c "import secrets; print(secrets.token_urlsafe(48))"
    (Get-Content .env.example) `
        -replace '^AIIDS_SECRET_KEY=.*', "AIIDS_SECRET_KEY=$key" `
        -replace '^AIIDS_DATABASE_URL=.*', '# AIIDS_DATABASE_URL defaults to backend/aiids.db' |
        Set-Content -Encoding utf8 backend\.env
}
if (-not (Test-Path "ml\artifacts\manifest.json")) {
    Step "Training the ML model (first run only, ~30 s)"
    & $Py ml\src\train.py | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail "Model training failed." }
}
if (-not (Test-Path "backend\.demo_credentials.json")) {
    Step "Creating admin account and demo device"
    & $Py scripts\seed_demo_data.py 2>$null
}

# ------------------------------------------------------------- start
New-Item -ItemType Directory -Force -Path $Logs | Out-Null
$procs = @()

function Start-AiidsProcess($name, $file, $argList, $dir) {
    Start-Process -FilePath $file -ArgumentList $argList -WorkingDirectory $dir -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $Logs "$name.log") `
        -RedirectStandardError (Join-Path $Logs "$name.err.log")
}

try {
    Step "Starting backend on http://127.0.0.1:$BackendPort  (log: logs\backend.log)"
    $procs += Start-AiidsProcess "backend" $Py @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$BackendPort") (Join-Path $Root "backend")
    $healthy = $false
    for ($i = 0; $i -lt 60; $i++) {
        if (Test-Url "http://127.0.0.1:$BackendPort/api/v1/health") { $healthy = $true; break }
        if ($procs[0].HasExited) { break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $healthy) {
        Get-Content (Join-Path $Logs "backend.err.log") -Tail 20 -ErrorAction SilentlyContinue
        Fail "Backend failed to start (see logs\backend.err.log)"
    }

    Step "Starting dashboard on http://localhost:$FrontendPort  (log: logs\frontend.log)"
    $procs += Start-AiidsProcess "frontend" "npm.cmd" @("run", "dev", "--", "--host", "127.0.0.1", "--port", "$FrontendPort", "--strictPort") (Join-Path $Root "frontend")
    for ($i = 0; $i -lt 60; $i++) {
        if (Test-Url "http://127.0.0.1:$FrontendPort") { break }
        Start-Sleep -Milliseconds 500
    }

    if ($Demo) {
        Step "Replaying demo traffic every 30 s  (log: logs\replay.log)"
        $procs += Start-AiidsProcess "replay" $Py @("-u", "scripts\replay_flows.py", "--scenario", "all", "--loop", "30") $Root
    }

    if ($Agent) {
        & $Py -c "import sys; sys.path.insert(0, 'agent'); from agent import config; sys.exit(0 if config.load() else 1)"
        if ($LASTEXITCODE -eq 0) {
            Step "Starting monitoring agent  (log: logs\agent.log)"
            $procs += Start-AiidsProcess "agent" $Py @("-u", "-m", "agent", "run") (Join-Path $Root "agent")
        } else {
            Warn "Agent not enrolled yet: create a code on the Devices page, then run"
            Warn "  cd agent; ..\.venv\Scripts\python.exe -m agent register --server http://127.0.0.1:$BackendPort --code XXXX-XXXX-XXXX"
        }
    }

    $email = & $Py -c "import json; print(json.load(open('backend/.demo_credentials.json')).get('user', {}).get('email', 'your account'))" 2>$null
    if (-not $email) { $email = "your account" }
    Write-Host ""
    Write-Host "  AI-IDS is running" -ForegroundColor Green
    Write-Host "  ---------------------------------------------"
    Write-Host "  Dashboard:  http://localhost:$FrontendPort"
    Write-Host "  API docs:   http://127.0.0.1:$BackendPort/api/docs"
    Write-Host "  Login:      $email"
    Write-Host "              password is in backend\.demo_credentials.json"
    Write-Host "  ---------------------------------------------"
    Write-Host "  Press Ctrl+C to stop."
    Write-Host ""
    Start-Process "http://localhost:$FrontendPort"

    while ($true) {
        foreach ($p in $procs) {
            if ($p.HasExited) {
                Warn "A service stopped unexpectedly. Check the files in logs\."
                exit 1
            }
        }
        Start-Sleep -Seconds 2
    }
}
finally {
    Write-Host ""
    Step "Stopping AI-IDS"
    foreach ($p in $procs) {
        if ($p -and -not $p.HasExited) {
            # /T kills the whole process tree (npm -> node/vite, uvicorn workers).
            & taskkill.exe /PID $p.Id /T /F 2>$null | Out-Null
        }
    }
    Write-Host "Stopped."
}
