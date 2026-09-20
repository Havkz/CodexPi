$ErrorActionPreference = 'Stop'
$taskRoot = 'C:\CodexPi'
$workerDirectory = Join-Path $taskRoot 'windows-worker'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this installer elevated as the same Windows user, not as SYSTEM.'
}
if (-not (Test-Path -LiteralPath (Join-Path $workerDirectory 'config.json'))) {
    throw 'Provision the user DPAPI credential first.'
}
$acl = Get-Acl -LiteralPath $workerDirectory
$acl.SetAccessRuleProtection($true, $false)
foreach ($sid in @($identity.User.Value, 'S-1-5-18', 'S-1-5-32-544')) {
    $accountSid = [Security.Principal.SecurityIdentifier]::new($sid)
    $rule = [Security.AccessControl.FileSystemAccessRule]::new($accountSid, 'FullControl',
        'ContainerInherit,ObjectInherit', 'None', 'Allow')
    $acl.AddAccessRule($rule)
}
Set-Acl -LiteralPath $workerDirectory -AclObject $acl
$action = New-ScheduledTaskAction -Execute (Join-Path $taskRoot '.venv\Scripts\pythonw.exe') `
    -Argument '-m app.windows_worker' -WorkingDirectory $taskRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity.Name
$taskPrincipal = New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -Hidden -StartWhenAvailable -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
$existing = Get-ScheduledTask -TaskName 'CodexPi Windows Worker' -ErrorAction SilentlyContinue
if ($existing) {
    $backupDirectory = Join-Path $taskRoot 'backups'
    New-Item -ItemType Directory -Path $backupDirectory -Force | Out-Null
    Export-ScheduledTask -TaskName $existing.TaskName | Set-Content -LiteralPath `
        (Join-Path $backupDirectory ('worker-task-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.xml'))
}
Register-ScheduledTask -TaskName 'CodexPi Windows Worker' -Action $action -Trigger $trigger `
    -Principal $taskPrincipal -Settings $settings -Description 'Authenticated outbound CodexPi Windows test worker' -Force | Out-Null
Start-ScheduledTask -TaskName 'CodexPi Windows Worker'
Get-ScheduledTask -TaskName 'CodexPi Windows Worker' | Select-Object TaskName, State
