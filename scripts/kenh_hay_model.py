"""Loi con lai la do KENH 8kHz hay do MODEL? Do doi chung tren cung 10 cau."""
import base64, difflib, io, json, re, sys, unicodedata, urllib.parse, urllib.request, wave
from pathlib import Path
import numpy as np
from scipy.signal import resample_poly
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from backend.services.stt_service import moi_tu_vung
from whisper_server.pho_server import _pick_device
from faster_whisper import WhisperModel

TTS="http://127.0.0.1:8100/api/voices/test-tts"; GIONG="giong_heu"
TMP=Path(r"C:\duan\chat-ai\logs\quet_stt2"); TMP.mkdir(parents=True, exist_ok=True)
CAU=["Alô em ơi","Lãi suất vay tín chấp bao nhiêu em","Anh vay được tối đa bao nhiêu",
     "Cần giấy tờ gì không em","Bao lâu thì giải ngân","Anh cần vay tám mươi triệu",
     "Anh muốn vay mua nhà","Anh không quan tâm đâu","Thôi để hôm khác đi",
     "Giám đốc ngân hàng tên gì em"]

def sinh(t,i,qdt):
    p=TMP/f"{i:02d}{'_dt' if qdt else ''}.wav"
    if not p.exists():
        d=urllib.parse.urlencode({"text":t,"voice_name":GIONG,
            "qua_dien_thoai":"true" if qdt else "false"}).encode()
        with urllib.request.urlopen(urllib.request.Request(TTS,data=d),timeout=300) as r:
            p.write_bytes(base64.b64decode(json.load(r)["audio"]))
    return p

def ch(s): return " ".join(re.sub(r"[^\w\s]"," ",unicodedata.normalize("NFC",s).lower()).split())
def gn(a,b): return difflib.SequenceMatcher(None,ch(a),ch(b)).ratio()
MOI=moi_tu_vung("nam")
KW=dict(language="vi",initial_prompt=MOI,no_speech_threshold=0.6,
        condition_on_previous_text=False,beam_size=5,vad_filter=False)
dev,ct=_pick_device()

for ten_m, duong in (("medium", r"C:\duan\chat-ai\models\phowhisper\PhoWhisper-medium-ct2"),
                     ("small",  r"C:\duan\chat-ai\models\phowhisper\PhoWhisper-small-ct2")):
    m=WhisperModel(duong,device=dev,compute_type=ct)
    for nhan,qdt in (("gốc 24kHz",False),("qua kênh 8kHz",True)):
        ra=[]
        for i,c in enumerate(CAU):
            segs,_=m.transcribe(str(sinh(c,i,qdt)),**KW)
            ra.append((c," ".join(s.text for s in segs).strip()))
        g=[gn(a,b) for a,b in ra]
        print(f"{ten_m:<8}{nhan:<16}{sum(g)/len(g)*100:6.1f}%  {sum(x>=0.85 for x in g)}/10")
        for (a,b),x in zip(ra,g):
            if x<0.85: print(f"          {a!r:<40} → {b!r}")
    print()
    del m
