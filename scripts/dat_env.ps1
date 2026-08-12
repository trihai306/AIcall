# Dat mot bien trong .env cua may Windows. Thay dong cu neu da co.
#   .\dat_env.ps1 -Ten PHONE_RATE_XUONG -Gia_tri 16000
param([string]$Ten, [string]$Gia_tri)

$ErrorActionPreference = "Stop"
Set-Location C:\duan\chat-ai

$dong = Get-Content .env
if ($dong -match "^$Ten=") {
    $dong = $dong -replace "^$Ten=.*", "$Ten=$Gia_tri"
} else {
    $dong += "$Ten=$Gia_tri"
}
Set-Content -Path .env -Value $dong -Encoding UTF8

Write-Output "--- cac dong PHONE_ hien tai ---"
Select-String -Path .env -Pattern '^PHONE_' | ForEach-Object { $_.Line }
