#!/system/bin/sh
F=/vendor/etc/mixer_paths.xml
[ -f "$F" ] || F=/system/etc/mixer_paths.xml

trich() {
  echo "===== $1 ====="
  sed -n "/<path name=\"$1\">/,/<\/path>/p" "$F" 2>/dev/null | head -25
  echo ""
}

trich "incall_wb-handset-mic"
trich "incall_nb-handset-mic"
trich "incall_wb-usb-headset-mic"
trich "incall-usb-headset-mic"
trich "incall_wb-headset"
trich "incall_nb-headset"
trich "route-uaif0-to-nsrc1"
trich "route-nsrc1-to-wdma2"
trich "route-rdma6-to-sifs2"
trich "route-sifs2-to-nsrc1"
trich "erap-usb-on"
