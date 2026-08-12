$S = "21f10e44220c7ece"
Write-Output "=== 5 cuoc goi gan nhat (type: 1=goi den 2=goi di 3=nho 5=tu choi) ==="
& adb -s $S shell "content query --uri content://call_log/calls --projection number:type:duration:date --sort 'date DESC LIMIT 5'" 2>&1 | Select-Object -First 6
