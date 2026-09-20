$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
. .\_common.ps1

$Root = Get-RepoRoot
$HomeDir = Initialize-AetherDirs
$env:AETHERQORE_HOME = $HomeDir
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"

Write-Host "AetherQore installer"
Write-Host "App files: $Root"
Write-Host "Data folder: $HomeDir"
Write-Host ""

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
if (-not $py) { throw "Python 3.11+ is required. Install from https://www.python.org/downloads/windows/ and tick 'Add python.exe to PATH'." }

Write-Host "Creating Python virtualenv..."
$venv = Join-Path $Backend ".venv"
if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) {
  & $py.Source -m venv $venv
}
$venvPython = Join-Path $venv "Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $Backend "requirements.txt")

$npm = Get-NpmCmd
Write-Host "Installing frontend packages (needs internet this once)..."
Push-Location $Frontend
try {
  & $npm install
  $env:NEXT_PUBLIC_API_URL = "http://127.0.0.1:8000"
  & $npm run build
} finally {
  Pop-Location
}

if (-not $env:AETHERQORE_ADMIN_EMAIL) {
  $entered = Read-Host "Admin email [admin@pharmacy.local]"
  $env:AETHERQORE_ADMIN_EMAIL = $(if ($entered) { $entered } else { "admin@pharmacy.local" })
}
if (-not $env:AETHERQORE_ADMIN_NAME) {
  $entered = Read-Host "Admin full name [Pharmacy Admin]"
  $env:AETHERQORE_ADMIN_NAME = $(if ($entered) { $entered } else { "Pharmacy Admin" })
}
if (-not $env:AETHERQORE_PHARMACY_NAME) {
  $entered = Read-Host "Pharmacy name [Pharmacy]"
  $env:AETHERQORE_PHARMACY_NAME = $(if ($entered) { $entered } else { "Pharmacy" })
}
if (-not $env:AETHERQORE_ADMIN_PASSWORD) {
  $secure = Read-Host "Admin password (leave blank to generate one)" -AsSecureString
  $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
  $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto($ptr)
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
  if ($plain) { $env:AETHERQORE_ADMIN_PASSWORD = $plain }
}

Write-Host "Writing local production config..."
Push-Location $Backend
try {
  & $venvPython -m app init-config
  & $venvPython -m app migrate
  & $venvPython -m app bootstrap
} finally {
  Pop-Location
}

$Wsh = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath("Desktop")
$start = $Wsh.CreateShortcut((Join-Path $desktop "AetherQore.lnk"))
$start.TargetPath = Join-Path $PSScriptRoot "Start-AetherQore.bat"
$start.WorkingDirectory = $PSScriptRoot
$start.WindowStyle = 7
$start.Description = "Start AetherQore on this computer"
$start.Save()

$stop = $Wsh.CreateShortcut((Join-Path $desktop "Stop AetherQore.lnk"))
$stop.TargetPath = Join-Path $PSScriptRoot "Stop-AetherQore.bat"
$stop.WorkingDirectory = $PSScriptRoot
$stop.WindowStyle = 7
$stop.Description = "Stop AetherQore"
$stop.Save()

Write-Host ""
Write-Host "Install finished."
Write-Host "First login details: $(Join-Path $HomeDir 'config\FIRST_LOGIN.txt')"
Write-Host "Double-click the AetherQore icon on the desktop to start."
Write-Host "Leave AI_PROVIDER and AI_API_KEY empty for an offline pharmacy."
