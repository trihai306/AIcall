"""heu_a co that su tot hon giong_heu khong - tren bo RONG, va co cung giong khong?"""
import base64, difflib, io, json, re, statistics, sys, unicodedata, urllib.parse, urllib.request, wave
from pathlib import Path
import numpy as np
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from backend.pipeline.text_normalizer import normalize_for_tts
from whisper_server.pho_server import _pick_device
from faster_whisper import WhisperModel
TTS="http://127.0.0.1:8100/api/voices/test-tts"
M=r"C:\duan\chat-ai\models\phowhisper\PhoWhisper-medium-ct2"
src=open(r"C:\duan\chat-ai\scripts\nghe_lai_30_cau.py",encoding="utf-8").read()
exec("NGAN=["+src.split("CAU=[")[1].split("]\n")[0]+"]")
dai=open(r"C:\duan\chat-ai\scripts\cau_dai_30.py",encoding="utf-8").read()
exec("DAI=[\n"+dai.split("CAU=[\n")[1].split("\n]\n")[0]+"\n]")
CAU=NGAN[:15]+DAI[:8]
# 1. hai doan mau co cung giong khong: so dac trung pho (MFCC trung binh)
import torchaudio, torch
def dac_trung(p):
    w,sr=torchaudio.load(p)
    if w.shape[0]>1: w=w.mean(0,keepdim=True)
    m=torchaudio.transforms.MFCC(sample_rate=sr,n_mfcc=20)(w)[0]
    return m.mean(dim=1)
R=Path(r"C:\duan\chat-ai\models\tts\ref_voices")
va=dac_trung(str(R/"giong_heu.wav")); vb=dac_trung(str(R/"heu_a.wav"))
cos=float(torch.nn.functional.cosine_similarity(va,vb,dim=0))
for ten in ("giong_heu","heu_a"):
    w,sr=torchaudio.load(str(R/f"{ten}.wav"))
    txt=(R/f"{ten}.txt").read_text(encoding="utf-8").strip() if (R/f"{ten}.txt").exists() else "(lấy từ .env)"
    print(f"{ten:<11} {w.shape[-1]/sr:5.2f}s  lời mẫu: {txt[:64]}")
print(f"giống nhau về âm sắc (MFCC cosine): {cos:.3f}   (1.0 = trùng khít)\n")
def rms_(x): return float(np.sqrt(np.mean(x**2))) if len(x) else 0.0
def sinh(t,v):
    d=urllib.parse.urlencode({"text":t,"voice_name":v,"qua_dien_thoai":"false"}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS,data=d),timeout=600) as r:
        j=json.load(r)
    return None if j.get("error") else base64.b64decode(j["audio"])
dev,ct=_pick_device(); stt=WhisperModel(M,device=dev,compute_type=ct)
def tu(s): return [t for t in re.sub(r"[^\w\s]"," ",unicodedata.normalize("NFC",s).lower()).split() if t]
def sai(a,b):
    A,B=tu(a),tu(b); sm=difflib.SequenceMatcher(None,A,B,autojunk=False); m=t=0
    for op,i1,i2,j1,j2 in sm.get_opcodes():
        if op in ("delete","replace"): m+=i2-i1
        if op in ("insert","replace"): t+=j2-j1
    return (m+t)/(2*max(1,len(A)))
def lo_hong(x,sr):
    o=int(sr*0.020); n=len(x)//o
    e=np.array([rms_(x[i*o:(i+1)*o]) for i in range(n)])
    if not n: return 0
    ng=0.20*float(np.percentile(e,95)); im=e<ng; so=0;i=0
    while i<n:
        if im[i]:
            j=i
            while j<n and im[j]: j+=1
            if (j-i)*20>=360: so+=1
            i=j
        else: i+=1
    return so
print(f"{'đoạn mẫu':<12}{'chữ cuối/TV':>12}{'chữ cuối đúng':>15}{'từ sai':>9}{'lỗ hổng':>9}")
print("-"*60)
for v in ("giong_heu","heu_a"):
    ty=[];e=[];lo=0;dung=0
    for c in CAU:
        wav=sinh(c,v)
        if not wav: continue
        with wave.open(io.BytesIO(wav)) as w:
            sr=w.getframerate(); x=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)/32768
        lo+=lo_hong(x,sr)
        segs,_=stt.transcribe(io.BytesIO(wav),language="vi",word_timestamps=True,vad_filter=False,beam_size=5)
        wl=[w for s in segs for w in (s.words or []) if w.end>w.start]
        vv=[(unicodedata.normalize("NFC",w.word.strip().lower().strip(".,?!")),
             rms_(x[int(w.start*sr):int(w.end*sr)])) for w in wl]
        vv=[t for t in vv if t[1]>0]
        if len(vv)<3: continue
        ty.append(vv[-1][1]/max(1e-9,statistics.median(t[1] for t in vv[:-1])))
        mong=tu(normalize_for_tts(c))
        dung += bool(mong) and vv[-1][0]==mong[-1]
        e.append(sai(normalize_for_tts(c)," ".join(t[0] for t in vv)))
    print(f"{v:<12}{sum(ty)/len(ty):12.2f}{dung:>10}/{len(e)}{sum(e)/len(e)*100:8.1f}%{lo:9}")
