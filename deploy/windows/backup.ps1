$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
. .\_common.ps1

$env:AETHERQORE_HOME = Get-AetherHome
Initialize-AetherDirs | Out-Null
$Python = Get-AetherPython
$Backend = Join-Path (Get-RepoRoot) "backend"
Push-Location $Backend
try {
  & $Python -m app backup
} finally {
  Pop-Location
}
Write-Host "Backups folder: $(Join-Path (Get-AetherHome) 'backups')"
