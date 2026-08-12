#!/system/bin/sh
F=/vendor/etc/mixer_paths.xml
[ -f "$F" ] || F=/system/etc/mixer_paths.xml

echo "############ 1. CAC HO TUYEN (tien to truoc dau '-') ############"
grep -oE '<path name="[^"]*"' "$F" | sed 's/<path name="//; s/"//' \
  | sed 's/-.*//' | sort | uniq -c | sort -rn | head -40

echo ""
echo "############ 2. CAC KHOI 'route-*' (vien gach xay dung) ############"
grep -oE '<path name="route-[^"]*"' "$F" | sed 's/<path name="//; s/"//' | sort -u

echo ""
echo "############ 3. TUYEN NAO DUNG AIF1TX (duong len qua codec) ############"
grep -B30 'AIF1TX1 Input' "$F" | grep -oE '<path name="[^"]*"' | sed 's/<path name="//; s/"//' | sort -u | head -30
