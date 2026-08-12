# Bật cách 3 cho cuộc gọi thật: đổi PHONE_RATE_XUONG về 8000 và bật
# PHONE_TANG_TUAN_HOAN. Sao lưu .env trước khi sửa.
#
# Phải THAY dòng PHONE_RATE_XUONG có sẵn chứ không nối thêm - hai dòng trùng
# tên trong .env thì không rõ dòng nào thắng.

$ErrorActionPreference = "Stop"
Set-Location C:\duan\chat-ai

$sao = ".env.truoc_tuan_hoan"
if (-not (Test-Path $sao)) {
    Copy-Item .env $sao
    Write-Output "[OK] Da sao luu .env -> $sao"
} else {
    Write-Output "[--] Ban sao luu da co tu truoc, giu nguyen"
}

$dong = Get-Content .env

# 1. Thay dong rate_xuong
if ($dong -match '^PHONE_RATE_XUONG=') {
    $dong = $dong -replace '^PHONE_RATE_XUONG=.*', 'PHONE_RATE_XUONG=8000'
    Write-Output "[OK] PHONE_RATE_XUONG -> 8000 (thay dong cu)"
} else {
    $dong += 'PHONE_RATE_XUONG=8000'
    Write-Output "[OK] PHONE_RATE_XUONG=8000 (them moi)"
}

# 2. Bat tang tuan hoan
if ($dong -match '^PHONE_TANG_TUAN_HOAN=') {
    $dong = $dong -replace '^PHONE_TANG_TUAN_HOAN=.*', 'PHONE_TANG_TUAN_HOAN=true'
    Write-Output "[OK] PHONE_TANG_TUAN_HOAN -> true (thay dong cu)"
} else {
    $dong += 'PHONE_TANG_TUAN_HOAN=true'
    Write-Output "[OK] PHONE_TANG_TUAN_HOAN=true (them moi)"
}

Set-Content -Path .env -Value $dong -Encoding UTF8

Write-Output ""
Write-Output "--- cac dong PHONE_ sau khi sua ---"
Select-String -Path .env -Pattern '^PHONE_' | ForEach-Object { $_.Line }
