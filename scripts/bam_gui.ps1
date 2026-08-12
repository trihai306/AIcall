# Bam nut Gui (toa do lay tu anh chup: nut teal goc phai duoi, co huy hieu SIM 2)
$S = "21f10e44220c7ece"

adb -s $S shell "input tap 996 1956" | Out-Null
Start-Sleep -Seconds 5

adb -s $S shell "screencap -p /sdcard/da_gui.png" | Out-Null
adb -s $S pull /sdcard/da_gui.png C:/duan/chat-ai/logs/da_gui.png | Out-Null
adb -s $S shell "rm /sdcard/da_gui.png" | Out-Null
Write-Output "da chup lai man hinh sau khi bam"
