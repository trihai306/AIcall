# Ha muc tin hieu xuong dien thoai. Tham so truyen vao: muc dBFS (vd -26).
param([string]$Muc = "-26")

$ErrorActionPreference = "Stop"
Set-Location C:\duan\chat-ai

$dong = Get-Content .env
if ($dong -match '^PHONE_MUC_DBFS=') {
    $dong = $dong -replace '^PHONE_MUC_DBFS=.*', "PHONE_MUC_DBFS=$Muc"
} else {
    $dong += "PHONE_MUC_DBFS=$Muc"
}
Set-Content -Path .env -Value $dong -Encoding UTF8

Write-Output "--- cac dong PHONE_ hien tai ---"
Select-String -Path .env -Pattern '^PHONE_' | ForEach-Object { $_.Line }
