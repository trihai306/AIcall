# Mo app cau hinh IMS cua Samsung - khong sua gi, chi xem no cho bat gi.
$S = "21f10e44220c7ece"
adb -s $S shell "input keyevent KEYCODE_WAKEUP" | Out-Null
adb -s $S shell "wm dismiss-keyguard" | Out-Null
Start-Sleep -Milliseconds 600

Write-Output "=== cac activity cua app IMS settings ==="
adb -s $S shell "su -c 'dumpsys package com.samsung.advp.imssettings'" 2>$null |
    Select-String -Pattern "^\s+[0-9a-f]+ com.samsung.advp.imssettings/" |
    Select-Object -First 12

adb -s $S shell "monkey -p com.samsung.advp.imssettings -c android.intent.category.LAUNCHER 1" 2>&1 | Out-Null
Start-Sleep -Seconds 4

adb -s $S shell "screencap -p /sdcard/ims.png" | Out-Null
adb -s $S pull /sdcard/ims.png C:/duan/chat-ai/logs/ims_settings.png | Out-Null
adb -s $S shell "rm /sdcard/ims.png" | Out-Null

Write-Output ""
Write-Output "=== man hinh dang o truoc ==="
adb -s $S shell "dumpsys window" 2>$null | Select-String -Pattern "mCurrentFocus" | Select-Object -First 1
