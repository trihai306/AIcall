param(
    [string]$Model = "bankvn-candidate-conservative-v1",
    [string]$Dataset = "training/bankvn/bench/router_cases.jsonl",
    [string]$Output = "data/bankvn/state/router-candidate-conservative-clean40.json"
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..\")).Path
$python = Join-Path $repo ".venv-train\Scripts\python.exe"
$benchmark = Join-Path $repo "training\bankvn\router_benchmark.py"

if (-not (Test-Path $python)) {
    throw "Khong thay .venv-train Python: $python"
}

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
Set-Location $repo

& $python -X utf8 $benchmark --model $Model --dataset $Dataset --output $Output
exit $LASTEXITCODE
