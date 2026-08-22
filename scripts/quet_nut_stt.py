"""Quet cac nut van cua faster-whisper tren dung 10 cau khach, qua kenh thoai.

Nap model truc tiep (khong qua server) de doi cau hinh ma khong phai khoi dong lai.
"""
import base64, difflib, json, os, re, sys, unicodedata, urllib.parse, urllib.request
from pathlib import Path
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from backend.services.stt_service import moi_tu_vung

TTS="http://127.0.0.1:8100/api/voices/test-tts"; GIONG="giong_heu"
TMP=Path(r"C:\duan\chat-ai\logs\quet_stt"); TMP.mkdir(parents=True, exist_ok=True)
CAU=["Alô em ơi","Lãi suất vay tín chấp bao nhiêu em","Anh vay được tối đa bao nhiêu",
     "Cần giấy tờ gì không em","Bao lâu thì giải ngân","Anh cần vay tám mươi triệu",
     "Anh muốn vay mua nhà","Anh không quan tâm đâu","Thôi để hôm khác đi",
     "Giám đốc ngân hàng tên gì em"]

def sinh(t, i):
    p = TMP / f"{i:02d}.wav"
    if p.exists(): return p
    d=urllib.parse.urlencode({"text":t,"voice_name":GIONG,"qua_dien_thoai":"true"}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS,data=d),timeout=300) as r:
        j=json.load(r)
    p.write_bytes(base64.b64decode(j["audio"])); return p
wav=[sinh(c,i) for i,c in enumerate(CAU)]

from faster_whisper import WhisperModel
from whisper_server.pho_server import _pick_device
M = r"C:\duan\chat-ai\models\phowhisper\PhoWhisper-medium-ct2"
dev, ct = _pick_device()
print(f"model {M}  device={dev} compute={ct}\n")
model = WhisperModel(M, device=dev, compute_type=ct)

def ch(s): return " ".join(re.sub(r"[^\w\s]"," ",unicodedata.normalize("NFC",s).lower()).split())
def gn(a,b): return difflib.SequenceMatcher(None,ch(a),ch(b)).ratio()

MOI = moi_tu_vung("nam")
CAU_HINH = [
    ("nay: VAD TAT beam5",          dict(vad_filter=False)),
    ("VAD BAT (300ms)",             dict(vad_filter=True,  vad_parameters={"min_silence_duration_ms":300})),
    ("VAD on + dem 800ms",          dict(vad_filter=True,  vad_parameters={"min_silence_duration_ms":300,"speech_pad_ms":800})),
    ("VAD on(100)",                 dict(vad_filter=True,  vad_parameters={"min_silence_duration_ms":100})),
    ("beam 10",                     dict(vad_filter=True,  vad_parameters={"min_silence_duration_ms":300}, beam_size=10)),
    ("VAD TAT + beam 10",           dict(vad_filter=False, beam_size=10)),
    ("VAD TAT + beam10 + tim 5",    dict(vad_filter=False, beam_size=10, best_of=5, patience=2.0)),
]
print(f"{'cấu hình':<30}{'nghe đúng':>11}{'đạt':>7}   câu còn hỏng")
print("-"*96)
for ten, kw in CAU_HINH:
    kw = {"language":"vi","initial_prompt":MOI,"no_speech_threshold":0.6,
          "condition_on_previous_text":False,"beam_size":5, **kw}
    ra=[]
    for p,c in zip(wav,CAU):
        segs,_=model.transcribe(str(p), **kw)
        ra.append((c," ".join(s.text for s in segs).strip()))
    g=[gn(a,b) for a,b in ra]
    hong=[a for (a,b),x in zip(ra,g) if x<0.85]
    print(f"{ten:<30}{sum(g)/len(g)*100:10.1f}%{sum(x>=0.85 for x in g):5}/10   {', '.join(repr(h) for h in hong)[:52]}")
