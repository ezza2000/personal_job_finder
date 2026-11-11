$ErrorActionPreference = 'Stop'

$taskName = 'Personal Job Finder'
$projectRoot = $PSScriptRoot
$launcher = Join-Path $projectRoot 'run.ps1'
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$powerShell = Join-Path $PSHOME 'powershell.exe'

if (-not (Test-Path -LiteralPath $launcher)) {
    throw "App launcher not found at $launcher"
}

$action = New-ScheduledTaskAction `
    -Execute $powerShell `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$launcher`"" `
    -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$principal = New-ScheduledTaskPrincipal `
    -UserId $currentUser `
    -LogonType Interactive `
    -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $taskName `
    -Description 'Starts the Personal Job Finder dashboard and checks configured Gmail SEEK alerts at sign-in.' `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Force | Out-Null

Write-Host "Registered '$taskName' to start when $currentUser signs in."
