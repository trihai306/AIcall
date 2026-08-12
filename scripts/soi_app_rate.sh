#!/system/bin/sh
echo "=== log cua app cau tieng (rate, AudioTrack) ==="
logcat -d -t 400 2>/dev/null | grep -iE "voicebridge|tuktech" | tail -25

echo ""
echo "=== AudioTrack dang mo o rate nao ==="
dumpsys media.audio_flinger 2>/dev/null | grep -iE "sampleRate|sample rate|Fast track|Client" | head -20

echo ""
echo "=== app co dang chay khong ==="
ps -A 2>/dev/null | grep -i tuktech
