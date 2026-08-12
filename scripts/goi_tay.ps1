$S = "21f10e44220c7ece"
Write-Output "=== ACTION_CALL (nguyen van dau ra) ==="
& adb -s $S shell "am start -a android.intent.action.CALL -d tel:0396130621" 2>&1

Write-Output ""
Write-Output "=== trang thai telecom ngay sau do ==="
Start-Sleep -Seconds 3
& adb -s $S shell "dumpsys telecom | grep -iE 'mCallState|Call id|mState|IN_CALL|DIALING' | head -8" 2>&1

Write-Output ""
Write-Output "=== app dang o truoc man hinh ==="
& adb -s $S shell "dumpsys window | grep -E 'mCurrentFocus|mFocusedApp' | head -3" 2>&1

Write-Output ""
Write-Output "=== quyen CALL_PHONE cua shell ==="
& adb -s $S shell "pm list permissions -g -d | grep -i call" 2>&1 | Select-Object -First 3
