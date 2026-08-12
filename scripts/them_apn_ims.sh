#!/system/bin/sh
# Them APN IMS cho Viettel (452-04). May nay khong co APN IMS nao cho Viet Nam,
# nen IMS khong co duong de dung ket noi -> khong dang ky duoc -> khong co VoLTE.
#
# HOAN TAC: xem cuoi file.

echo "=== TRUOC KHI THEM ==="
content query --uri content://telephony/carriers \
  --projection _id:name:apn:type --where "mcc=452 AND mnc='04'" 2>/dev/null

echo ""
echo "=== THEM APN IMS ==="
content insert --uri content://telephony/carriers \
  --bind name:s:"Viettel IMS" \
  --bind apn:s:"ims" \
  --bind type:s:"ims" \
  --bind mcc:s:"452" \
  --bind mnc:s:"04" \
  --bind numeric:s:"45204" \
  --bind protocol:s:"IPV4V6" \
  --bind roaming_protocol:s:"IPV4V6" \
  --bind carrier_enabled:i:1 \
  --bind bearer:i:0 2>&1

echo ""
echo "=== SAU KHI THEM ==="
content query --uri content://telephony/carriers \
  --projection _id:name:apn:type --where "mcc=452 AND mnc='04'" 2>/dev/null

echo ""
echo "HOAN TAC neu can:"
echo "  content delete --uri content://telephony/carriers --where \"name='Viettel IMS'\""
