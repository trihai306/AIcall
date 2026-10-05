param(
    [int]$TeacherSamples = 100,
    [int]$RouterTeacherSamplesPerClass = 20,
    [int]$SleepSeconds = 300
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..\")).Path
$runner = Join-Path $PSScriptRoot "run_forever.ps1"
$logs = Join-Path $repo "logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null
$log = Join-Path $logs "bankvn_24x7.log"

$runnerArgs = @{
    TeacherSamples = $TeacherSamples
    RouterTeacherSamplesPerClass = $RouterTeacherSamplesPerClass
    SleepSeconds = $SleepSeconds
    SftBase = "models/bankvn/sft/bankvn-candidate-1h-20260921/final"
    SftOutput = "models/bankvn/sft/bankvn-candidate-24x7"
}

"[$(Get-Date -Format o)] BankVN 24x7 start" | Out-File -FilePath $log -Append -Encoding utf8
$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $runner @runnerArgs 2>&1 | Out-File -FilePath $log -Append -Encoding utf8
$runnerExitCode = $LASTEXITCODE
$runnerSucceeded = $?
$ErrorActionPreference = $previousErrorActionPreference
if ($null -eq $runnerExitCode) {
    $runnerExitCode = if ($runnerSucceeded) { 0 } else { 1 }
}
exit $runnerExitCode
