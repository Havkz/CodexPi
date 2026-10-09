$ErrorActionPreference = 'Stop'
$taskProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$PID"
$workerProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($taskProcess.ParentProcessId)"
if ($workerProcess.Name -ne 'Runner.Worker.exe' -or
    -not $workerProcess.ExecutablePath.StartsWith('C:\CodexPi\actions-runner\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Cannot confirm the native GitHub Actions job process'
}
& 'C:\Python314\python.exe' 'C:\CodexPi\app\windows_ci.py' start --pid $workerProcess.ProcessId
if ($LASTEXITCODE -ne 0) { throw 'CodexPi CI admission failed' }
