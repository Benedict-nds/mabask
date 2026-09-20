param(
  [Parameter(Mandatory = $true)]
  [string]$BackupFile
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
. .\_common.ps1

if (-not (Test-Path $BackupFile)) {
  throw "Backup file not found: $BackupFile"
}

Write-Host "Stopping AetherQore before restore..."
Stop-AetherQore

$env:AETHERQORE_HOME = Get-AetherHome
$Python = Get-AetherPython
$Backend = Join-Path (Get-RepoRoot) "backend"
Push-Location $Backend
try {
  & $Python -m app restore $BackupFile
  & $Python -m app verify
} finally {
  Pop-Location
}
Write-Host "Restore complete. Start AetherQore from the desktop icon."
