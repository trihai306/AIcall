param(
    [int]$TeacherSamples = 100,
    [int]$TeacherMaxAttempts = 600,
    [int]$TeacherWorkers = 2,
    [double]$Epochs = 1.0,
    [double]$LearningRate = 0.00002,
    [int]$MaxSamples = 6000,
    [int]$SleepSeconds = 1800,
    [switch]$Once,
    [switch]$ForceRetrain
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$python = Join-Path $repo ".venv-train\Scripts\python.exe"
$runner = Join-Path $repo "training\bankvn\qwen_continuous.py"

if (-not (Test-Path $python)) {
    throw "Chưa có .venv-train cho Qwen QLoRA"
}

$env:PYTHONUTF8 = "1"
Set-Location $repo
$runnerArgs = @(
    "--teacher-samples", "$TeacherSamples",
    "--teacher-max-attempts", "$TeacherMaxAttempts",
    "--teacher-workers", "$TeacherWorkers",
    "--epochs", "$Epochs",
    "--learning-rate", "$LearningRate",
    "--max-samples", "$MaxSamples",
    "--sleep-seconds", "$SleepSeconds"
)
if (-not $Once) { $runnerArgs += "--forever" }
if ($ForceRetrain) { $runnerArgs += "--force-retrain" }

& $python $runner @runnerArgs
exit $LASTEXITCODE
