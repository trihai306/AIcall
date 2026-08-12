# Bam "Send" tren hop thoai xac nhan (KHONG tich "Remember my choice").
$S = "21f10e44220c7ece"

adb -s $S shell "input tap 787 1287" | Out-Null
Start-Sleep -Seconds 8

adb -s $S shell "screencap -p /sdcard/kq.png" | Out-Null
adb -s $S pull /sdcard/kq.png C:/duan/chat-ai/logs/kq_gui.png | Out-Null
adb -s $S shell "rm /sdcard/kq.png" | Out-Null
Write-Output "xong"
