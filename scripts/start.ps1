param(
    [switch]$NoBrowser,
    [switch]$InstallDependencies
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$WebRoot = Join-Path $ProjectRoot 'web'
$VenvRoot = Join-Path $ProjectRoot '.venv'
$PythonPath = Join-Path $VenvRoot 'Scripts\python.exe'
$LogRoot = Join-Path $VenvRoot 'run'
$BackendUrl = 'http://127.0.0.1:8000'
$FrontendUrl = 'http://127.0.0.1:5173'

function Get-DependencyHash([string]$Path) {
    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    try {
        return [BitConverter]::ToString($algorithm.ComputeHash([IO.File]::ReadAllBytes($Path))).Replace('-', '')
    } finally {
        $algorithm.Dispose()
    }
}

function Assert-ProjectPort([int]$Port, [string]$CommandPattern) {
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    foreach ($listener in $listeners) {
        $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
        if (-not $owner -or $owner.CommandLine -notmatch $CommandPattern) {
            throw "Port $Port is used by another program. Close it and run start.bat again."
        }
    }
    return $listeners.Count -gt 0
}

function Wait-Service([string]$Url, [string]$Name, [string]$ErrorLog) {
    $deadline = (Get-Date).AddSeconds(60)
    do {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) { return }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    } while ((Get-Date) -lt $deadline)
    throw "$Name did not become ready within 60 seconds. Check: $ErrorLog"
}

try {
    Set-Location -LiteralPath $ProjectRoot
    $node = Get-Command node.exe -ErrorAction SilentlyContinue
    $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $node -or -not $npm) {
        throw 'Node.js and npm are required. Install them, then reopen start.bat. This project was tested with Node.js 22.'
    }

    # Refuse occupied ports before installing dependencies or launching anything.
    $backendPattern = [regex]::Escape($PythonPath) + '.*uvicorn\s+server\.main:app(?:\s|$)'
    $viteEntry = Join-Path $WebRoot 'node_modules\vite\bin\vite.js'
    $frontendPattern = [regex]::Escape($viteEntry).Replace('\\', '[\\/]')
    $backendRunning = Assert-ProjectPort 8000 $backendPattern
    $frontendRunning = Assert-ProjectPort 5173 $frontendPattern

    if (-not (Test-Path -LiteralPath $PythonPath)) {
        $systemPython = Get-Command python.exe -ErrorAction SilentlyContinue
        $pythonLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($systemPython) {
            & $systemPython.Source -m venv $VenvRoot
        } elseif ($pythonLauncher) {
            & $pythonLauncher.Source -3 -m venv $VenvRoot
        } else {
            throw 'Python is required. Install Python, then reopen start.bat. This project was tested with Python 3.13.'
        }
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $PythonPath)) {
            throw 'Could not create .venv. Check the Python installation.'
        }
    }

    & $PythonPath -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'
    if ($LASTEXITCODE -ne 0) { throw 'The project needs a working Python 3.10+ virtual environment.' }
    New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null

    $requirements = Join-Path $ProjectRoot 'server\requirements.txt'
    $requirementsHash = Get-DependencyHash $requirements
    $pythonStamp = Join-Path $VenvRoot '.startup-requirements.sha256'
    $pythonChanged = (Test-Path -LiteralPath $pythonStamp) -and ((Get-Content -LiteralPath $pythonStamp -Raw).Trim() -ne $requirementsHash)
    & $PythonPath -c "import importlib.util, sys; sys.exit(0 if all(importlib.util.find_spec(m) for m in ['fastapi', 'uvicorn', 'sqlalchemy', 'pydantic', 'backtrader', 'pandas', 'numpy', 'matplotlib', 'akshare', 'tqsdk', 'dotenv']) else 1)"
    if ($LASTEXITCODE -ne 0 -or $pythonChanged -or $InstallDependencies) {
        if ($backendRunning) { throw 'Stop the running backend before updating its dependencies.' }
        Write-Host 'Installing backend dependencies (first setup may take several minutes)...'
        & $PythonPath -m pip install -r $requirements
        if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed. Check the network and pip output above.' }
    }
    Set-Content -LiteralPath $pythonStamp -Value $requirementsHash -Encoding Ascii

    $lockHash = Get-DependencyHash (Join-Path $WebRoot 'package-lock.json')
    $frontendStamp = Join-Path $WebRoot 'node_modules\.startup-package.sha256'
    $frontendChanged = (Test-Path -LiteralPath $frontendStamp) -and ((Get-Content -LiteralPath $frontendStamp -Raw).Trim() -ne $lockHash)
    Push-Location -LiteralPath $WebRoot
    try {
        & $npm.Source ls --depth=0 --silent *> $null
        if ($LASTEXITCODE -ne 0 -or $frontendChanged -or $InstallDependencies) {
            if ($frontendRunning) { throw 'Stop the running frontend before updating its dependencies.' }
            Write-Host 'Installing frontend dependencies (first setup may take several minutes)...'
            & $npm.Source ci --no-audit --no-fund
            if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed. Check the network and npm output above.' }
        }
    } finally {
        Pop-Location
    }
    Set-Content -LiteralPath $frontendStamp -Value $lockHash -Encoding Ascii

    $envPath = Join-Path $ProjectRoot '.env'
    if (-not (Test-Path -LiteralPath $envPath)) {
        Copy-Item -LiteralPath (Join-Path $ProjectRoot '.env.example') -Destination $envPath
        Write-Host 'Created .env. Fill in your Tq credentials and Jin10 token to use those data sources.' -ForegroundColor Yellow
    }

    $backendLog = Join-Path $LogRoot 'backend.stderr.log'
    $frontendLog = Join-Path $LogRoot 'frontend.stderr.log'
    if (-not $backendRunning) {
        Write-Host 'Starting backend...'
        Start-Process -FilePath $PythonPath -ArgumentList '-m', 'uvicorn', 'server.main:app', '--host', '127.0.0.1', '--port', '8000' -WorkingDirectory $ProjectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $LogRoot 'backend.stdout.log') -RedirectStandardError $backendLog | Out-Null
    } else {
        Write-Host 'Backend is already running; reusing it.'
    }
    Wait-Service "$BackendUrl/openapi.json" 'Backend' $backendLog

    if (-not $frontendRunning) {
        Write-Host 'Starting frontend...'
        Start-Process -FilePath $node.Source -ArgumentList ('"' + $viteEntry + '"'), '--host', '127.0.0.1', '--port', '5173', '--strictPort' -WorkingDirectory $WebRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $LogRoot 'frontend.stdout.log') -RedirectStandardError $frontendLog | Out-Null
    } else {
        Write-Host 'Frontend is already running; reusing it.'
    }
    Wait-Service "$FrontendUrl/@vite/client" 'Frontend' $frontendLog

    Write-Host "Ready: $FrontendUrl" -ForegroundColor Green
    Write-Host "Backend: $BackendUrl | Logs: $LogRoot"
    if (-not $NoBrowser) { Start-Process $FrontendUrl | Out-Null }
    exit 0
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
