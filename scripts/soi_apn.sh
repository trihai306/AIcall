#!/system/bin/sh
# Soi danh sach APN cua may, tim xem co APN kieu "ims" khong.
echo "=== TAT CA APN (name | apn | type | mccmnc) ==="
content query --uri content://telephony/carriers \
  --projection name:apn:type:mcc:mnc:carrier_enabled 2>/dev/null | head -40

echo ""
echo "=== APN co chua 'ims' ==="
content query --uri content://telephony/carriers \
  --projection name:apn:type:mcc:mnc 2>/dev/null | grep -i ims

echo ""
echo "=== APN dang duoc chon (preferapn) ==="
content query --uri content://telephony/carriers/preferapn \
  --projection name:apn:type 2>/dev/null

echo ""
echo "=== MCC/MNC hien tai ==="
getprop gsm.sim.operator.numeric
getprop gsm.operator.numeric
