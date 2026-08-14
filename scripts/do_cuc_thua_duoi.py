"""Duoi cau co CUC TIENG THUA khong, va cat duoc khong ma khong an mat chu that.

Cach do: tim khoang IM cuoi cung. Phan sau no la "duoi". So nang luong duoi voi
than cau, va cho STT nghe ban DA CAT de biet co mat chu nao khong.
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
FILE=[]
G=Path(r"C:\Users\Admin\Desktop\Check giọng")
for d in ("Lan 7","Lan 6 - DA SUA","30 BAN MOI 12s - CHOT"):
    p=G/d
    if p.exists(): FILE += sorted(p.rglob("*.wav"))[:9]
def rms(x): return float(np.sqrt(np.mean(x**2))) if len(x) else 0.0
def nghe(x,sr):
    b=io.BytesIO()
    with wave.open(b,"wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(x,-1,1)*32767).astype(np.int16).tobytes())
    b.seek(0)
    segs,_=stt.transcribe(b,language="vi",initial_prompt=MOI,vad_filter=False,beam_size=5)
    return " ".join(s.text.strip() for s in segs)
print(f"{'tệp':<30}{'đuôi':>7}{'ms':>6}{'đuôi/thân':>11}   cắt đuôi rồi máy nghe có mất chữ")
print("-"*104)
for f in FILE:
    with wave.open(str(f)) as w:
        sr=w.getframerate(); x=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)/32768
    o=int(sr*0.010); n=len(x)//o
    e=np.array([rms(x[i*o:(i+1)*o]) for i in range(n)])
    if not n: continue
    than=float(np.median(e[e>0.02])) if (e>0.02).any() else 0.0
    ng=0.10*float(np.percentile(e,95))
    # tim khoang im >=60ms cuoi cung, cach cuoi khong qua 500ms
    im=e<ng; cuoi=None; i=n-1
    while i>=0:
        if im[i]:
            j=i
            while j>=0 and im[j]: j-=1
            if (i-j)*10>=60 and (n-1-i)*10<=500 and (n-1-i)*10>=20:
                cuoi=i; break
            i=j
        else: i-=1
    if cuoi is None:
        print(f"{f.name[:29]:<30}{'—':>7}"); continue
    duoi=x[(cuoi+1)*o:]
    ty=rms(duoi)/max(1e-9,than)
    truoc=nghe(x,sr); sau=nghe(x[:(cuoi+1)*o],sr)
    mat = "GIỮ NGUYÊN" if truoc.rstrip('.')==sau.rstrip('.') else f"KHÁC: {truoc[-26:]!r} -> {sau[-26:]!r}"
    print(f"{f.name[:29]:<30}{'có':>7}{len(duoi)/sr*1000:6.0f}{ty:11.2f}   {mat}")
