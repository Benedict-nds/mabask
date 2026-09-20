$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
. .\_common.ps1

Stop-AetherQore
Write-Host "AetherQore stopped."
