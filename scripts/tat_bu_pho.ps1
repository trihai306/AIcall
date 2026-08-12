# Tắt bộ bù phổ `toi_uu_cho_thoai` - nghi phạm gây tiếng "dè".
# Chống vỡ tiếng KHÔNG mất: nhánh else vẫn chạy `chuan_muc_thoai`.
$ErrorActionPreference = "Stop"
Set-Location C:\duan\chat-ai

$dong = Get-Content .env
if ($dong -match '^PHONE_TOI_UU_AM=') {
    $dong = $dong -replace '^PHONE_TOI_UU_AM=.*', 'PHONE_TOI_UU_AM=false'
} else {
    $dong += 'PHONE_TOI_UU_AM=false'
}
Set-Content -Path .env -Value $dong -Encoding UTF8

Write-Output "--- cac dong PHONE_ hien tai ---"
Select-String -Path .env -Pattern '^PHONE_' | ForEach-Object { $_.Line }
