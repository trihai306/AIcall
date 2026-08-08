# =====================================================
# AI Banking Call System - khoi dong dich vu (Windows)
#   .\scripts\start_services.ps1 -Detached
#
# Chay nen bang cach: ghi 1 file .bat roi nho Win32_Process.Create khoi chay.
# Lam vay vi (a) tien trinh khong con la con cua phien SSH nen khong bi giet,
# (b) chuyen huong log nam trong .bat nen khong vo vi long dau nhay.
#
# KHONG co -Detached thi chay foreground kem --reload (che do dev). Luu y:
# F5-TTS mat 2-3 phut moi nap xong, ma --reload restart ca app moi khi co file
# thay doi -> chi can scp mot file la mat tieng them 2-3 phut nua, health bao
# "tts":"not_loaded" va moi luot deu cam. Da mat kha nhieu thoi gian vi cho nay.
# Vi vay --reload chi theo doi thu muc backend, khong theo doi scripts/ hay
# training/. Muon chay that thi luon dung -Detached.
#
# TU KHOI DONG LAI KHI CODE MOI HON TIEN TRINH
# Truoc day cho nay chi kiem "co uvicorn dang chay khong" roi bo qua. Cong voi
# viec dong app KHONG dung dich vu nen (main.js window-all-closed, de khoi nap
# lai F5-TTS 2-3 phut), chuoi thanh ra:
#
#     sua code backend/ -> mo lai app -> script thay uvicorn cu con song
#       -> in "[OK] Backend dang chay" -> KHONG NAP CODE MOI
#
# Hien ra dung thanh "goi tu app cam tieng ma scripts/goi_va_noi.py van OK":
# script nap code moi nhat tu dia moi lan chay, app thi dung tien trinh cu.
# /api/health KHONG lo ra dieu nay - no van bao tts:loaded, stt:ok nhu thuong.
# Da mat mot buoi truy nham vao logic goi (precise_call_state, giu_duong_tiem)
# trong khi logic do da dung tu lau.
#
# Nay: so gio khoi dong tien trinh voi mtime moi nhat cua code no nap. Cu hon
# thi dung han roi khoi dong lai. Dung -Restart de ep, -NoRestart de cam.
# KHONG restart khi may dang co cuoc goi - hoi /api/devices/voice/status truoc.
# =====================================================
param(
    [switch]$Detached,
    [int]$Port = 8100,
    [int]$WhisperPort = 8178,
    [switch]$Restart,        # ep khoi dong lai du code khong doi
    [switch]$NoRestart       # cam khoi dong lai du code da doi (giu hanh vi cu)
)
$ErrorActionPreference = "Continue"
$PROJECT = Split-Path -Parent $PSScriptRoot
$PY      = "$PROJECT\.venv\python.exe"
# PhoWhisper-MEDIUM, khong phai small. Do bang scripts/so_stt_small_medium.py
# tren cau qua 8kHz + AMR-NB + do nghieng pho cua cuoc goi that:
#     small   CER 0.229   giu 5/7 tu khoa   0.12s/cau
#     medium  CER 0.011   giu 7/7 tu khoa   0.24s/cau
# CER giam 21 lan, gia chi +120ms moi luot. Dung ha ve small de "cho nhanh".
$CT2DIR  = "$PROJECT\models\phowhisper\PhoWhisper-medium-ct2"
$LOGS    = "$PROJECT\logs"
$RUN     = "$PROJECT\logs\_run"
New-Item -ItemType Directory -Force -Path $LOGS,$RUN | Out-Null

function Start-Detached($Name, $Body) {
    $bat = "$RUN\$Name.bat"
    @(
        "@echo off",
        "chcp 65001 > nul",
        "set PYTHONUTF8=1",
        "set PYTHONIOENCODING=utf-8",
        "set PATH=C:\ffmpeg-shared\bin;%PATH%",
        # -1 = giữ model trong VRAM vĩnh viễn. Mặc định Ollama đẩy ra sau 5 phút,
        # nên lượt gọi đầu sau lúc nghỉ phải nạp lại 2.1GB -> TTFT vọt lên ~1700ms
        # thay vì ~515ms.
        "set OLLAMA_KEEP_ALIVE=-1",
        # 1 = CHI giu dung mot model. Chu thich cu o day noi "may nay VRAM du
        # (4.5/12GB) nen giu luon" - SAI tu khi them F5-TTS va model thu hai.
        #
        # Do that 08-08: qwen2.5:7b (5.1GB) + qwen2.5:3b (2.4GB, khong ma chay
        # that nao dung) cung bi ghim Forever tren card 11.9GB. F5-TTS gianh
        # cho trong luc goi -> Ollama day 7B ra. Cuoc sau nap lai 5.1GB TU O
        # CUNG = ~6 giay, roi tron vao luot dau tien khach hoi that.
        # Bo 3B ra thi 7B tru duoc qua ca cuoc goi, cu 6 giay bien mat
        # (cong_cu_ms cao nhat 6294ms -> 393ms).
        "set OLLAMA_MAX_LOADED_MODELS=1",
        # 1, KHONG phai 2. Do 08-08 tren 2 cuoc goi song song:
        #   NUM_PARALLEL=2 -> TTFA cao nhat 7512 / 8270 ms
        #   NUM_PARALLEL=1 -> TTFA cao nhat 2646 / 2121 ms, trung vi cung tot hon
        # Hai khe ngu canh tren card 11.9GB lam duoi tre vot gap ba ma dinh VRAM
        # khong giam (11453 vs 11400 MiB). Mot khe thi hai cuoc xep hang o Ollama,
        # nhung moi lenh LLM chi 200-600ms nen cho khong dang ke.
        "set OLLAMA_NUM_PARALLEL=1",
        "cd /d `"$PROJECT`"",
        $Body
    ) | Set-Content -Path $bat -Encoding ascii
    $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create `
         -Arguments @{ CommandLine = "cmd.exe /c `"$bat`""; CurrentDirectory = $PROJECT }
    return $r.ProcessId
}

# --- phat hien code moi hon tien trinh dang chay -----------------------------

<#
Thoi diem sua gan nhat trong danh sach duong dan (thu muc thi quet *.py de quy).
Tinh ca .env: backend doc settings luc NAP MODULE, nen sua .env ma khong khoi
dong lai thi gia tri moi khong bao gio co hieu luc - da mac o PHONE_SILENCE_END_MS.
Bo qua __pycache__: .pyc sinh ra sau khi tien trinh chay nen luon "moi hon",
tinh vao la lan nao cung bao code cu.
#>
function Get-CodeMtime([string[]]$Paths) {
    $moi = $null
    foreach ($p in $Paths) {
        if (-not (Test-Path $p)) { continue }
        $item = Get-Item $p
        if ($item.PSIsContainer) {
            $f = Get-ChildItem -Path $p -Recurse -File -Filter *.py -EA SilentlyContinue |
                 Where-Object { $_.FullName -notlike '*__pycache__*' } |
                 Sort-Object LastWriteTime -Descending | Select-Object -First 1
            if ($f -and (-not $moi -or $f.LastWriteTime -gt $moi)) { $moi = $f.LastWriteTime }
        } elseif (-not $moi -or $item.LastWriteTime -gt $moi) {
            $moi = $item.LastWriteTime
        }
    }
    return $moi
}

<#
Co cuoc goi nao dang chay khong? Khoi dong lai giua cuoc goi la cat ngang khach,
va nang hon: mot chien dich tu dong dang chay nen se chet khi nguoi dung chi
vo tinh mo app. Hoi backend; hoi khong duoc thi coi nhu KHONG co cuoc goi -
backend da treo thi restart la viec dung.
#>
function Test-DangGoi([int]$Port) {
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/devices/voice/status" `
                               -TimeoutSec 3 -EA Stop
        $dang = @($r.calls | Where-Object { $_.running })
        if ($dang.Count -gt 0) { return $dang.Count }
    } catch { }
    return 0
}

<#
Dung tien trinh roi CHO NO CHET HAN va cho cong nha ra.
Khong cho thi doan khoi dong ngay ben duoi thay cong con ban -> uvicorn khong
bind duoc -> chet lang le, va lan sau lai thay "khong co backend" nen khoi dong
lai. Dung loi ma stop_backend.py da ghi lai.
#>
function Stop-AndWait($Proc, [int]$Port, [string]$Nhan) {
    Write-Host "[..] Dung $Nhan cu (PID $($Proc.ProcessId)) ..."
    try { Stop-Process -Id $Proc.ProcessId -Force -EA Stop }
    catch { Write-Host "     [CANH BAO] khong dung duoc: $($_.Exception.Message)"; return $false }
    for ($i = 0; $i -lt 40; $i++) {          # toi da 10 giay
        Start-Sleep -Milliseconds 250
        $song = Get-Process -Id $Proc.ProcessId -EA SilentlyContinue
        $cong = Get-NetTCPConnection -State Listen -LocalPort $Port -EA SilentlyContinue
        if (-not $song -and -not $cong) {
            Write-Host "     da dung han, cong $Port da nha"
            return $true
        }
    }
    Write-Host "     [CANH BAO] sau 10s cong $Port van chua nha - khoi dong co the that bai"
    return $false
}

<#
Tra ve $true neu can khoi dong lai. In ra LY DO chu khong im lang: nguoi dung
phai biet vi sao dang phai cho 2-3 phut nap lai F5-TTS.

$ChiCanhBao = chi bao "dang chay code cu" chu KHONG tu dung. Dung cho PhoWhisper:
whisper_server/ gan nhu khong bao gio sua, trong khi tu y giet no thi hong buoi
chuan bi dataset dang chay (prepare_dataset.py goi vao :8178). Tu khoi dong lai
o do la them rui ro moi de chua mot benh chua tung xay ra. Muon ep thi -Restart.
#>
function Test-CanNapLai($Proc, [string[]]$DuongDanCode, [string]$Nhan,
                        [switch]$ChiCanhBao) {
    $moi = Get-CodeMtime $DuongDanCode
    $cu  = $Proc.CreationDate
    if ($Restart) {
        Write-Host "[!!] $Nhan : co -Restart, khoi dong lai theo yeu cau"
        return $true
    }
    if ($moi -and $moi -gt $cu) {
        $khiNao = "khoi dong $($cu.ToString('MM-dd HH:mm:ss')), code sua $($moi.ToString('MM-dd HH:mm:ss'))"
        if ($NoRestart) {
            Write-Host "[!!] $Nhan DANG CHAY CODE CU ($khiNao) - co -NoRestart nen giu nguyen"
            return $false
        }
        if ($ChiCanhBao) {
            Write-Host "[!!] $Nhan DANG CHAY CODE CU ($khiNao)"
            Write-Host "     Khong tu khoi dong lai (co the dang co viec dung no)."
            Write-Host "     Muon nap code moi: chay lai script nay kem -Restart"
            return $false
        }
        Write-Host "[!!] $Nhan dang chay CODE CU ($khiNao)"
        return $true
    }
    Write-Host "[OK] $Nhan dang chay (PID $($Proc.ProcessId), khoi dong $($cu.ToString('MM-dd HH:mm')), code khong doi)"
    return $false
}

Write-Host "Project: $PROJECT   Port: $Port"

# --- 0. Khoa xung san GPU ---
# GPU tut ve 277-600MHz khi ranh (max 3090MHz). Moi luot goi cach nhau vai giay
# nen lan nao cung phai leo xung lai: do duoc TTS 687-691ms thay vi 513-537ms.
# Khoa san 1500MHz chi an dien khi CO TAI (luc ranh van ve P8/13W), nen khong
# ton them dien. Go bo: nvidia-smi --reset-gpu-clocks
try {
    nvidia-smi --lock-gpu-clocks=1500,3090 2>&1 | Out-Null
    $c = (nvidia-smi --query-gpu=clocks.max.sm --format=csv,noheader,nounits)
    Write-Host "[OK] Da khoa xung GPU san 1500MHz (max $c MHz)"
} catch {
    Write-Host "[--] Khong khoa duoc xung GPU (bo qua, chi cham hon ~160ms/luot)"
}

# --- 1. Ollama ---
if (Get-Process ollama -EA SilentlyContinue) {
    Write-Host "[OK] Ollama dang chay san"
} else {
    Start-Detached "ollama" "ollama serve > `"$LOGS\ollama.log`" 2>&1" | Out-Null
    Start-Sleep -Seconds 3
    Write-Host "[OK] Ollama da khoi dong"
}

# CANH BAO neu bien Ollama chua dat o MUC MAY.
#
# Nhung dong "set OLLAMA_*" trong Start-Detached ben tren CHI an khi chinh script
# nay khoi dong Ollama. Thuc te app khay he thong (ollama app.exe) thuong dung
# Ollama len TRUOC, luc do cac dong set do khong bao gio cham toi no - da mat
# ca buoi 08-08 moi phat hien NUM_PARALLEL chua tung co tac dung.
#
# Dat o muc may thi an bat ke ai khoi dong Ollama. Doi bien phai TAT HAN ollama
# (ca "ollama app") roi bat lai moi ap dung.
$canCo = @{
    "OLLAMA_FLASH_ATTENTION"   = "1"        # nhanh hon VA cho phep nen KV cache
    "OLLAMA_KV_CACHE_TYPE"     = "q8_0"     # nen KV cache: dinh 1 cuoc 10257 -> 8610 MiB
    "OLLAMA_CONTEXT_LENGTH"    = "2048"     # app chi bao gio xin 2048, dung tra tien 4096
    "OLLAMA_NUM_PARALLEL"      = "1"        # xem chu thich o Start-Detached
    "OLLAMA_MAX_LOADED_MODELS" = "1"
}
$thieu = @()
foreach ($k in $canCo.Keys) {
    if ([Environment]::GetEnvironmentVariable($k, "Machine") -ne $canCo[$k]) {
        $thieu += "$k=$($canCo[$k])"
    }
}
if ($thieu.Count) {
    Write-Host "[!!] Bien Ollama chua dat dung o muc may: $($thieu -join ', ')"
    Write-Host "     Dat bang PowerShell quyen admin, roi TAT HAN ollama va bat lai:"
    foreach ($t in $thieu) {
        $kv = $t -split '=', 2
        Write-Host "       [Environment]::SetEnvironmentVariable('$($kv[0])','$($kv[1])','Machine')"
    }
}

# Day model THUA ra khoi VRAM. OLLAMA_MAX_LOADED_MODELS chi an tu lan Ollama
# khoi dong lai; model dang ghim san van nam do, nen phai don bang tay o day.
# Xem chu thich o Start-Detached ben tren de biet vi sao ton tai buoc nay.
$modelChinh = ""
if (Test-Path "$PROJECT\.env") {
    $d = Select-String -Path "$PROJECT\.env" -Pattern '^\s*OLLAMA_MODEL\s*=\s*(.+?)\s*$' -EA SilentlyContinue
    if ($d) { $modelChinh = $d.Matches[0].Groups[1].Value.Trim() }
}
if ($modelChinh) {
    $dangNap = @(ollama ps 2>$null | Select-Object -Skip 1 |
                 ForEach-Object { ($_ -split '\s+')[0] } | Where-Object { $_ })
    foreach ($m in $dangNap) {
        if ($m -ne $modelChinh) {
            ollama stop $m 2>$null | Out-Null
            Write-Host "[OK] Da day model thua '$m' khoi VRAM (chi giu '$modelChinh')"
        }
    }
} else {
    Write-Host "[--] Khong doc duoc OLLAMA_MODEL tu .env, bo qua buoc don VRAM"
}

# --- 2. PhoWhisper STT ---
if (-not (Test-Path "$CT2DIR\model.bin")) {
    Write-Host "[ERROR] Thieu model PhoWhisper CT2: $CT2DIR"; exit 1
}
$pho = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -EA SilentlyContinue |
       Where-Object { $_.CommandLine -like "*pho_server.py*" }
if ($pho -and (Test-CanNapLai $pho @("$PROJECT\whisper_server") "PhoWhisper" -ChiCanhBao)) {
    if (Stop-AndWait $pho $WhisperPort "PhoWhisper") { $pho = $null }
}
if ($pho) {
    # Test-CanNapLai da in dong trang thai roi, khong in lai.
} else {
    # TAT VAD Silero cua faster-whisper. No cat SACH nhung cau ngan that: do
    # tren ban ghi cuoc goi that (scripts/do_tat_vad_whisper.py), doan "alo alo"
    # 820ms co tieng ro rang bi tra ve RONG khi bat VAD, tat thi doc duoc.
    # Khong so bia chu - da do ca chieu nguoc lai: 7 doan chi co nen, va 4 muc
    # tap am chong them (dinh 328 -> 4915), TAT VAD deu tra RONG. Bo loc
    # `_dang_ngo` trong stt_service (avg_logprob + no_speech_prob) dang ganh
    # viec chong bia, khong can VAD lam nua.
    #
    # PHAI dung dang co ngoac `set "VAR=0"`. Viet `set VAR=0 && ...` thi cmd gan
    # ca DAU CACH truoc && vao gia tri -> "0 " khong khop voi ("0","false") nen
    # VAD van BAT ma khong bao gi. Da mac dung loi nay, chi lo ra vi /health in
    # ra vad_filter. Kiem lai bang /health sau moi lan doi, dung tin log khoi dong.
    $p1 = Start-Detached "phowhisper" "set `"STT_VAD_FILTER=0`" && `"$PY`" `"$PROJECT\whisper_server\pho_server.py`" --model `"$CT2DIR`" --port $WhisperPort > `"$LOGS\pho-server.log`" 2>&1"
    Write-Host "[OK] PhoWhisper dang khoi dong (cmd PID $p1) -> :$WhisperPort"
}

# --- 3. FastAPI backend ---
$be = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -EA SilentlyContinue |
      Where-Object { $_.CommandLine -like "*uvicorn*backend.main*" }
if ($be -and (Test-CanNapLai $be @("$PROJECT\backend", "$PROJECT\.env") "Backend")) {
    # Cat ngang mot cuoc goi dang chay la thiet hai that: khach dang nghe thi mat
    # tieng, con mot chien dich tu dong thi chet ca luot quay so - chi vi nguoi
    # dung vo tinh mo app. Tha chay code cu them mot luc con hon.
    $dangGoi = Test-DangGoi $Port
    if ($dangGoi -gt 0) {
        Write-Host "[!!] DANG CO $dangGoi CUOC GOI - KHONG khoi dong lai bay gio."
        Write-Host "     Backend van chay CODE CU. Goi xong hay chay lai script nay,"
        Write-Host "     hoac menu He thong > Khoi dong lai dich vu trong app."
    } elseif (Stop-AndWait $be $Port "Backend") {
        $be = $null
    }
}
if ($be) {
    # Test-CanNapLai da in dong trang thai roi, khong in lai.
} elseif ($Detached) {
    $p2 = Start-Detached "backend" "`"$PY`" -m uvicorn backend.main:app --host 0.0.0.0 --port $Port --log-level info > `"$LOGS\backend.log`" 2>&1"
    Write-Host "[OK] Backend dang khoi dong (cmd PID $p2) -> http://localhost:$Port"
    Write-Host "     Log: $LOGS\backend.log"
} else {
    # --reload-dir backend: khong co no thi uvicorn theo doi ca cay thu muc, va
    # moi lan scp mot script vao scripts/ la nap lai F5-TTS mat them 2-3 phut.
    & $PY -m uvicorn backend.main:app --host 0.0.0.0 --port $Port `
        --reload --reload-dir backend --log-level info
}
