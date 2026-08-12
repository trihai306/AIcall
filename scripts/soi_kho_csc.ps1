# Xem may con du lieu CSC/OMC nao khong. Neu co nhieu CSC thi doi duoc bang
# ma *#272*IMEI# ma KHONG phai flash.
$S = "21f10e44220c7ece"

foreach ($d in @("/system/csc", "/odm/etc/csc", "/optics/configs/carriers",
                 "/prism/etc", "/omc", "/vendor/omc", "/system/omc",
                 "/efs/carrier", "/data/omc")) {
    $r = adb -s $S shell "su -c 'ls -1 $d 2>/dev/null | head -12'" 2>$null
    if ($r) {
        Write-Output "=== $d ==="
        $r
        Write-Output ""
    }
}

Write-Output "=== file cau hinh CSC neu co ==="
adb -s $S shell "su -c 'find /system /odm /optics /prism /omc -maxdepth 3 -iname \"*cscfeature*\" -o -maxdepth 3 -iname \"customer.xml\" 2>/dev/null | head -8'" 2>$null

Write-Output ""
Write-Output "=== Magisk co chay khong (co the dung module VoLTE) ==="
adb -s $S shell "su -c 'magisk -v'" 2>$null
adb -s $S shell "su -c 'magisk --list-modules 2>/dev/null'" 2>$null

Write-Output ""
Write-Output "=== IMEI (can cho ma *#272*IMEI#) ==="
adb -s $S shell "su -c 'service call iphonesubinfo 1'" 2>$null | Out-String
