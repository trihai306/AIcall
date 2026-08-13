"""Dau file la AM RAC hay tieng that? Rac co van tay: TO -> IM -> TO."""
import base64, io, json, sys, urllib.parse, urllib.request, wave
from pathlib import Path
import numpy as np
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
TTS="http://127.0.0.1:8100/api/voices/test-tts"; GIONG="giong_heu"
CAU=["Dạ hẹn gặp lại anh chị ạ.","Dạ hạn mức vay lên đến 500 triệu đồng ạ.",
     "Em chào anh chị ạ.","Dạ phí trả nợ trước hạn là 2% trên số tiền trả trước ạ."]
def sinh(t):
    d=urllib.parse.urlencode({"text":t,"voice_name":GIONG,"qua_dien_thoai":"false"}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS,data=d),timeout=300) as r:
        return json.load(r)["audio"]
print("bao hình 50ms một ô, 1,2 giây đầu (đơn vị: biên độ đỉnh 0-1)\n")
for c in CAU:
    with wave.open(io.BytesIO(base64.b64decode(sinh(c)))) as w:
        sr=w.getframerate(); x=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16)
    o=int(sr*0.05); v=[float(np.abs(x[i*o:(i+1)*o]).max())/32768 for i in range(24)]
    print(f"  {c[:46]}")
    print("   " + "".join("█" if a>.35 else "▓" if a>.15 else "░" if a>.03 else "·" for a in v))
    print(f"   {'':0}0ms{'':>18}600ms{'':>17}1200ms   đỉnh 0-150ms={max(v[:3]):.2f}  "
          f"thấp nhất 150-800ms={min(v[3:16]):.3f}")
print("\n█ >0.35 to   ▓ 0.15-0.35   ░ 0.03-0.15 lí nhí   · <0.03 im")
print("Vân tay âm rác: █ ở đầu, rồi một dải · hoặc ░ dài, rồi mới █ lại.")
print("Tiếng thật vào ngay: █▓ liền mạch, không có dải im chen giữa.")
