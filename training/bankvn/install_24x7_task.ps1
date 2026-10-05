$ErrorActionPreference = "Stop"

$taskName = "BankVN-Train-24x7"
$runner = "C:\duan\chat-ai\training\bankvn\run_24x7_logged.cmd"
$taskCommand = "cmd.exe /d /c $runner"
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

# schtasks resolves the current interactive account reliably over OpenSSH.
# PowerShell then applies settings that schtasks.exe does not expose, notably
# unlimited runtime and automatic restart after a failure.
& schtasks.exe /Create /SC ONLOGON /RL HIGHEST /TN $taskName /TR $taskCommand /F | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Không tạo được Scheduled Task $taskName (mã $LASTEXITCODE)"
}
Set-ScheduledTask -TaskName $taskName -Settings $settings | Out-Null

Write-Output "OK: $taskName"
