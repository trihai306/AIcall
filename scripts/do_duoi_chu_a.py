"""Chu "a" cuoi cau co bi chap them mot duoi am khong?

Do: cat dan 0/30/60/90/120ms cuoi roi cho STT nghe lai chu CUOI. Neu cat mot
chut ma "han"/"ha" tro lai thanh "a" thi dung la duoi am thua.
"""
import io, sys, unicodedata, wave
from pathlib import Path
import numpy as np
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from whisper_server.pho_server import _pick_device
from faster_whisper import WhisperModel
from backend.services.stt_service import moi_tu_vung
dev,ct=_pick_device()
stt=WhisperModel(r"C:\duan\chat-ai\models\phowhisper\PhoWhisper-medium-ct2",device=dev,compute_type=ct)
MOI=moi_tu_vung("nam")
G=Path(r"C:\Users\Admin\Desktop\Check giọng\30 BAN MOI 12s - CHOT")
FILE=[p for p in sorted(G.glob("*.wav"))][:10]
def nghe_cuoi(x,sr):
    b=io.BytesIO()
    with wave.open(b,"wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(x,-1,1)*32767).astype(np.int16).tobytes())
    b.seek(0)
    segs,_=stt.transcribe(b,language="vi",initial_prompt=MOI,vad_filter=False,
                          beam_size=5,word_timestamps=True)
    tu=[w for s in segs for w in (s.words or [])]
    return unicodedata.normalize("NFC",tu[-1].word.strip().lower().strip(".,?!")) if tu else "∅"
MUC=(0,30,60,90,120)
dem={m:0 for m in MUC}
print(f"{'tệp':<26}" + "".join(f"{m:>8}ms" for m in MUC))
print("-"*74)
for f in FILE:
    with wave.open(str(f)) as w:
        sr=w.getframerate(); x=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)/32768
    ra=[]
    for m in MUC:
        k=len(x)-int(sr*m/1000)
        c=nghe_cuoi(x[:k],sr)
        ra.append(c)
        if c=="ạ": dem[m]+=1
    print(f"{f.name[:25]:<26}" + "".join(f"{c:>10}" for c in ra))
print("-"*74)
print("số tệp máy nghe chữ cuối ĐÚNG là 'ạ': " +
      "  ".join(f"{m}ms={dem[m]}/{len(FILE)}" for m in MUC))
