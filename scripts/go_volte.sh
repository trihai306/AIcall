#!/system/bin/sh
# Go APN IMS -> tat VoLTE -> cuoc goi quay ve chuyen mach kenh, duong tiem tieng
# chay lai nhu cu. Them lai bat cu luc nao bang them_apn_ims.sh.

echo "=== TRUOC ==="
content query --uri content://telephony/carriers \
  --projection _id:name:apn:type --where "mcc=452 AND mnc='04'" 2>/dev/null

echo ""
echo "=== XOA APN IMS ==="
content delete --uri content://telephony/carriers --where "name='Viettel IMS'" 2>&1

echo ""
echo "=== SAU ==="
content query --uri content://telephony/carriers \
  --projection _id:name:apn:type --where "mcc=452 AND mnc='04'" 2>/dev/null

echo ""
echo "=== Bat/tat che do may bay de nap lai ==="
settings put global airplane_mode_on 1
am broadcast -a android.intent.action.AIRPLANE_MODE --ez state true >/dev/null 2>&1
sleep 6
settings put global airplane_mode_on 0
am broadcast -a android.intent.action.AIRPLANE_MODE --ez state false >/dev/null 2>&1
sleep 30

echo ""
echo "=== mang hien tai ==="
getprop gsm.network.type
echo "(cho nay chua goi nen van la LTE - phai xem LUC DANG GOI)"
