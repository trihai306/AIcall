#!/system/bin/sh
echo "=== TAT CA APN cua VIET NAM (mcc=452) ==="
content query --uri content://telephony/carriers \
  --projection _id:name:apn:type:mcc:mnc:carrier_enabled \
  --where "mcc=452" 2>/dev/null

echo ""
echo "=== Rieng Viettel 452-04 ==="
content query --uri content://telephony/carriers \
  --projection _id:name:apn:type:mnc \
  --where "mcc=452 AND mnc=04" 2>/dev/null

echo ""
echo "=== Co APN type ims cho 452 khong ==="
content query --uri content://telephony/carriers \
  --projection name:apn:type:mnc --where "mcc=452" 2>/dev/null | grep -i ims

echo ""
echo "(neu muc tren TRONG => may KHONG co APN IMS cho Viettel)"
