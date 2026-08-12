# Soi goc re vi sao VoLTE bi chan: CSC, carrier config, va kha nang phan cung.
$S = "21f10e44220c7ece"
function P($ten) {
    $v = adb -s $S shell getprop $ten 2>$null
    if ([string]::IsNullOrWhiteSpace($v)) { $v = "(TRONG)" }
    Write-Output ("  {0,-42} {1}" -f $ten, $v)
}

Write-Output "=== CSC (goi tuy bien nha mang) ==="
P "ro.csc.sales_code"
P "ro.csc.country_code"
P "ro.csc.countryiso_code"
P "ril.official_cscver"
P "ro.omc.sales_code"
P "persist.omc.sales_code"

Write-Output ""
Write-Output "=== May co PHAN CUNG/PHAN MEM VoLTE khong ==="
P "persist.dbg.volte_avail_ovr"
P "persist.dbg.vt_avail_ovr"
P "ro.vendor.radio.volte"
P "ro.telephony.default_network"

Write-Output ""
Write-Output "=== Goi VoLTE cua Samsung co tren may khong ==="
adb -s $S shell "pm list packages" 2>$null | Select-String -Pattern "ims" | Select-Object -First 8

Write-Output ""
Write-Output "=== carrier config ==="
adb -s $S shell "dumpsys carrier_config" 2>$null | Select-String -Pattern "volte|vowifi|ims_gba|editable_enhanced" | Select-Object -First 12
