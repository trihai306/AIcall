# Cham vao mot toa do roi chup lai man hinh. Dung de dieu huong tung buoc.
#   .\cham.ps1 -X 444 -Y 411 -Ten buoc1
param([int]$X, [int]$Y, [string]$Ten = "buoc", [int]$Cho = 3)

$S = "21f10e44220c7ece"
if ($X -gt 0 -or $Y -gt 0) {
    adb -s $S shell "input tap $X $Y" | Out-Null
    Start-Sleep -Seconds $Cho
}
adb -s $S shell "screencap -p /sdcard/b.png" | Out-Null
adb -s $S pull /sdcard/b.png "C:/duan/chat-ai/logs/$Ten.png" | Out-Null
adb -s $S shell "rm /sdcard/b.png" | Out-Null
adb -s $S shell "dumpsys window" 2>$null | Select-String -Pattern "mCurrentFocus" | Select-Object -First 1
