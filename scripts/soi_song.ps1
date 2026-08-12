$S = "21f10e44220c7ece"
$ADB = "adb"
function A($cmd) { & $ADB -s $S shell $cmd 2>&1 }

Write-Output "=== che do may bay (1 = dang bat) ==="
A "settings get global airplane_mode_on"

Write-Output "=== trang thai dang ky mang ==="
A "dumpsys telephony.registry | findstr /i `"mServiceState`"" | Select-Object -First 4

Write-Output "=== nha mang / SIM ==="
foreach ($p in "gsm.sim.state","gsm.operator.alpha","gsm.operator.numeric","gsm.network.type","gsm.sim.operator.alpha") {
    $v = A "getprop $p"
    Write-Output ("  {0,-26} = {1}" -f $p, $v)
}

Write-Output "=== cuong do song ==="
A "dumpsys telephony.registry | findstr /i `"mSignalStrength`"" | Select-Object -First 2
