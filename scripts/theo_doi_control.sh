#!/system/bin/sh
# Theo doi control duong tiem LIEN TUC trong suot cuoc goi, de biet cai nao bi
# HAL gianh lai va vao luc nao. Doc moi 1.5s trong ~70s.
MIX=/data/local/tmp/mixctl

logcat -c
echo "bat dau theo doi ..."
i=0
while [ $i -lt 46 ]; do
  T=$(date +%H:%M:%S)
  U=$($MIX get "ABOX UAIF0 SPK" 2>/dev/null | sed 's/.*(//; s/).*//')
  A2=$($MIX get "AIF1TX1 Input 2" 2>/dev/null | sed 's/.*(//; s/).*//')
  A1=$($MIX get "AIF1TX1 Input 1" 2>/dev/null | sed 's/.*(//; s/).*//')
  N=$($MIX get "ABOX NSRC1" 2>/dev/null | sed 's/.*(//; s/).*//')
  ST=$(dumpsys telephony.registry 2>/dev/null | grep -o 'mForegroundCallState=[0-9]*' | head -1 | sed 's/mForegroundCallState=//')
  echo "$T st=$ST | UAIF0SPK=$U | TX1in2=$A2 | TX1in1=$A1 | NSRC1=$N"
  i=$((i+1))
  sleep 1.5
done

echo ""
echo "=== LOG HAL trong cuoc goi ==="
logcat -d 2>/dev/null | grep -iE "audio_hw|audio_route|set_route|volte|incall_|apply" | tail -25
