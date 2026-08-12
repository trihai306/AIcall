#!/system/bin/sh
F=/vendor/etc/mixer_paths.xml
[ -f "$F" ] || F=/system/etc/mixer_paths.xml

trich() {
  echo "===== $1 ====="
  sed -n "/<path name=\"$1\">/,/<\/path>/p" "$F" 2>/dev/null | head -22
  echo ""
}

echo "########## HO apcall (AP xu ly cuoc goi) ##########"
grep -oE '<path name="apcall[^"]*"' "$F" | sed 's/<path name="//; s/"//' | sort -u
echo ""
trich "apcall-handset-mic"
trich "apcall_wb-handset-mic"

echo "########## VoLTE thoai (khong phai video) ##########"
trich "volte_cp_wb-handset-mic"
trich "volte_cp_nb-handset-mic"
trich "volte_cp_evs-handset-mic"

echo "########## Khoi lien quan SIFS1 / UAIF ##########"
trich "route-rdma7-to-sifs1"
trich "route-sifs1-to-uaif1"
trich "route-sifs0-to-uaif0"
trich "route-uaif1-to-nsrc3"
trich "route-uaif0-to-nsrc0"
