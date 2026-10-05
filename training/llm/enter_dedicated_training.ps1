$ErrorActionPreference = "Stop"
$project = "C:\duan\chat-ai"
$statePath = Join-Path $project "logs\dedicated_training_state.json"
$stopTasks = @("VoiceBankMoApp", "VoiceBankMan", "BankVN-Test-Ollama-CPU")
$state = @()

foreach ($name in $stopTasks) {
    $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if (-not $task) { continue }
    $state += [pscustomobject]@{ name = $name; state = [string]$task.State }
    if ($task.State -eq "Running") { Stop-ScheduledTask -TaskName $name }
    if ($task.State -ne "Disabled") { Disable-ScheduledTask -TaskName $name | Out-Null }
}
$state | ConvertTo-Json -Depth 3 | Set-Content -Path $statePath -Encoding UTF8

$teacher = Get-ScheduledTask -TaskName "Shinhan-Teacher-Questions" -ErrorAction Stop
if ($teacher.State -eq "Running") { Stop-ScheduledTask -TaskName $teacher.TaskName }
Get-CimInstance Win32_Process -Filter "Name='VoiceBank AI.exe'" -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
& (Join-Path $project "scripts\stop_services.ps1")

# The teacher remains the only project process using the production Ollama/GPU.
Start-ScheduledTask -TaskName "Shinhan-Teacher-Questions"
Start-Sleep -Seconds 3
$listening = Get-NetTCPConnection -State Listen -LocalPort 8100 -ErrorAction SilentlyContinue
$teacher = Get-ScheduledTask -TaskName "Shinhan-Teacher-Questions"
Write-Output ([pscustomobject]@{
    backend_stopped = -not [bool]$listening
    teacher_task = [string]$teacher.State
    disabled_tasks = $stopTasks
    ollama_models = @(ollama ps | Select-Object -Skip 1)
} | ConvertTo-Json -Depth 4)
if ($listening -or $teacher.State -ne "Running") { exit 1 }
