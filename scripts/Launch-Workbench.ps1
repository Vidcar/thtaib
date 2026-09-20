param(
  [switch]$CheckOnly,
  [switch]$NoDesktop,
  [switch]$ShowConsole
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backendUrl = "http://127.0.0.1:8000"

function Get-ProductDataRoot {
  if ($env:WORKBENCH_DATA_ROOT) {
    return $env:WORKBENCH_DATA_ROOT
  }
  $localAppData = $env:LOCALAPPDATA
  if (-not $localAppData) {
    $localAppData = Join-Path $HOME "AppData\Local"
  }
  return Join-Path $localAppData "LocalAIWorkbench"
}

$dataRoot = Get-ProductDataRoot
$logRoot = Join-Path $dataRoot "logs"
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
$launcherLog = Join-Path $logRoot "workbench-launcher.log"
$backendOutLog = Join-Path $logRoot "workbench-backend-launcher.out.log"
$backendErrLog = Join-Path $logRoot "workbench-backend-launcher.err.log"

function Write-LaunchLog($message) {
  $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  Add-Content -Path $launcherLog -Value "[$stamp] $message"
}

function Show-Error($message) {
  Write-LaunchLog "ERROR $message"
  if (-not $ShowConsole) {
    try {
      $shell = New-Object -ComObject WScript.Shell
      $null = $shell.Popup($message, 0, "Local AI Workbench", 16)
    } catch {
      Write-Host $message
    }
  } else {
    Write-Host $message
  }
}

function Assert-Command($name) {
  $command = Get-Command $name -ErrorAction SilentlyContinue
  if (-not $command) {
    throw "$name is not available on PATH. Local AI Workbench was not launched."
  }
  return $command.Source
}

function Test-BackendHealth {
  try {
    $health = Invoke-RestMethod -Uri "$backendUrl/health" -TimeoutSec 2
    return $health.status -eq "ok" -and $health.product -eq "Local AI Workbench"
  } catch {
    return $false
  }
}

function Wait-BackendHealth($timeoutSeconds) {
  $deadline = (Get-Date).AddSeconds($timeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    if (Test-BackendHealth) {
      return $true
    }
    Start-Sleep -Milliseconds 500
  }
  return $false
}

function Assert-BuiltDesktop {
  $index = Join-Path $repoRoot "apps\desktop\dist\index.html"
  $main = Join-Path $repoRoot "apps\desktop\dist-electron\main.js"
  if (-not (Test-Path $index) -or -not (Test-Path $main)) {
    throw "The desktop build is missing. Ask Codex to build the desktop before launching."
  }
}

function Start-BackendIfNeeded {
  if (Test-BackendHealth) {
    Write-LaunchLog "Reusing healthy backend at $backendUrl"
    return
  }

  $mutex = New-Object System.Threading.Mutex($false, "LocalAIWorkbench.LaunchBackend")
  $hasMutex = $false
  try {
    $hasMutex = $mutex.WaitOne([TimeSpan]::FromSeconds(30))
    if (-not $hasMutex) {
      throw "Another launcher is starting the backend and did not finish in time."
    }
    if (Test-BackendHealth) {
      Write-LaunchLog "Backend became healthy while waiting for launch lock"
      return
    }

    $uv = Assert-Command "uv"
    $backendDir = Join-Path $repoRoot "apps\backend"
    Write-LaunchLog "Starting backend with uv at $backendUrl"
    Start-Process `
      -FilePath $uv `
      -ArgumentList @("--directory", "`"$backendDir`"", "run", "workbench-backend", "--host", "127.0.0.1", "--port", "8000") `
      -WorkingDirectory $repoRoot `
      -WindowStyle Hidden `
      -RedirectStandardOutput $backendOutLog `
      -RedirectStandardError $backendErrLog | Out-Null

    if (-not (Wait-BackendHealth 45)) {
      throw "The backend did not become healthy on 127.0.0.1:8000. See $backendErrLog"
    }
    Write-LaunchLog "Backend is healthy"
  } finally {
    if ($hasMutex) {
      $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
  }
}

function Open-Desktop {
  if ($NoDesktop) {
    Write-LaunchLog "NoDesktop requested; backend check complete"
    return
  }
  $desktopDir = Join-Path $repoRoot "apps\desktop"
  $electron = Join-Path $desktopDir "node_modules\electron\dist\electron.exe"
  if (-not (Test-Path $electron)) {
    throw "Electron is missing at $electron. The existing desktop dependencies are not installed."
  }
  Write-LaunchLog "Opening Electron desktop"
  Start-Process `
    -FilePath $electron `
    -ArgumentList @(".") `
    -WorkingDirectory $desktopDir `
    -WindowStyle Normal | Out-Null
}

try {
  Write-LaunchLog "Launcher started"
  Assert-Command "uv" | Out-Null
  Assert-BuiltDesktop
  Start-BackendIfNeeded
  if ($CheckOnly) {
    Write-LaunchLog "CheckOnly passed"
    Write-Host "Local AI Workbench launcher checks passed."
    exit 0
  }
  Open-Desktop
  Write-LaunchLog "Launcher finished"
} catch {
  Show-Error $_.Exception.Message
  exit 1
}
