# =====================================================
# Bat xem app Electron co that su goi start_services.ps1 khong.
#   .\scripts\bat_loi_goi_dich_vu.ps1
#
# Chay truoc khi bam VoiceBank-AI.exe. Script doi toi 30s, moi 200ms quet mot
# lan xem co tien trinh powershell nao dang chay start_services.ps1 - do la
# bang chung Electron goi dung duong dan, dung tham so, va ExecutionPolicy
# khong chan. Khong dung/khoi dong dich vu nao nen an toan khi may dang ban.
# =====================================================
param([int]$TimeoutSec = 30)

$deadline = (Get-Date).AddSeconds($TimeoutSec)
Write-Host "Dang cho app goi start_services.ps1 (toi da ${TimeoutSec}s)..."

while ((Get-Date) -lt $deadline) {
    # Khop CA DUONG DAN. Neu chi tim '*start_services.ps1*' thi script nay bat
    # nham chinh no (ten file cua no cung chua chuoi do) va bao thanh cong gia.
    $p = Get-CimInstance Win32_Process |
         Where-Object { $_.Name -like 'powershell*' -and $_.CommandLine -like '*\scripts\start_services.ps1*' }
    if ($p) {
        foreach ($x in $p) {
            Write-Host "[BAT DUOC] PID $($x.ProcessId)"
            Write-Host "  $($x.CommandLine)"
        }
        exit 0
    }
    Start-Sleep -Milliseconds 200
}

Write-Host "[KHONG THAY] Het ${TimeoutSec}s ma khong co powershell nao chay start_services.ps1"
exit 1
