"""Can HE_SO_BU_LANG: chu cuoi bi bop <-> F5 bia quang lang. Do CA BA mat.

0.85 duoc chon vi 1.11 lam F5 bia quang lang giua cau; 0.75 thi doc sai chu.
Nhung 0.85 lai bop nghet chu CUOI (-11 dB). Phai can, khong duoc chi nhin mot mat.
"""
import asyncio, difflib, io, re, statistics, sys, unicodedata, wave
import numpy as np
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import backend.services.tts_service as TS
from backend.pipeline.text_normalizer import normalize_for_tts
from whisper_server.pho_server import _pick_device
from faster_whisper import WhisperModel
M=r"C:\duan\chat-ai\models\phowhisper\PhoWhisper-medium-ct2"
src=open(r"C:\duan\chat-ai\scripts\nghe_lai_30_cau.py",encoding="utf-8").read()
exec("CAU=["+src.split("CAU=[")[1].split("]\n")[0]+"]")
dai=open(r"C:\duan\chat-ai\scripts\cau_dai_30.py",encoding="utf-8").read()
exec("DAI=[\n"+dai.split("CAU=[\n")[1].split("\n]\n")[0]+"\n]")
NGAN=CAU[:15]; DAI=DAI[:10]
def rms(x): return float(np.sqrt(np.mean(x**2))) if len(x) else 0.0
def tu(s): return [t for t in re.sub(r"[^\w\s]"," ",unicodedata.normalize("NFC",s).lower()).split() if t]
def sai(a,b):
    A,B=tu(a),tu(b); sm=difflib.SequenceMatcher(None,A,B,autojunk=False); m=t=0
    for op,i1,i2,j1,j2 in sm.get_opcodes():
        if op in ("delete","replace"): m+=i2-i1
        if op in ("insert","replace"): t+=j2-j1
    return (m+t)/(2*max(1,len(A)))
def lo_hong(x,sr,nguong_ms=360):
    """Quang lang >= nguong (F5 bia ra), do bang RMS tuong doi nhu cat_lang_bia."""
    o=int(sr*0.020); n=len(x)//o
    e=np.array([rms(x[i*o:(i+1)*o]) for i in range(n)])
    if not n: return 0,0.0
    nguong=0.20*float(np.percentile(e,95)); im=e<nguong
    so=0; tong=0.0; i=0
    while i<n:
        if im[i]:
            j=i
            while j<n and im[j]: j+=1
            d=(j-i)*20
            if d>=nguong_ms: so+=1; tong+=d
            i=j
        else: i+=1
    return so,tong
dev,ct=_pick_device(); stt=WhisperModel(M,device=dev,compute_type=ct)
async def main():
    tts=TS.F5TTSService(); tts.load()
    toc=tts.toc_do_cua("giong_heu")*tts.he_so_thoai()
    goc=TS.HE_SO_BU_LANG
    print(f"{'bộ':<8}{'hệ số':<8}{'chữ cuối/TV':>13}{'dB':>7}{'lỗ hổng':>10}{'ms lỗ':>8}{'từ sai':>9}")
    print("-"*66)
    for ten_bo,CAU in (("ngắn",NGAN),("dài",DAI)):
      for hs in (0.85,1.00,1.15):
        TS.HE_SO_BU_LANG=hs
        r=[];lo=0;lo_ms=0.0;e=[];giay=0.0
        for c in CAU:
            wav=await tts.synthesize(c,voice="giong_heu",speed=toc,use_cache=False)
            with wave.open(io.BytesIO(wav)) as w:
                sr=w.getframerate(); x=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)/32768
            giay+=len(x)/sr
            a,b=lo_hong(x,sr); lo+=a; lo_ms+=b
            segs,_=stt.transcribe(io.BytesIO(wav),language="vi",word_timestamps=True,
                                  vad_filter=False,beam_size=5)
            wl=[w for s in segs for w in (s.words or []) if w.end>w.start]
            v=[(w.word, rms(x[int(w.start*sr):int(w.end*sr)])) for w in wl]
            v=[t for t in v if t[1]>0]
            if len(v)>=3: r.append(v[-1][1]/max(1e-9,statistics.median(t[1] for t in v[:-1])))
            e.append(sai(normalize_for_tts(c)," ".join(t[0] for t in v)))
        tb=sum(r)/len(r)
        print(f"{ten_bo:<8}{hs:<8.2f}{tb:13.2f}{20*np.log10(tb):7.1f}{lo:10}{lo_ms:8.0f}{sum(e)/len(e)*100:8.1f}%")
    TS.HE_SO_BU_LANG=goc
asyncio.run(main())
