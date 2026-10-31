param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [switch]$Preview
)
$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$python = Join-Path $ProjectRoot '.venv\Scripts\pythonw.exe'
$config = Join-Path $ProjectRoot 'data\daily\config.json'
if (!(Test-Path -LiteralPath $python) -or !(Test-Path -LiteralPath $config)) {
    throw 'Python 3.10 venv and data/daily/config.json are required.'
}
$arguments = '-m tracker.cli refresh --config "{0}" --scheduled' -f $config
$taskName = 'Pakistan Used Car Tracker - Daily'
if ($Preview) {
    [ordered]@{ TaskName=$taskName; Execute=$python; Arguments=$arguments;
        WorkingDirectory=$ProjectRoot; DailyAt='09:00'; TimeZone='Asia/Karachi';
        CatchUpAtLogon=$true; StartWhenAvailable=$true; RunOnlyWhenLoggedOn=$true
    } | ConvertTo-Json
    return
}
if ((Get-TimeZone).Id -ne 'Pakistan Standard Time') {
    throw 'This 09:00 local schedule requires Windows Pakistan Standard Time.'
}
$action = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $ProjectRoot
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$triggers = @((New-ScheduledTaskTrigger -Daily -At '09:00'), (New-ScheduledTaskTrigger -AtLogOn -User $user))
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $triggers `
    -Settings $settings -Principal $principal -Description 'Daily 09:00 Pakistan time; four-city collection and local dashboard export.' -Force | Out-Null
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State
