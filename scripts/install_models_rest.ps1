# =====================================================
# Cai not cac model con thieu (chay SAU install_windows.ps1)
#   - BAAI/bge-m3        : embedding cho RAG (~2.3GB)
#   - Silero VAD         : phat hien giong noi (torch.hub, nho)
#   - Vistral-7B-Chat    : LLM tieng Viet GGUF (~4GB) -> ollama create
# =====================================================
$ErrorActionPreference = "Continue"
$PROJECT = "C:\duan\chat-ai"
$PY      = "$PROJECT\.venv\python.exe"
$LLMDIR  = "$PROJECT\models\llm"
$GGUF    = "$LLMDIR\vistral-7b-chat-q4.gguf"

function Step($n,$m){ Write-Output ""; Write-Output "############ MODEL $n : $m ############"; Write-Output "[$(Get-Date -Format 'HH:mm:ss')]" }
Set-Location $PROJECT

# ---------- 1. bge-m3 (RAG embedding) ----------
Step 1 "BAAI/bge-m3 (embedding RAG)"
& $PY -c @"
from sentence_transformers import SentenceTransformer
m = SentenceTransformer('BAAI/bge-m3')
v = m.encode(['xin chao'])
print('  bge-m3 OK, dim =', len(v[0]))
"@
Write-Output "[EXIT] $LASTEXITCODE"

# ---------- 2. Silero VAD ----------
Step 2 "Silero VAD"
& $PY -c @"
import torch
model, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad', model='silero_vad', force_reload=False, trust_repo=True)
print('  Silero VAD OK')
"@
Write-Output "[EXIT] $LASTEXITCODE"

# ---------- 3. Vistral-7B-Chat GGUF -> Ollama ----------
Step 3 "Vistral-7B-Chat GGUF (~4GB)"
New-Item -ItemType Directory -Force -Path $LLMDIR | Out-Null
if (Test-Path $GGUF) {
    Write-Output "[SKIP] GGUF da co"
} else {
    & $PY -c @"
from huggingface_hub import hf_hub_download
import shutil
p = hf_hub_download(repo_id='uonlp/Vistral-7B-Chat-gguf', filename='ggml-vistral-7B-chat-q4_1.gguf')
shutil.copy(p, r'$GGUF')
print('  Saved ->', r'$GGUF')
"@
    Write-Output "[EXIT] $LASTEXITCODE"
}
if (Test-Path $GGUF) {
    $have = (ollama list 2>$null | Out-String)
    if ($have -match "vistral-7b-chat") {
        Write-Output "[SKIP] ollama model vistral-7b-chat da co"
    } else {
        Push-Location $LLMDIR
        ollama create vistral-7b-chat -f Modelfile.vistral
        Write-Output "[EXIT create] $LASTEXITCODE"
        Pop-Location
    }
}

Write-Output ""
Write-Output "############ MODEL XONG ############"
ollama list 2>$null | Out-String
Write-Output "=== dung luong models/ ==="
Get-ChildItem "$PROJECT\models" -Directory | ForEach-Object {
    $s = (Get-ChildItem $_.FullName -Recurse -File -EA SilentlyContinue | Measure-Object -Property Length -Sum).Sum
    "{0,-16} {1,8:N2} GB" -f $_.Name, ($s/1GB)
}
Write-Output "MARKER_MODELS_DONE"
