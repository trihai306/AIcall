# Do tim control khuech dai tren duong tiem tieng, de khoi phai ha muc tin hieu.
$ErrorActionPreference = "Continue"
$S = "21f10e44220c7ece"

Write-Output "=== control co chua Gain/Volume ==="
adb -s $S shell "tinymix" 2>$null | Select-String -Pattern "Gain|Volume|VOL" | Select-Object -First 40

Write-Output ""
Write-Output "=== control lien quan SPUS / SIFS / UAIF ==="
adb -s $S shell "tinymix" 2>$null | Select-String -Pattern "SPUS|SIFS|UAIF" | Select-Object -First 40

Write-Output ""
Write-Output "=== tong so control ==="
(adb -s $S shell "tinymix" 2>$null | Measure-Object -Line).Lines
