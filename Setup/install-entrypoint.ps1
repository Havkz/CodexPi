$ErrorActionPreference = 'Stop'
$entryDirectory = 'C:\CodexPi\bin'
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$parts = @($userPath -split ';' | Where-Object { $_ })
if ($entryDirectory -notin $parts) {
    $backupDirectory = 'C:\CodexPi\backups'
    New-Item -ItemType Directory -Path $backupDirectory -Force | Out-Null
    $userPath | Set-Content -LiteralPath (Join-Path $backupDirectory ('user-path-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.txt'))
    [Environment]::SetEnvironmentVariable('Path', (($parts + $entryDirectory) -join ';'), 'User')
}
Add-Type -Namespace CodexPi -Name EnvironmentNotice -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("user32.dll", CharSet=System.Runtime.InteropServices.CharSet.Unicode, SetLastError=true)]
public static extern System.IntPtr SendMessageTimeout(System.IntPtr window, uint message, System.UIntPtr wparam,
    string lparam, uint flags, uint timeout, out System.UIntPtr result);
'@
$noticeResult = [UIntPtr]::Zero
[CodexPi.EnvironmentNotice]::SendMessageTimeout([IntPtr]0xffff, 0x1a, [UIntPtr]::Zero,
    'Environment', 2, 3000, [ref]$noticeResult) | Out-Null
Write-Output 'codexpi is registered in the user PATH. Open a new terminal to use it.'
