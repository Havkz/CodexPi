$ErrorActionPreference = 'Stop'
$taskRoot = 'C:\CodexPi'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run elevated to repair the confirmed Windows WoL adapter.'
}
$adapter = @(Get-NetAdapter -Physical | Where-Object MacAddress -eq '74-56-3C-2B-FD-0F')
if ($adapter.Count -ne 1) { throw 'The confirmed WoL Ethernet adapter was not found.' }
$powerKey = 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power'
$oldPower = Get-NetAdapterPowerManagement -Name $adapter[0].Name
$oldFast = Get-ItemProperty -LiteralPath $powerKey -Name HiberbootEnabled
$backup = Join-Path $taskRoot ('backups\wol-before-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.json')
@{mac=$adapter[0].MacAddress; wake=$oldPower.WakeOnMagicPacket.ToString(); fast_startup=$oldFast.HiberbootEnabled} |
    ConvertTo-Json | Set-Content -LiteralPath $backup -Encoding UTF8
# Hybrid shutdown does not reliably arm the NIC for WoL. Keep ordinary full shutdown.
Set-ItemProperty -LiteralPath $powerKey -Name HiberbootEnabled -Value 0
Enable-NetAdapterPowerManagement -Name $adapter[0].Name -WakeOnMagicPacket -NoRestart | Out-Null
Set-NetAdapterAdvancedProperty -Name $adapter[0].Name -RegistryKeyword '*WakeOnMagicPacket' -RegistryValue 1 -NoRestart
Set-NetAdapterAdvancedProperty -Name $adapter[0].Name -RegistryKeyword 'S5WakeOnLan' -RegistryValue 1 -NoRestart
if ((Get-ItemProperty -LiteralPath $powerKey -Name HiberbootEnabled).HiberbootEnabled -ne 0) {
    throw 'Fast Startup could not be disabled.'
}
Write-Output 'WoL configured; Fast Startup disabled. No network reset, reboot or shutdown was performed.'
Write-Output 'If the current driver still reports WakeOnMagicPacket Disabled, apply it at the next Windows restart.'
