# Bản PowerShell của training/voice/train.sh - cho Windows không có WSL/bash.
#
#   powershell -ExecutionPolicy Bypass -File training\voice\train.ps1 -VoiceName giong_thu
#   powershell -ExecutionPolicy Bypass -File training\voice\train.ps1 -VoiceName giong_thu -Epochs 10
#
# Yêu cầu: đã chạy prepare_dataset.py, đã có model gốc ViVoice, GPU NVIDIA.
#
# BA LỖI ĐÃ GẶP VÀ ĐƯỢC XỬ LÝ SẴN Ở ĐÂY:
#
# 1. accelerate quá mới -> "AcceleratedOptimizer has no attribute '_modules'".
#    pyproject của F5-TTS chỉ ghi accelerate>=0.33.0 nên pip kéo bản mới nhất.
#    Script tự kiểm tra và hạ về 1.0.1 nếu cần (1.10.1 vẫn lỗi).
#
# 2. Train "xong" sau 2 phút mà không train gì: trainer.py đọc start_update từ
#    checkpoint (540000 của bản ViVoice) rồi tính skipped_epoch vượt số epoch nên
#    bỏ qua toàn bộ vòng lặp, lưu lại y nguyên model gốc. Script tự tạo bản sao
#    có update=0 để dùng làm điểm khởi đầu.
#
# 3. VRAM: backend đang chạy chiếm ~4.5GB, train chiếm ~7GB -> tổng gần tràn
#    12GB và chậm hẳn. Dùng -StopServices để tắt backend trong lúc train.
param(
    [Parameter(Mandatory = $true)][string]$VoiceName,
    [int]$BatchSize     = 3200,      # frames/GPU
    # 2 chu khong phai 8: tren Windows moi worker la mot tien trinh moi hoan
    # chinh (khong fork duoc nhu Linux). Da gap that - 8 worker cua
    # prepare_csv_wavs.py bi ket lai sau khi tien trinh cha chet, giu file
    # raw.arrow, khien lan chay sau bao "OSError: [Errno 22] Invalid argument".
    [int]$NumWorkers    = 2,
    [int]$WarmupUpdates = 500,
    [int]$SaveUpdates   = 2000,
    [int]$LastUpdates   = 1000,
    [int]$Epochs        = 100,       # đo được ~21s/update, 36 update/epoch
    [switch]$StopServices,           # tắt backend để nhường VRAM
    [switch]$Fresh                   # xoá checkpoint cũ, train lại từ model gốc
)
$ErrorActionPreference = "Stop"

$PROJECT   = "C:\duan\chat-ai"
$F5DIR     = "$PROJECT\tools\F5-TTS-Vietnamese"
$PRE_CKPT  = "$PROJECT\models\tts\F5-TTS-Vietnamese-ViVoice\model_last.pt"
$PRE_START = "$PROJECT\models\tts\F5-TTS-Vietnamese-ViVoice\model_finetune_start.pt"
$PRE_VOCAB = "$PROJECT\models\tts\F5-TTS-Vietnamese-ViVoice\vocab.txt"
$OUTDIR    = "$PROJECT\models\tts\finetuned\$VoiceName"
$PY        = "$PROJECT\.venv\python.exe"

$env:CUDA_VISIBLE_DEVICES = "0"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

if (-not (Test-Path $PRE_CKPT)) { throw "Thieu model goc: $PRE_CKPT" }
if (-not (Test-Path "$F5DIR\data\your_dataset")) { throw "Chua co dataset. Chay prepare_dataset.py truoc." }

# --- [0/5] accelerate phải đủ cũ -------------------------------------------
Write-Host "=== [0/5] Kiem tra accelerate ==="
$acc = (& $PY -m pip show accelerate 2>$null | Select-String "^Version:").ToString() -replace "Version:\s*",""
Write-Host "  dang co: $acc"
if ($acc -and [version]($acc -replace "[^\d.]","") -gt [version]"1.0.1") {
    Write-Host "  -> ha ve 1.0.1 (ban moi hon lam vo finetune_cli)"
    & $PY -m pip install --no-input "accelerate==1.0.1" 2>&1 | Select-Object -Last 1
}

if ($StopServices) {
    Write-Host "=== Tat backend de nhuong VRAM ==="
    & powershell -ExecutionPolicy Bypass -File "$PROJECT\scripts\stop_services.ps1" -All 2>&1 | Out-Null
    Start-Sleep -Seconds 5
}

Set-Location $F5DIR

Write-Host "=== [1/5] Chuan bi metadata ==="
& $PY prepare_metadata.py
if ($LASTEXITCODE -ne 0) { throw "prepare_metadata.py loi" }

Write-Host "=== [2/5] Vocab: dung vocab ViVoice ==="
New-Item -ItemType Directory -Force -Path "$F5DIR\data\your_training_dataset" | Out-Null
Copy-Item $PRE_VOCAB "$F5DIR\data\your_training_dataset\vocab.txt" -Force
# Cảnh báo ký tự ngoài vocab. Đặt trong file .py riêng: nhúng thẳng code Python
# vào here-string của PowerShell từng làm vỡ cú pháp (SyntaxError trong log).
& $PY "$PROJECT\scripts\check_vocab.py"

Write-Host "=== [3/5] Trich xuat dac trung ==="
& $PY src\f5_tts\train\datasets\prepare_csv_wavs.py data\your_training_dataset data\your_training_dataset --workers $NumWorkers
if ($LASTEXITCODE -ne 0) { throw "prepare_csv_wavs.py loi" }

Write-Host "=== [4/5] Dat lai bo dem buoc cua checkpoint goc ==="
if (-not (Test-Path $PRE_START)) {
    & $PY "$PROJECT\scripts\reset_update.py"
    if ($LASTEXITCODE -ne 0) { throw "reset_update.py loi" }
} else {
    Write-Host "  da co $PRE_START"
}

# F5-TTS dat num_workers=16 va finetune_cli.py khong cho doi tu dong lenh.
# PyTorch sinh lai toan bo worker o DAU MOI EPOCH; tren Windows moi worker la
# mot tien trinh moi hoan chinh, 16 cai sinh lai moi epoch la qua suc - do thuc
# te: chay tron 2 epoch roi chet o lan sinh thu ba voi
# "DataLoader worker exited unexpectedly". Khong phai thieu RAM (con 41.5 GB).
Write-Host "=== [5/5a] Ha num_workers cho Windows ==="
& $PY "$PROJECT\scripts\va_num_workers.py" --workers 2

# THU MUC CHECKPOINT DUNG CHUNG CHO MOI GIONG - day la mot cai bay.
# --dataset_name ghi cung "your_training_dataset", khong kem $VoiceName, nen moi
# buoi train deu doc/ghi vao cung ckpts\your_training_dataset. Voi --finetune,
# F5 TIEP TUC tu model_last.pt trong do neu co.
#
# Hau qua da do duoc: train giong moi "kiem_thu" tiep tuc tu checkpoint cua
# giong_nam (update 1260), roi voi -Epochs 1 thi logic bo epoch nhay qua het,
# chay 0 buoc, va luu ra ban sao Y HET giong_nam. Log van bao "Train xong".
$CKDIR = "$F5DIR\ckpts\your_training_dataset"
$CKLAST = "$CKDIR\model_last.pt"
# GIONG MOI thi LUON bat dau tu dau. Khong co luat nay thi giong moi ke thua
# trong so cua giong truoc - da do duoc: train "kiem_thu" cho ra ban sao Y HET
# "giong_nam". Giao dien web goi script nay ma khong truyen -Fresh, nen luat
# phai nam O DAY chu khong phai o cho goi.
$LaGiongMoi = -not (Test-Path "$OUTDIR\model_last.pt")
if ($LaGiongMoi -and (Test-Path $CKLAST)) {
    Write-Host "=== [5/5b] Giong MOI '$VoiceName' -> tu dong train tu dau ==="
    $Fresh = $true
}
if ($Fresh -and (Test-Path $CKDIR)) {
    $bak = "$CKDIR" + "_cu_" + (Get-Date -Format "MMdd_HHmmss")
    Write-Host "=== [5/5b] -Fresh: doi ten checkpoint cu -> $bak ==="
    Rename-Item $CKDIR $bak
} elseif (Test-Path $CKLAST) {
    $u = & $PY "$PROJECT\scripts\doc_update_ckpt.py" $CKLAST
    Write-Host "=== [5/5b] TIEP TUC tu checkpoint cu, update = $u ==="
    Write-Host "    Neu -Epochs qua nho so voi so update da co, vong lap se KHONG"
    Write-Host "    chay buoc nao ma van bao thanh cong. Dung -Fresh de train lai tu dau."
}

Write-Host "=== [5/5] Fine-tuning ($Epochs epoch) ==="
& $PY src\f5_tts\train\finetune_cli.py `
    --exp_name F5TTS_Base `
    --dataset_name your_training_dataset `
    --batch_size_per_gpu $BatchSize `
    --epochs $Epochs `
    --num_warmup_updates $WarmupUpdates `
    --save_per_updates $SaveUpdates `
    --last_per_updates $LastUpdates `
    --finetune `
    --log_samples `
    --pretrain $PRE_START
if ($LASTEXITCODE -ne 0) { throw "finetune_cli.py loi" }

Write-Host "=== Dong goi ket qua ==="
New-Item -ItemType Directory -Force -Path $OUTDIR | Out-Null
$ckpt = "$F5DIR\ckpts\your_training_dataset\model_last.pt"
if (-not (Test-Path $ckpt)) { throw "Khong thay checkpoint output: $ckpt" }
Copy-Item $ckpt "$OUTDIR\model_last.pt" -Force
Copy-Item "$F5DIR\data\your_training_dataset\vocab.txt" "$OUTDIR\vocab.txt" -Force

# CHOT CHAN: doi chieu trong so voi model goc. Khong co buoc nay thi mot buoi
# train chay 0 buoc trong Y HET mot buoi thanh cong - co file, du dung luong,
# ngay gio moi. Da mat hai buoi train vi khong kiem (giong_vivos va kiem_thu).
Write-Host "=== Kiem tra trong so CO THAT SU doi khong ==="
& $PY "$PROJECT\scripts\kiem_train_f5_that.py" --goc $PRE_CKPT --moi "$OUTDIR\model_last.pt"
if ($LASTEXITCODE -ne 0) { throw "Buoi train KHONG doi trong so - xem canh bao o tren" }

# Giọng mẫu: KHÔNG lấy bừa file đầu tiên. Chọn đoạn 3-8s, ưu tiên câu mở đầu
# bằng "Dạ" - đo được chữ đó bị đọc sai ~70% khi giọng mẫu không chứa nó.
& $PY "$PROJECT\scripts\pick_ref.py" --dataset "$F5DIR\data\your_dataset" --name $VoiceName

Write-Host ""
Write-Host "============================================"
Write-Host " Train xong. Cap nhat .env de dung giong moi:"
Write-Host "   F5TTS_CKPT_PATH=./models/tts/finetuned/$VoiceName/model_last.pt"
Write-Host "   F5TTS_VOCAB_PATH=./models/tts/finetuned/$VoiceName/vocab.txt"
Write-Host "   F5TTS_REF_AUDIO=./models/tts/ref_voices/$VoiceName.wav"
Write-Host "============================================"
