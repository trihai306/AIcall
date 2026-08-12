# Mo khung soan tin HDCALL -> 191 va chup man hinh de tim nut Gui.
# KHONG tu bam gui o buoc nay - phai nhin man hinh xac dinh dung nut truoc.
$S = "21f10e44220c7ece"

adb -s $S shell "input keyevent KEYCODE_WAKEUP" | Out-Null
adb -s $S shell "wm dismiss-keyguard" | Out-Null
Start-Sleep -Milliseconds 800

# Mo khung soan tin voi noi dung dien san
adb -s $S shell 'am start -a android.intent.action.SENDTO -d sms:191 --es sms_body "HDCALL"' 2>&1 | Out-String
Start-Sleep -Seconds 3

adb -s $S shell "screencap -p /sdcard/soan_tin.png" | Out-Null
adb -s $S pull /sdcard/soan_tin.png C:/duan/chat-ai/logs/soan_tin.png 2>&1 | Out-String
adb -s $S shell "rm /sdcard/soan_tin.png" | Out-Null

Write-Output "--- kich thuoc man hinh ---"
adb -s $S shell "wm size"
Write-Output "--- app dang o truoc ---"
adb -s $S shell "dumpsys window" 2>$null | Select-String -Pattern "mCurrentFocus" | Select-Object -First 2
