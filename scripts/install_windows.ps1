# =====================================================
# AI Banking Call System - Windows native installer
# Ban PowerShell tuong duong scripts/install/*.sh
# Chay: powershell -ExecutionPolicy Bypass -File install_windows.ps1
# =====================================================
$ErrorActionPreference = "Continue"
$PROJECT = "C:\duan\chat-ai"
$PY      = "$PROJECT\.venv\python.exe"
$PIP     = @("-m", "pip", "install", "--no-input")
$F5DIR   = "$PROJECT\tools\F5-TTS-Vietnamese"
$TTSDIR  = "$PROJECT\models\tts\F5-TTS-Vietnamese-ViVoice"
$PHODIR  = "$PROJECT\models\phowhisper"
$CT2DIR  = "$PHODIR\PhoWhisper-small-ct2"

function Step($n, $msg) {
    Write-Output ""
    Write-Output "############ STEP $n : $msg ############"
    Write-Output "[$(Get-Date -Format 'HH:mm:ss')]"
}

Set-Location $PROJECT

# ---------- 1. PyTorch CUDA 12.8 (Blackwell / RTX 50xx) ----------
Step 1 "PyTorch cu128"
$hasTorch = (& $PY -c "import torch,sys; sys.stdout.write(torch.__version__)" 2>$null)
if ($hasTorch) {
    Write-Output "[SKIP] torch da co: $hasTorch"
} else {
    & $PY -m pip install --no-input --upgrade pip
    & $PY @PIP torch torchaudio --index-url https://download.pytorch.org/whl/cu128
    Write-Output "[EXIT] $LASTEXITCODE"
}

# ---------- 2. Requirements cua project ----------
Step 2 "backend/requirements.txt"
& $PY @PIP -r "$PROJECT\backend\requirements.txt"
Write-Output "[EXIT] $LASTEXITCODE"

# ---------- 3. Clone + cai F5-TTS Vietnamese ----------
Step 3 "F5-TTS Vietnamese (clone + pip install -e)"
if (Test-Path "$F5DIR\pyproject.toml") {
    Write-Output "[SKIP] repo da co"
} else {
    if (Test-Path $F5DIR) { Remove-Item -Recurse -Force $F5DIR }
    New-Item -ItemType Directory -Force -Path "$PROJECT\tools" | Out-Null
    git clone --depth 1 https://github.com/nguyenthienhy/F5-TTS-Vietnamese $F5DIR
    Write-Output "[EXIT clone] $LASTEXITCODE"
}
if (Test-Path $F5DIR) {
    & $PY @PIP -e $F5DIR
    Write-Output "[EXIT pip -e] $LASTEXITCODE"
}

# ---------- 4. STT deps ----------
Step 4 "faster-whisper / ctranslate2 / transformers / huggingface_hub"
& $PY @PIP huggingface_hub faster-whisper "ctranslate2>=4.5" transformers
Write-Output "[EXIT] $LASTEXITCODE"

# ---------- 5. PhoWhisper -> CTranslate2 (int8_float16 vi co CUDA) ----------
Step 5 "PhoWhisper CT2"
if (Test-Path "$CT2DIR\model.bin") {
    Write-Output "[SKIP] CT2 model da co"
} else {
    New-Item -ItemType Directory -Force -Path $PHODIR | Out-Null
    $conv = "$PROJECT\.venv\Scripts\ct2-transformers-converter.exe"
    if (-not (Test-Path $conv)) { $conv = "$PROJECT\.venv\Scripts\ct2-transformers-converter" }
    & $conv --model vinai/PhoWhisper-small --output_dir $CT2DIR --quantization int8_float16 --copy_files tokenizer.json preprocessor_config.json
    if ($LASTEXITCODE -ne 0) {
        Write-Output "[RETRY] khong copy_files"
        & $conv --model vinai/PhoWhisper-small --output_dir $CT2DIR --quantization int8_float16
    }
    Write-Output "[EXIT] $LASTEXITCODE"
}

# ---------- 6. F5-TTS ViVoice checkpoint (~5.4GB) ----------
Step 6 "Tai model F5-TTS ViVoice (~5.4GB, lau)"
if (Test-Path "$TTSDIR\model_last.pt") {
    Write-Output "[SKIP] checkpoint da co"
} else {
    New-Item -ItemType Directory -Force -Path $TTSDIR | Out-Null
    & $PY -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='hynt/F5-TTS-Vietnamese-ViVoice', local_dir=r'$TTSDIR')"
    Write-Output "[EXIT] $LASTEXITCODE"
}
if ((Test-Path "$TTSDIR\config.json") -and (-not (Test-Path "$TTSDIR\vocab.txt"))) {
    Move-Item "$TTSDIR\config.json" "$TTSDIR\vocab.txt"
    Write-Output "[OK] doi ten config.json -> vocab.txt"
}

# ---------- 7. Ollama model ----------
Step 7 "Ollama model (theo OLLAMA_MODEL trong .env)"
$envModel = (Select-String -Path "$PROJECT\.env" -Pattern '^OLLAMA_MODEL=(.+)$' | ForEach-Object { $_.Matches[0].Groups[1].Value.Trim() })
if (-not $envModel) { $envModel = "qwen2.5:3b" }
Write-Output "Model can co: $envModel"
$have = (ollama list 2>$null | Out-String)
if ($have -match [regex]::Escape($envModel)) {
    Write-Output "[SKIP] da co $envModel"
} else {
    ollama pull $envModel
    Write-Output "[EXIT] $LASTEXITCODE"
}

# ---------- 8. Electron desktop deps ----------
Step 8 "npm install (desktop)"
if (Test-Path "$PROJECT\desktop\node_modules") {
    Write-Output "[SKIP] node_modules da co"
} else {
    Push-Location "$PROJECT\desktop"
    & cmd.exe /c "npm install 2>&1"
    Write-Output "[EXIT] $LASTEXITCODE"
    Pop-Location
}

# ---------- Tong ket ----------
Write-Output ""
Write-Output "############ HOAN TAT ############"
Write-Output "[$(Get-Date -Format 'HH:mm:ss')]"
& $PY -c @"
import importlib, sys
mods = ['torch','torchaudio','fastapi','uvicorn','faster_whisper','ctranslate2','chromadb','sentence_transformers','librosa','soundfile','ollama','f5_tts','torchcodec']
for m in mods:
    try:
        importlib.import_module(m)
        print(f'  OK   {m}')
    except Exception as e:
        print(f'  FAIL {m}: {type(e).__name__}: {str(e)[:90]}')
try:
    import torch
    print(f'  CUDA available: {torch.cuda.is_available()}')
    if torch.cuda.is_available():
        print(f'  GPU: {torch.cuda.get_device_name(0)}')
except Exception as e:
    print(f'  CUDA check failed: {e}')
"@
Write-Output "MARKER_INSTALL_DONE"
