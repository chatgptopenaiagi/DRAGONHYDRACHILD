param(
    [ValidateSet('Install','Status','Start','Disable','Enable')][string]$Action = 'Status',
    [string]$Python = 'C:\Users\Administrator\anaconda3\envs\codex-pytorch\python.exe'
)
$ErrorActionPreference = 'Stop'
$childRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if ($childRoot -ne 'C:\xampp\DRAGONHYDRACHILD') { throw 'CHILD scheduler is bound to its isolated laboratory root.' }
$taskName = 'DRAGONHYDRACHILD-Prospective'
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
$entryPoint = Join-Path $childRoot 'scripts\child_collect.py'
if ($existingTask -and ($existingTask.Actions.Arguments -notlike ('*' + $entryPoint + '*'))) {
    throw 'Existing task name belongs to a different action; refusing to modify it.'
}
if ($Action -eq 'Install') {
    if ($existingTask) { throw 'CHILD task already exists; use Status/Enable instead.' }
    if (-not (Test-Path -LiteralPath $Python)) { throw 'Canonical Python missing.' }
    $taskAction = New-ScheduledTaskAction -Execute $Python -Argument ('-B "' + $entryPoint + '"') -WorkingDirectory $childRoot
    $trigger = New-ScheduledTaskTrigger -Daily -At ((Get-Date).AddMinutes(2))
    $principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 3) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName $taskName -Action $taskAction -Trigger $trigger -Principal $principal -Settings $settings -Description 'One lawful CHILD league snapshot daily; local rate ceiling and immutable receipts; no stored account password.' | Out-Null
} elseif ($Action -eq 'Start') {
    Start-ScheduledTask -TaskName $taskName
} elseif ($Action -eq 'Disable') {
    Disable-ScheduledTask -TaskName $taskName | Out-Null
} elseif ($Action -eq 'Enable') {
    Enable-ScheduledTask -TaskName $taskName | Out-Null
}
$task = Get-ScheduledTask -TaskName $taskName
$info = Get-ScheduledTaskInfo -TaskName $taskName
[ordered]@{ task=$taskName; state=[string]$task.State; last_run=$info.LastRunTime.ToUniversalTime().ToString('o'); next_run=$info.NextRunTime.ToUniversalTime().ToString('o'); last_result=$info.LastTaskResult; root=$childRoot; logon='Interactive; owner must be signed in'; cadence='daily'; stop_command='.\scripts\Manage-ChildScheduler.ps1 -Action Disable' } | ConvertTo-Json
