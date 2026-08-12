$S = "21f10e44220c7ece"
adb -s $S shell "input keyevent KEYCODE_WAKEUP" | Out-Null
adb -s $S shell "wm dismiss-keyguard" | Out-Null
Start-Sleep -Milliseconds 600
adb -s $S shell 'am start -a android.intent.action.VIEW -d sms:191' | Out-Null
Start-Sleep -Seconds 4
adb -s $S shell "screencap -p /sdcard/tl.png" | Out-Null
adb -s $S pull /sdcard/tl.png C:/duan/chat-ai/logs/tra_loi_191.png | Out-Null
adb -s $S shell "rm /sdcard/tl.png" | Out-Null
Write-Output "xong"
