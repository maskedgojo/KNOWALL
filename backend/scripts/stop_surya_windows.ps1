# Stop ONLY the llama-server process registered by this user's Surya instance.
# Run after stopping the Flask backend. Intentionally not invoked at every request.
$ErrorActionPreference = "Stop"
$sentinel = Join-Path $HOME ".cache\datalab\surya\llamacpp_server.json"
if (-not (Test-Path $sentinel)) { Write-Output "No Surya llama.cpp sentinel; nothing to stop."; exit 0 }
$record = Get-Content $sentinel -Raw | ConvertFrom-Json
$serverPid = [int]$record.pid
if ($serverPid -le 0) { throw "Invalid PID in Surya sentinel. Inspect manually." }
$proc = Get-CimInstance Win32_Process -Filter "ProcessId = $serverPid"
if ($null -eq $proc) { Write-Output "Process already stopped. Removing stale sentinel."; Remove-Item $sentinel; exit 0 }
# Don't terminate unrelated processes if Windows has reused a process ID.
if (($proc.Name -notlike "llama-server*") -or ($proc.CommandLine -notmatch "llama-server")) {
    throw "PID $serverPid does not look like llama-server. Refusing to stop it."
}
Stop-Process -Id $serverPid -Force
Start-Sleep -Milliseconds 500
if (-not (Get-Process -Id $serverPid -ErrorAction SilentlyContinue)) {
    Remove-Item $sentinel -ErrorAction SilentlyContinue
    Write-Output "Stopped Surya llama-server (PID $serverPid)."
} else {
    Write-Warning "Process still appears active; inspect Task Manager."
}
