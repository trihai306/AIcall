#!/system/bin/sh
# Tim cac tuyen (path) lien quan VoLTE / bang rong / IMS trong mixer_paths.xml
F=/vendor/etc/mixer_paths.xml
[ -f "$F" ] || F=/system/etc/mixer_paths.xml
echo "file: $F"
echo ""

echo "=== TAT CA ten path co chua incall / volte / wb / ims ==="
grep -oE '<path name="[^"]*"' "$F" 2>/dev/null | grep -iE 'incall|volte|_wb|ims|voice' | sort -u

echo ""
echo "=== So luong path tong cong ==="
grep -c '<path name=' "$F" 2>/dev/null

echo ""
echo "=== Path dang dung cho CS hien tai (de doi chieu) ==="
sed -n '/<path name="incall_nb-handset-mic"/,/<\/path>/p' "$F" 2>/dev/null | head -25
