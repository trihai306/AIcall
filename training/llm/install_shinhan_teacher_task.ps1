$ErrorActionPreference = "Stop"
$taskName = "Shinhan-Teacher-Questions"
$runner = "C:\duan\chat-ai\training\llm\run_shinhan_teacher.cmd"
$command = "cmd.exe /d /c $runner"

& schtasks.exe /Create /SC MINUTE /MO 1 /RL HIGHEST /TN $taskName /TR $command /F | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Cannot create Scheduled Task $taskName (exit $LASTEXITCODE)"
}
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries
Set-ScheduledTask -TaskName $taskName -Settings $settings | Out-Null
Write-Output "Installed $taskName"
