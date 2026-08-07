# =====================================================
# Va 2 loi sau khi cai:
#   1. torchcodec / sentence_transformers khong load duoc
#      -> can FFmpeg ban SHARED (co av*.dll), ban dang co la static
#   2. F5-TTS nang fastapi 0.115.6 -> 0.141.1, pha pin cua project
# =====================================================
$ErrorActionPreference = "Continue"
$PROJECT = "C:\duan\chat-ai"
$PY      = "$PROJECT\.venv\python.exe"
$FFDIR   = "C:\ffmpeg-shared"
$URL     = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-n7.1-latest-win64-gpl-shared-7.1.zip"
$ZIP     = "$env:TEMP\ffmpeg-shared.zip"

function Step($n,$m){ Write-Output ""; Write-Output "############ FIX $n : $m ############" }

# ---------- 1. FFmpeg shared ----------
Step 1 "FFmpeg 7.1 shared (co av*.dll)"
if (Test-Path "$FFDIR\bin\avcodec-61.dll") {
    Write-Output "[SKIP] da co FFmpeg shared"
} else {
    Write-Output "Tai $URL ..."
    $ProgressPreference = 'SilentlyContinue'
    Invoke-WebRequest -Uri $URL -OutFile $ZIP -UseBasicParsing
    Write-Output "  tai xong: $([math]::Round((Get-Item $ZIP).Length/1MB,1)) MB"
    if (Test-Path $FFDIR) { Remove-Item -Recurse -Force $FFDIR }
    Expand-Archive -Path $ZIP -DestinationPath "$env:TEMP\ffx" -Force
    $inner = Get-ChildItem "$env:TEMP\ffx" -Directory | Select-Object -First 1
    Move-Item $inner.FullName $FFDIR
    Remove-Item $ZIP,"$env:TEMP\ffx" -Recurse -Force -EA SilentlyContinue
}
Write-Output "=== DLL tim thay ==="
Get-ChildItem "$FFDIR\bin" -Filter "av*.dll" -EA SilentlyContinue | Select-Object -ExpandProperty Name

# ---------- 2. Them vao PATH (User scope - khong can quyen admin) ----------
Step 2 "Them $FFDIR\bin vao PATH"
$cur = [Environment]::GetEnvironmentVariable("Path","User")
if ($cur -notlike "*$FFDIR\bin*") {
    [Environment]::SetEnvironmentVariable("Path", "$FFDIR\bin;$cur", "User")
    Write-Output "[OK] da them vao User PATH (co hieu luc voi tien trinh moi)"
} else {
    Write-Output "[SKIP] da co trong PATH"
}
$env:PATH = "$FFDIR\bin;$env:PATH"

# ---------- 3. Khoi phuc pin cua project ----------
Step 3 "Khoi phuc pin backend/requirements.txt"
& $PY -m pip install --no-input -r "$PROJECT\backend\requirements.txt"
Write-Output "[EXIT] $LASTEXITCODE"

# ---------- 4. Kiem tra lai ----------
Step 4 "Kiem tra lai"
& $PY -c @"
import importlib, sys
for m in ['torchcodec','sentence_transformers','f5_tts','fastapi','torch','faster_whisper','chromadb']:
    try:
        mod = importlib.import_module(m)
        v = getattr(mod, '__version__', '')
        print(f'  OK   {m} {v}')
    except Exception as e:
        print(f'  FAIL {m}: {type(e).__name__}: {str(e)[:110]}')
import torch
print(f'  CUDA: {torch.cuda.is_available()}  GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else "-"}')
"@
Write-Output "MARKER_FIX_DONE"
