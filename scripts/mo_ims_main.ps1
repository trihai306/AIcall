$S = "21f10e44220c7ece"
adb -s $S shell "input keyevent KEYCODE_WAKEUP" | Out-Null
adb -s $S shell "wm dismiss-keyguard" | Out-Null
Start-Sleep -Milliseconds 600

adb -s $S shell "su -c 'am start -n com.samsung.advp.imssettings/.MainActivity'" 2>&1 | Out-String
Start-Sleep -Seconds 4

adb -s $S shell "screencap -p /sdcard/ims2.png" | Out-Null
adb -s $S pull /sdcard/ims2.png C:/duan/chat-ai/logs/ims_main.png | Out-Null
adb -s $S shell "rm /sdcard/ims2.png" | Out-Null

Write-Output "=== dang o truoc ==="
adb -s $S shell "dumpsys window" 2>$null | Select-String -Pattern "mCurrentFocus" | Select-Object -First 1
