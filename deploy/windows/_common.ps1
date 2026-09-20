$ErrorActionPreference = "Stop"

function Get-RepoRoot {
  return (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

function Get-AetherHome {
  if ($env:AETHERQORE_HOME -and $env:AETHERQORE_HOME.Trim()) {
    return $env:AETHERQORE_HOME
  }
  return (Join-Path $env:LOCALAPPDATA "AetherQore")
}

function Get-AetherPython {
  $root = Get-RepoRoot
  $venvPython = Join-Path $root "backend\.venv\Scripts\python.exe"
  if (Test-Path $venvPython) {
    return $venvPython
  }
  throw "Python virtualenv not found at $venvPython. Run deploy\windows\install.ps1 first."
}

function Get-NpmCmd {
  $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
  if (-not $npm) {
    throw "npm was not found on PATH. Install Node.js 20 LTS, then reopen PowerShell."
  }
  return $npm.Source
}

function Initialize-AetherDirs {
  $homeDir = Get-AetherHome
  foreach ($name in @("data", "backups", "logs", "config", "uploads", "run")) {
    $path = Join-Path $homeDir $name
    if (-not (Test-Path $path)) {
      New-Item -ItemType Directory -Path $path | Out-Null
    }
  }
  return $homeDir
}

function Stop-ListenPort([int]$Port) {
  try {
    $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($row in $listeners) {
      Stop-Process -Id $row.OwningProcess -Force -ErrorAction SilentlyContinue
    }
  } catch {
    $lines = netstat -ano | Select-String ":$Port\s+.LISTENING"
    foreach ($line in $lines) {
      $procId = ($line.ToString().Trim() -split "\s+")[-1]
      if ($procId -match "^\d+$") {
        Stop-Process -Id ([int]$procId) -Force -ErrorAction SilentlyContinue
      }
    }
  }
}

function Stop-PidFile([string]$PidFile) {
  if (-not (Test-Path $PidFile)) { return }
  $procId = (Get-Content $PidFile | Select-Object -First 1).Trim()
  if ($procId -match "^\d+$") {
    Stop-Process -Id ([int]$procId) -Force -ErrorAction SilentlyContinue
  }
  Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

function Stop-AetherQore {
  $homeDir = Initialize-AetherDirs
  $runDir = Join-Path $homeDir "run"
  Stop-PidFile (Join-Path $runDir "backend.pid")
  Stop-PidFile (Join-Path $runDir "frontend.pid")
  Stop-ListenPort 8000
  Stop-ListenPort 3000
  Start-Sleep -Seconds 1
}

function Wait-Http([string]$Url, [int]$Seconds = 60) {
  $deadline = (Get-Date).AddSeconds($Seconds)
  while ((Get-Date) -lt $deadline) {
    try {
      $res = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
      if ($res.StatusCode -ge 200 -and $res.StatusCode -lt 500) {
        return
      }
    } catch {
      Start-Sleep -Milliseconds 800
    }
  }
  throw "Timed out waiting for $Url"
}
