"""Nghiem thu bat bien: NGHE THU (24kHz) doc dung nhip CUOC GOI.

Do bang nhip that su cua file wav, khong tin vao con so cau hinh.
"""
import base64, io, json, re, sys, unicodedata, urllib.parse, urllib.request, wave
from types import SimpleNamespace
from pathlib import Path
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from backend.pipeline.text_normalizer import normalize_for_tts
TTS="http://127.0.0.1:8100/api/voices/test-tts"
HS="http://127.0.0.1:8100/api/voices/phone-speed"; GIONG="giong_heu"
CAU=["Dạ hạn mức vay lên đến 500 triệu đồng ạ.",
     "Dạ lãi suất vay tín chấp bên em từ 7,9% một năm ạ.",
     "Dạ thời gian giải ngân trung bình từ hai đến ba ngày làm việc ạ."]
def dat_hs(v):
    req=urllib.request.Request(HS,data=json.dumps({"he_so":v}).encode(),
        headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=60) as r: return json.load(r)
def sinh(t,qdt):
    d=urllib.parse.urlencode({"text":t,"voice_name":GIONG,
        "qua_dien_thoai":"true" if qdt else "false"}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS,data=d),timeout=600) as r:
        return json.load(r)
def am_tiet(s): return len(re.sub(r"[^\w\s]"," ",unicodedata.normalize("NFC",s)).split())
# doi chung voi tinh toan cua pipeline
from backend.pipeline.streaming_pipeline import StreamingPipeline
from backend.main import app_state
for hs in (1.28, 1.00):
    dat_hs(hs)
    tts=app_state.tts if getattr(app_state,"tts",None) else None
    print(f"\nhệ số thoại {hs:.2f}")
    for qdt in (False, True):
        nh=[]
        for c in CAU:
            j=sinh(c,qdt)
            if j.get("error"): print("  LỖI",j["error"][:60]); continue
            nh.append(am_tiet(normalize_for_tts(c))/(j["duration_ms"]/1000)*60)
        print(f"   {'qua kênh 8kHz' if qdt else 'nghe thử 24kHz':<18}"
              f"{sum(nh)/len(nh):6.0f} âm tiết/phút")
dat_hs(1.00)
print("\nĐã đặt hệ số thoại = 1.00")
