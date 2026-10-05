param(
    [string]$Profile = "training/bankvn/configs/bankvn-350m-rtx5070-continual.json",
    [string]$ProfileName = "bankvn-350m-rtx5070-continual",
    [string]$FetchDataset = "hoanghai2110/vi-pretrain-clean",
    [string]$FetchOutput = "data/bankvn/raw/vi_pretrain_clean_20k.jsonl",
    [int]$FetchDocsPerCycle = 250,
    [string]$Tokenizer = "models/bankvn/tokenizer-sp-smoke6",
    [string]$PretrainOutput = "models/bankvn/pretrain/bankvn-continual-20260920",
    [string]$InitFrom = "models/bankvn/sft/bankvn-smoke6-router-refine1/final",
    [string]$SftBase = "models/bankvn/sft/bankvn-smoke6-router-refine1/final",
    [switch]$EnablePretrain,
    [int]$StepsPerCycle = 200,
    [int]$TeacherSamples = 200,
    [int]$RouterTeacherSamplesPerClass = 20,
    [int]$RouterTeacherBatchSize = 3,
    [int]$TeacherMaxAttempts = 1200,
    [int]$TeacherBatchSize = 20,
    [int]$TeacherMaxBatches = 12,
    [string]$TeacherShardDir = "data/bankvn/sft/teacher_shards",
    [int]$TeacherSeed = 42,
    [string]$TeacherModel = "qwen3.5:9b",
    [int]$TeacherWorkers = 2,
    [int]$TeacherSourceChars = 1600,
    [int]$TeacherSourceOverlapChars = 160,
    [int]$TeacherMaxChunksPerSource = 8,
    [int]$TeacherNumPredict = 384,
    [int]$TeacherRetryNumPredict = 768,
    [int]$TeacherNumCtx = 4096,
    [int]$TeacherSpeechProfilesPerSource = 3,
    [double]$CorpusMinScore = 0.18,
    [int]$MinCorpusDocs = 10000,
    [int]$SftBatchSize = 1,
    [int]$SftGradAccum = 8,
    [string]$SftOutput = "models/bankvn/sft/bankvn-candidate",
    [double]$SftEpochs = 0.25,
    [int]$SftMinUpdates = 0,
    [double]$SftLr = 0.000002,
    [int]$SftMaxSourceRecords = 600,
    [int]$SftMaxReplayRecords = 600,
    [double]$SftAssistantRouterRatio = 0.5,
    [switch]$SftRouterFormatTokens,
    [string]$BenchmarkDataset = "training/bankvn/bench/router_cases.jsonl",
    [string]$BenchmarkBaseline = "data/bankvn/state/router-baseline-clean40.json",
    [string]$BenchmarkOutput = "data/bankvn/state/router-candidate-continuous.json",
    [string]$GateOutput = "data/bankvn/state/router-last-gate.json",
    [string]$CandidateModelName = "bankvn-candidate-continuous",
    [double]$GateMinDomainAccuracy = 0.90,
    [double]$GateMinToolCallAccuracy = 0.90,
    [double]$GateMaxHallucinationRate = 0.10,
    [double]$GateMinDecodeSpeedFactor = 0.90,
    [int]$MinFreeVramMB = 7000,
    [int]$SleepSeconds = 300,
    [switch]$Once
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path
$python = Join-Path $repo ".venv-train\\Scripts\\python.exe"
$continuous = Join-Path $repo "training\\bankvn\\continuous.py"

if (-not (Test-Path $python)) {
    throw "Chưa có .venv-train. Chạy: python training\\llm\\setup_env.py"
}

$env:PYTHONUTF8 = "1"
Set-Location $repo

$continuousArgs = @(
    "--profile", $Profile,
    "--profile-name", $ProfileName,
    "--fetch-dataset", $FetchDataset,
    "--fetch-output", $FetchOutput,
    "--fetch-docs-per-cycle", "$FetchDocsPerCycle",
    "--tokenizer", $Tokenizer,
    "--pretrain-output", $PretrainOutput,
    "--init-from", $InitFrom,
    "--sft-base", $SftBase,
    "--steps-per-cycle", "$StepsPerCycle",
    "--teacher-model", $TeacherModel,
    "--teacher-samples", "$TeacherSamples",
    "--router-teacher-samples-per-class", "$RouterTeacherSamplesPerClass",
    "--router-teacher-batch-size", "$RouterTeacherBatchSize",
    "--teacher-max-attempts", "$TeacherMaxAttempts",
    "--teacher-batch-size", "$TeacherBatchSize",
    "--teacher-max-batches", "$TeacherMaxBatches",
    "--teacher-shard-dir", $TeacherShardDir,
    "--teacher-seed", "$TeacherSeed",
    "--teacher-workers", "$TeacherWorkers",
    "--teacher-source-chars", "$TeacherSourceChars",
    "--teacher-source-overlap-chars", "$TeacherSourceOverlapChars",
    "--teacher-max-chunks-per-source", "$TeacherMaxChunksPerSource",
    "--teacher-num-predict", "$TeacherNumPredict",
    "--teacher-retry-num-predict", "$TeacherRetryNumPredict",
    "--teacher-num-ctx", "$TeacherNumCtx",
    "--teacher-speech-profiles-per-source", "$TeacherSpeechProfilesPerSource",
    "--corpus-min-score", "$CorpusMinScore",
    "--min-corpus-docs", "$MinCorpusDocs",
    "--sft-batch-size", "$SftBatchSize",
    "--sft-grad-accum", "$SftGradAccum",
    "--sft-output", $SftOutput,
    "--sft-epochs", "$SftEpochs",
    "--sft-min-updates", "$SftMinUpdates",
    "--sft-lr", "$SftLr",
    "--sft-max-source-records", "$SftMaxSourceRecords",
    "--sft-max-replay-records", "$SftMaxReplayRecords",
    "--sft-assistant-router-ratio", "$SftAssistantRouterRatio",
    "--benchmark-dataset", $BenchmarkDataset,
    "--benchmark-baseline", $BenchmarkBaseline,
    "--benchmark-output", $BenchmarkOutput,
    "--gate-output", $GateOutput,
    "--candidate-model-name", $CandidateModelName,
    "--gate-min-domain-accuracy", "$GateMinDomainAccuracy",
    "--gate-min-tool-call-accuracy", "$GateMinToolCallAccuracy",
    "--gate-max-hallucination-rate", "$GateMaxHallucinationRate",
    "--gate-min-decode-speed-factor", "$GateMinDecodeSpeedFactor",
    "--min-free-vram-mb", "$MinFreeVramMB",
    "--sleep-seconds", "$SleepSeconds"
)

if ($EnablePretrain) {
    $continuousArgs += "--enable-pretrain"
}
if ($SftRouterFormatTokens) {
    $continuousArgs += "--sft-router-format-tokens"
}
if (-not $Once) {
    $continuousArgs += "--forever"
}

& $python $continuous @continuousArgs
exit $LASTEXITCODE
