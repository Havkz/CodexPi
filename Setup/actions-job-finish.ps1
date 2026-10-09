$ErrorActionPreference = 'Stop'
$taskProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$PID"
$workerProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($taskProcess.ParentProcessId)"
if ($workerProcess.Name -ne 'Runner.Worker.exe') { throw 'Cannot confirm the Actions job process' }
& 'C:\Python314\python.exe' 'C:\CodexPi\app\windows_ci.py' finish --pid $workerProcess.ProcessId
if ($LASTEXITCODE -ne 0) { throw 'CodexPi CI release failed' }
