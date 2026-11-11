$ErrorActionPreference = 'Stop'

$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$frontendPath = Join-Path $projectRoot 'frontend'
$frontendEnvPath = Join-Path $frontendPath '.env.local'

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Project virtual environment not found at $pythonPath. Follow the setup steps in README.md first."
}

function Test-ApiAtPort([int]$Port) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "http://127.0.0.1:$Port/health"
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Test-PortBindable([int]$Port) {
    $listener = $null
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        if ($listener) { $listener.Stop() }
    }
}

$apiPort = $null
$apiAlreadyRunning = $false
for ($candidatePort = 8090; $candidatePort -le 8110; $candidatePort++) {
    if (Test-ApiAtPort $candidatePort) {
        $apiPort = $candidatePort
        $apiAlreadyRunning = $true
        break
    }
    if (Test-PortBindable $candidatePort) {
        $apiPort = $candidatePort
        break
    }
}
if ($null -eq $apiPort) {
    throw 'Could not find a free API port between 8090 and 8110. Close an existing server or check Windows port reservations.'
}

$apiUrl = "http://127.0.0.1:$apiPort"
$envLines = @()
if (Test-Path -LiteralPath $frontendEnvPath) {
    $envLines = @(Get-Content -LiteralPath $frontendEnvPath | Where-Object { $_ -notmatch '^VITE_API_URL=' })
}
$envLines += "VITE_API_URL=$apiUrl"
Set-Content -LiteralPath $frontendEnvPath -Value $envLines -Encoding utf8

if (-not $apiAlreadyRunning) {
    $apiArgs = @('-m', 'uvicorn', 'app.main:app', '--reload', '--host', '127.0.0.1', '--port', "$apiPort")
    Start-Process -FilePath $pythonPath -ArgumentList $apiArgs -WorkingDirectory $projectRoot
    $apiReady = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Seconds 1
        if (Test-ApiAtPort $apiPort) { $apiReady = $true; break }
    }
    if (-not $apiReady) {
        throw "The API did not start on port $apiPort. Check the API console window for details."
    }
}

$npmCommand = Get-Command 'npm.cmd' -ErrorAction SilentlyContinue
if (-not $npmCommand) { throw 'Node.js/npm is not installed or is not available on PATH.' }
if (-not (Test-Path -LiteralPath (Join-Path $frontendPath 'node_modules\vite\bin\vite.js'))) {
    Write-Host 'Installing dashboard dependencies...'
    Push-Location $frontendPath
    try { & $npmCommand.Source install } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { throw 'npm install failed. Check the frontend console output and try again.' }
}

$dashboardUrl = 'http://127.0.0.1:5173'
$dashboardReady = $false
try {
    $page = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 $dashboardUrl
    $dashboardReady = $page.StatusCode -eq 200 -and $page.Content -match 'Personal Job Finder'
} catch { }
if (-not $dashboardReady) {
    Start-Process -FilePath $npmCommand.Source -ArgumentList @('run', 'dev') -WorkingDirectory $frontendPath
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Seconds 1
        try {
            $page = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 $dashboardUrl
            if ($page.StatusCode -eq 200 -and $page.Content -match 'Personal Job Finder') {
                $dashboardReady = $true
                break
            }
        } catch { }
    }
}
if (-not $dashboardReady) {
    throw 'The dashboard did not start at http://127.0.0.1:5173. Check the frontend console window.'
}

Write-Host "API:       $apiUrl/docs"
Write-Host "Dashboard: $dashboardUrl"
Start-Process $dashboardUrl
