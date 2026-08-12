#!/system/bin/sh
echo "=== Bat che do may bay ==="
settings put global airplane_mode_on 1
am broadcast -a android.intent.action.AIRPLANE_MODE --ez state true >/dev/null 2>&1
sleep 6

echo "=== Tat che do may bay ==="
settings put global airplane_mode_on 0
am broadcast -a android.intent.action.AIRPLANE_MODE --ez state false >/dev/null 2>&1
echo "cho 35s cho mang bat lai va IMS thu dang ky ..."
sleep 35

echo ""
echo "=== APN dang chon ==="
content query --uri content://telephony/carriers/preferapn --projection name:apn:type 2>/dev/null

echo ""
echo "=== IMS / VoLTE ==="
dumpsys telephony.registry 2>/dev/null | grep -E "mVoLteServiceState|mApnBlackList" | head -3

echo ""
echo "=== co VoLTE cua nha mang ==="
dumpsys carrier_config 2>/dev/null | grep -E "carrier_volte_available_bool|carrier_volte_provisioned_bool" | head -2

echo ""
echo "=== mang dang bat ==="
getprop gsm.network.type

echo ""
echo "=== IMS da dang ky chua (log) ==="
logcat -d -t 200 2>/dev/null | grep -iE "ims.*regist|volte" | tail -8
