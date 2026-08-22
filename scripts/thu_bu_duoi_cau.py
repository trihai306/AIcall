"""Bu do to cho CHU CUOI co lam may nghe dung tro lai khong?

Khong doi chu, khong doi model - chi keo bien do chu cuoi len ngang cac chu
khac. Neu STT nghe dung tro lai thi day la ban va dung; neu khong thi tieng do
von da meo chu khong phai chi nho.
"""
import base64, difflib, io, json, re, statistics, sys, unicodedata, urllib.parse, urllib.request, wave
from pathlib import Path
import numpy as np
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from whisper_server.pho_server import _pick_device
from faster_whisper import WhisperModel
TTS="http://127.0.0.1:8100/api/voices/test-tts"; GIONG="giong_heu"
M=r"C:\duan\chat-ai\models\phowhisper\PhoWhisper-medium-ct2"
CAU=["Thời gian vay tối đa hai mươi lăm năm.",
     "Anh chị chuẩn bị hồ sơ vay vốn.",
     "Hạn mức lên đến năm trăm triệu đồng.",
     "Thời hạn vay là ba mươi sáu tháng.",
     "Em cảm ơn anh chị rất nhiều.",
     "Gói vay này dành cho khách hàng có thu nhập ổn định.",
     "Bên em hỗ trợ tối đa năm trăm triệu đồng.",
     "Thủ tục rất đơn giản và nhanh gọn."]
def rms(x): return float(np.sqrt(np.mean(x**2))) if len(x) else 0.0
def sinh(t):
    d=urllib.parse.urlencode({"text":t,"voice_name":GIONG,"qua_dien_thoai":"false"}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS,data=d),timeout=600) as r:
        j=json.load(r)
    return None if j.get("error") else base64.b64decode(j["audio"])
def goi(wav):
    with wave.open(io.BytesIO(wav)) as w:
        return w.getframerate(), np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)/32768
def dong(x,sr):
    b=io.BytesIO()
    with wave.open(b,"wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(x,-1,1)*32767).astype(np.int16).tobytes())
    return b.getvalue()
dev,ct=_pick_device(); stt=WhisperModel(M,device=dev,compute_type=ct)
def nghe_tu(wav):
    segs,_=stt.transcribe(io.BytesIO(wav),language="vi",word_timestamps=True,
                          vad_filter=False,beam_size=5)
    return [w for s in segs for w in (s.words or []) if w.end>w.start]
def bu_duoi(wav, tran_dB=12.0, dich=0.75):
    """Keo chu CUOI len ngang trung vi cac chu khac, khong qua tran dB."""
    sr,x=goi(wav); tu=nghe_tu(wav)
    if len(tu)<3: return wav,1.0
    r=[rms(x[int(w.start*sr):int(w.end*sr)]) for w in tu]
    r=[v for v in r if v>0]
    if len(r)<3: return wav,1.0
    muc_tieu=dich*statistics.median(r[:-1])
    if r[-1]<=0 or r[-1]>=muc_tieu: return wav,1.0
    g=min(muc_tieu/r[-1], 10**(tran_dB/20))
    a=int(tu[-1].start*sr); y=x.copy()
    # ramp muot 30ms de khong nghe ra cho noi
    n=min(int(sr*0.03), max(1,len(y)-a))
    y[a:a+n]*=np.linspace(1.0,g,n); y[a+n:]*=g
    return dong(y,sr), g
def tu_cuoi(wav):
    t=nghe_tu(wav)
    return unicodedata.normalize("NFC",t[-1].word.strip().lower().strip(".,?!")) if t else "∅"
print(f"{'mong đợi':<10}{'chưa bù':<12}{'bù bao nhiêu':>13}{'sau khi bù':<12}")
print("-"*52)
dung_truoc=dung_sau=0
for c in CAU:
    wav=sinh(c)
    if not wav: continue
    mong=re.sub(r"[^\w\s]","",unicodedata.normalize("NFC",c)).split()[-1].lower()
    t1=tu_cuoi(wav)
    wav2,g=bu_duoi(wav)
    t2=tu_cuoi(wav2)
    dung_truoc+= t1==mong; dung_sau+= t2==mong
    print(f"{mong:<10}{t1:<12}{20*np.log10(g):>10.1f} dB  {t2:<12}"
          + ("  ✓" if t2==mong else ""))
print("-"*52)
print(f"máy nghe ĐÚNG chữ cuối:  chưa bù {dung_truoc}/{len(CAU)}   sau khi bù {dung_sau}/{len(CAU)}")
