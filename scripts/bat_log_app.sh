#!/system/bin/sh
# Xem app cau tieng thuc su dung tan so nao khi duoc bao 16000.
am force-stop com.tuktech.voicebridge
sleep 2
logcat -c
am start-foreground-service -n com.tuktech.voicebridge/.BridgeService \
   --ei src 3 --ei port 8123 --ei rate_xuong 16000 --ei rate_len 8000 >/dev/null 2>&1
sleep 4

echo "=== log cua app ==="
logcat -d 2>/dev/null | grep -iE "voicebridge|BridgeService|AudioTrack|AudioRecord|rate" | head -30

echo ""
echo "=== AudioTrack nao dang mo (sampleRate) ==="
dumpsys media.audio_flinger 2>/dev/null | grep -B2 -A2 "sampleRate=" | head -20
