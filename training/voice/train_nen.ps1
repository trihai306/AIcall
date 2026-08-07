# Chạy train.ps1 như một tác vụ ĐỘC LẬP, sống sót qua mọi thứ.
#
# VÌ SAO PHẢI QUA TASK SCHEDULER, không phải Start-Process:
#
# Mọi tiến trình tạo bằng Start-Process từ một phiên SSH đều là CON của phiên đó.
# SSH đóng phiên là Windows giết cả cây. Đã đo bằng thực nghiệm: một lệnh ping
# 300 giây khởi động qua SSH sống bình thường khi phiên còn mở, chết ngay khi
# phiên đóng.
#
# Điều nguy hiểm là nó chết IM LẶNG: Start-Process vẫn trả PID hợp lệ, script
# vẫn in "đã khởi động", file log tạo ra nhưng 0 byte. Nhìn bên ngoài y hệt như
# đang chạy. Ba lần thử trước đều mắc bẫy này.
#
# Task Scheduler chạy tác vụ dưới dịch vụ của Windows, không thuộc phiên đăng
# nhập nào, nên train nhiều giờ vẫn sống dù SSH ngắt, backend restart, hay người
# dùng đăng xuất.
#
#   powershell -ExecutionPolicy Bypass -File training\voice\train_nen.ps1 -VoiceName giong_nam
#   powershell -ExecutionPolicy Bypass -File training\voice\train_nen.ps1 -VoiceName giong_nam -Epochs 60
#
# Xem tiến độ : Get-Content logs\train_giong_<ten>.log -Tail 20 -Wait
# Dừng        : schtasks /end /tn chatai_train_<ten>
# Xoá tác vụ  : schtasks /delete /tn chatai_train_<ten> /f

param(
    [Parameter(Mandatory = $true)][string]$VoiceName,
    [int]$Epochs    = 100,
    [int]$BatchSize = 3200
)

# Continue chứ KHÔNG phải Stop: schtasks ghi thông báo ra stderr trong trường hợp
# bình thường (ví dụ /query một tác vụ chưa tồn tại), mà với Stop thì PowerShell
# coi mọi dòng stderr của lệnh ngoài là lỗi kết thúc. Kiểm $LASTEXITCODE thay vì
# trông vào cơ chế đó.
$ErrorActionPreference = "Continue"
$PROJECT = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$LOGS    = Join-Path $PROJECT "logs"
New-Item -ItemType Directory -Force -Path $LOGS | Out-Null

$log    = Join-Path $LOGS "train_giong_$VoiceName.log"
$bat    = Join-Path $LOGS "_train_giong_$VoiceName.bat"
$script = Join-Path $PSScriptRoot "train.ps1"
$task   = "chatai_train_$VoiceName"

if (-not (Test-Path $script)) { throw "Khong thay $script" }

# Đang chạy rồi thì dừng - hai job train cùng lúc là chắc chắn hết VRAM.
$dang = & schtasks /query /tn $task 2>&1
if ($LASTEXITCODE -eq 0 -and ($dang -join " ") -match "Running") {
    throw "Tac vu '$task' dang chay. Dung truoc bang: schtasks /end /tn $task"
}

# Dọn tiến trình treo từ lần chạy trước. Khi job train chết giữa chừng, các
# worker của prepare_csv_wavs.py và của DataLoader KHÔNG chết theo - đã đo được
# 18 tiến trình còn sống sau một lần gãy. Chúng giữ file raw.arrow, khiến lần
# chạy sau báo "OSError: [Errno 22] Invalid argument" - một thông báo chẳng liên
# quan gì tới nguyên nhân thật, rất dễ đi mò nhầm hướng.
$treo = Get-Process python -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -like "$PROJECT*" }
if ($treo) {
    Write-Output "Don $($treo.Count) tien trinh python treo tu lan chay truoc..."
    $treo | ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 5
}

# raw.arrow do prepare_csv_wavs.py dung lai tu metadata.csv moi lan chay. Bo ban
# cu di: neu no dang o trang thai do dang thi lan chay sau mo khong duoc.
$arrow = Join-Path $PROJECT "tools\F5-TTS-Vietnamese\data\your_training_dataset\raw.arrow"
if (Test-Path $arrow) { Remove-Item $arrow -Force -ErrorAction SilentlyContinue }

# Viết .bat thay vì nhét lệnh dài vào /tr: tham số /tr của schtasks giới hạn
# 261 ký tự và rất khó thoát dấu ngoặc cho đúng.
# cmd chuyển hướng ở mức hệ điều hành, tránh bẫy $ErrorActionPreference='Stop'
# của train.ps1 - python ghi thanh tqdm ra stderr, gộp bằng '*>&1' của PowerShell
# là dòng tqdm đầu tiên bị coi là lỗi và script dừng ngay.
@"
@echo off
cd /d "$PROJECT"
powershell -ExecutionPolicy Bypass -NoProfile -File "$script" -VoiceName $VoiceName -Epochs $Epochs -BatchSize $BatchSize > "$log" 2>&1
"@ | Out-File -FilePath $bat -Encoding ascii

schtasks /delete /tn $task /f 2>$null | Out-Null
# /sc once /st 23:59 chỉ để thoả cú pháp - chạy ngay bằng /run ở dưới.
# /rl highest để có đủ quyền đọc ghi trong thư mục dự án.
schtasks /create /tn $task /tr "`"$bat`"" /sc once /st 23:59 /f /rl highest | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Tao tac vu that bai (exit $LASTEXITCODE)" }

schtasks /run /tn $task | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Chay tac vu that bai (exit $LASTEXITCODE)" }

Write-Output "Da giao cho Task Scheduler:"
Write-Output "  tac vu : $task"
Write-Output "  log    : $log"
Write-Output ""
Write-Output "Xem tien do : Get-Content `"$log`" -Tail 20 -Wait"
Write-Output "Dung        : schtasks /end /tn $task"
