#!/system/bin/sh
F=/vendor/etc/mixer_paths.xml
[ -f "$F" ] || F=/system/etc/mixer_paths.xml

trich() {
  echo "===== $1 ====="
  sed -n "/<path name=\"$1\">/,/<\/path>/p" "$F" 2>/dev/null | head -30
  echo ""
}

echo "########## TUYEN VoLTE (bang rong) ##########"
trich "volte_vt_cp_wb-handset-mic"
trich "volte_vt_cp_wb-usb-headset-mic"
trich "volte_vt_cp_wb-headphone"

echo "########## TUYEN CS dang dung (doi chieu) ##########"
trich "incall_nb-handset-mic"
trich "incall-usb-headset-mic"
trich "incall_nb-headphone"

echo "########## CAC TUYEN CON duoc tham chieu ##########"
trich "route-cp-tx"
trich "route-cp-wb-tx"
trich "dev-dual-mic"

echo "########## Moi ten path co chu volte (day du) ##########"
grep -oE '<path name="[^"]*volte[^"]*"' "$F" 2>/dev/null | sort -u
