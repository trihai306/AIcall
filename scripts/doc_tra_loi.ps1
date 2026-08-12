# Doc tin tra loi tu 191 va kiem lai co VoLTE cua nha mang.
$S = "21f10e44220c7ece"

Write-Output "=== TIN NHAN DEN GAN DAY ==="
adb -s $S shell "su -c 'content query --uri content://sms/inbox --projection address:body:date --sort \"date DESC limit 5\"'" 2>&1 | Out-String

Write-Output ""
Write-Output "=== CO VoLTE CUA NHA MANG (sau khi dang ky) ==="
adb -s $S shell "dumpsys carrier_config" 2>$null | Select-String -Pattern "carrier_volte_available_bool|carrier_volte_provisioned_bool" | Select-Object -First 4

Write-Output ""
Write-Output "=== IMS DA DANG KY CHUA ==="
adb -s $S shell "dumpsys telephony.registry" 2>$null | Select-String -Pattern "mVoLteServiceState|mApnBlackList" | Select-Object -First 3

Write-Output ""
Write-Output "=== MANG DANG BAT ==="
adb -s $S shell "getprop gsm.network.type"
