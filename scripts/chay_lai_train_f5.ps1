# =====================================================
# Khoi dong lai fine-tune F5-TTS, chay NEN (khong chet theo phien SSH).
#
#   powershell -ExecutionPolicy Bypass -File scripts\chay_lai_train_f5.ps1
#
# Khac lenh cu o hai cho, va chi hai cho do:
#   --save_per_updates  2000 -> 500
#   --last_per_updates  1000 -> 200
# Ly do: lan truoc chay 11 phut roi dut giua chung ma CHUA CO checkpoint nao,
# nen mat trang. Luu day hon thi lan sau con cho de chay tiep.
#
# Cach chay nen giong start_services.ps1: ghi 1 file .bat roi nho
# Win32_Process.Create khoi chay, de tien trinh khong con la con cua phien SSH.
# =====================================================
param(
    [int]$SavePerUpdates = 500,
    [int]$LastPerUpdates = 200
)
$ErrorActionPreference = "Continue"
$PROJECT = Split-Path -Parent $PSScriptRoot
$F5      = "$PROJECT\tools\F5-TTS-Vietnamese"
$PY      = "$PROJECT\.venv\python.exe"
$RUN     = "$PROJECT\logs\_run"
$LOG     = "$PROJECT\logs\train_f5.log"
New-Item -ItemType Directory -Force -Path $RUN | Out-Null

# Khong khoi dong khi con mot ban dang chay - hai ban cung ghi mot thu muc ckpts
# la hong ca hai.
$dang = Get-CimInstance Win32_Process -Filter "Name like '%python%'" |
        Where-Object { $_.CommandLine -like '*finetune_cli*' }
if ($dang) {
    Write-Host "[BO QUA] Da co ban dang chay, PID $($dang.ProcessId)"
    exit 1
}

$vram = (nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader)
Write-Host "VRAM truoc khi chay: $vram"

$args = @(
    "src\f5_tts\train\finetune_cli.py",
    "--exp_name F5TTS_Base",
    "--dataset_name your_training_dataset",
    "--batch_size_per_gpu 3200",
    "--epochs 30",
    "--num_warmup_updates 500",
    "--save_per_updates $SavePerUpdates",
    "--last_per_updates $LastPerUpdates",
    "--finetune",
    "--log_samples",
    "--pretrain $PROJECT\models\tts\F5-TTS-Vietnamese-ViVoice\model_finetune_start.pt"
) -join " "

$bat = "$RUN\train_f5.bat"
@(
    "@echo off",
    "chcp 65001 > nul",
    "set PYTHONUTF8=1",
    "set PYTHONIOENCODING=utf-8",
    "cd /d `"$F5`"",
    "`"$PY`" $args > `"$LOG`" 2>&1"
) | Set-Content -Path $bat -Encoding ascii

$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create `
     -Arguments @{ CommandLine = "cmd.exe /c `"$bat`""; CurrentDirectory = $F5 }
Write-Host "[OK] Da khoi chay (cmd PID $($r.ProcessId))"
Write-Host "     save_per_updates=$SavePerUpdates  last_per_updates=$LastPerUpdates"
Write-Host "     Log: $LOG"
Write-Host "     Checkpoint: $F5\ckpts\your_training_dataset"
