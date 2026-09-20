$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
. .\_common.ps1

$Root = Get-RepoRoot
$HomeDir = Initialize-AetherDirs
$env:AETHERQORE_HOME = $HomeDir
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$Python = Get-AetherPython
$Npm = Get-NpmCmd
$RunDir = Join-Path $HomeDir "run"
$LogDir = Join-Path $HomeDir "logs"

Write-Host "Stopping any previous AetherQore processes..."
Stop-AetherQore

$buildMarker = Join-Path $Frontend ".next"
if (-not (Test-Path $buildMarker)) {
  throw "Frontend production build is missing. Run deploy\windows\install.ps1 first."
}

Write-Host "Starting backend..."
$backend = Start-Process -FilePath $Python -ArgumentList "-m","app","serve" -WorkingDirectory $Backend -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $LogDir "backend.out.log") -RedirectStandardError (Join-Path $LogDir "backend.err.log")
Set-Content -Path (Join-Path $RunDir "backend.pid") -Value $backend.Id

Write-Host "Starting frontend..."
$frontend = Start-Process -FilePath $Npm -ArgumentList "run","start","--","-H","127.0.0.1","-p","3000" -WorkingDirectory $Frontend -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $LogDir "frontend.out.log") -RedirectStandardError (Join-Path $LogDir "frontend.err.log")
Set-Content -Path (Join-Path $RunDir "frontend.pid") -Value $frontend.Id

Write-Host "Waiting for services..."
Wait-Http "http://127.0.0.1:8000/health" 90
Wait-Http "http://127.0.0.1:3000" 90

Start-Process "http://127.0.0.1:3000"
Write-Host "AetherQore is ready at http://127.0.0.1:3000"
Write-Host "Use the Stop AetherQore desktop icon when the pharmacy closes."
