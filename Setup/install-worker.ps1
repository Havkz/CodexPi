param([switch]$AutoBoot)
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

if ($AutoBoot) {
    New-Item -ItemType Directory -Path (Join-Path $taskRoot 'backups') -Force | Out-Null
    # Keep the browser-capable logon task; the startup worker hands off after user login.
    $adapter = Get-NetAdapter -Physical | Where-Object MacAddress -eq '74-56-3C-2B-FD-0F'
    if (@($adapter).Count -ne 1) { throw 'The confirmed Windows WoL Ethernet adapter was not found.' }
    $address = Get-NetIPAddress -InterfaceIndex $adapter.InterfaceIndex -AddressFamily IPv4 |
        Where-Object IPAddress -eq '192.168.2.200'
    if (-not $address) { throw 'The confirmed Windows WoL LAN address was not found.' }
    $credential = Get-Credential -UserName $identity.Name -Message 'CodexPi Boot Worker: Windows account password, not PIN. Stored only by Windows Task Scheduler.'
    if (-not $credential -or $credential.UserName -ne $identity.Name) { throw 'Use the current Windows user account.' }
    $bootAction = New-ScheduledTaskAction -Execute (Join-Path $taskRoot '.venv\Scripts\pythonw.exe') `
        -Argument '-m app.windows_worker --boot' -WorkingDirectory $taskRoot
    $existingBoot = Get-ScheduledTask -TaskName 'CodexPi Windows Boot Worker' -ErrorAction SilentlyContinue
    if ($existingBoot) {
        Export-ScheduledTask -TaskName $existingBoot.TaskName | Set-Content -LiteralPath `
            (Join-Path $taskRoot 'backups' ('boot-worker-task-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.xml'))
    }
    $bootTask = New-ScheduledTask -Action $bootAction -Trigger (New-ScheduledTaskTrigger -AtStartup) `
        -Settings $settings -Principal (New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType Password -RunLevel Highest)
    try {
        $taskPassword = $credential.GetNetworkCredential().Password
        Register-ScheduledTask -TaskName 'CodexPi Windows Boot Worker' -InputObject $bootTask `
            -User $identity.Name -Password $taskPassword -Force | Out-Null
    } finally {
        $taskPassword = $null
        $credential = $null
    }
    Enable-NetAdapterPowerManagement -Name $adapter.Name -WakeOnMagicPacket -NoRestart | Out-Null
    $powerConfig = @{mac=$adapter.MacAddress; address=$address.IPAddress; startup_ready=$true} | ConvertTo-Json
    Set-Content -LiteralPath (Join-Path $workerDirectory 'power.json') -Value $powerConfig -Encoding UTF8
    Get-ScheduledTask -TaskName 'CodexPi Windows Boot Worker' | Select-Object TaskName, State
}
