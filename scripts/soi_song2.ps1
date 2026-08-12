$S = "21f10e44220c7ece"
Write-Output "=== trang thai dich vu ==="
& adb -s $S shell "dumpsys telephony.registry | grep -i mServiceState | head -3" 2>&1

Write-Output ""
Write-Output "=== VoLTE / IMS ==="
foreach ($p in "persist.dbg.volte_avail_ovr","persist.dbg.vt_avail_ovr","persist.radio.volte.enable","persist.radio.imsregrequired") {
    $v = & adb -s $S shell "getprop $p" 2>&1
    Write-Output ("  {0,-32} = {1}" -f $p, $v)
}
$v = & adb -s $S shell "settings get global volte_vt_enabled" 2>&1
Write-Output ("  {0,-32} = {1}" -f "volte_vt_enabled", $v)

Write-Output ""
Write-Output "=== mang kha dung (2G/3G/4G) ==="
$v = & adb -s $S shell "settings get global preferred_network_mode" 2>&1
Write-Output ("  preferred_network_mode = {0}" -f $v)
