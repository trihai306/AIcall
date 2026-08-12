S=21f10e44220c7ece
echo "=== trang thai dich vu (voiceRegState / dataRegState) ==="
adb -s $S shell "dumpsys telephony.registry | grep -i 'mServiceState' | head -4"
echo
echo "=== VoLTE / IMS ==="
for p in persist.dbg.volte_avail_ovr persist.dbg.vt_avail_ovr persist.radio.volte.enable; do
  printf "  %-32s = %s\n" "$p" "$(adb -s $S shell getprop $p)"
done
adb -s $S shell "settings get global volte_vt_enabled"
echo
echo "=== IMS dang ky ==="
adb -s $S shell "dumpsys telephony.registry | grep -iE 'ims|Registered' | head -6"
