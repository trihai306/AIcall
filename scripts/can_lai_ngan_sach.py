"""Can HE_SO_BU_LANG tren BA mat cung luc, tren ca cau NGAN va cau DAI."""
import asyncio, difflib, io, re, sys, unicodedata, wave
import numpy as np
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import backend.services.tts_service as TS
from backend.api.voices import _cat_manh_nhu_pipeline, _ghep_nhu_pipeline
from backend.pipeline.text_normalizer import normalize_for_tts
from whisper_server.pho_server import _pick_device
from faster_whisper import WhisperModel
from backend.services.stt_service import moi_tu_vung
dev,ct=_pick_device()
stt=WhisperModel(r"C:\duan\chat-ai\models\phowhisper\PhoWhisper-medium-ct2",device=dev,compute_type=ct)
MOI=moi_tu_vung("nam")
src=open(r"C:\duan\chat-ai\scripts\nghe_lai_30_cau.py",encoding="utf-8").read()
exec("NGAN=["+src.split("CAU=[")[1].split("]\n")[0]+"]")
moi=open(r"C:\duan\chat-ai\scripts\cau_moi_12s.py",encoding="utf-8").read()
exec("DAI=[\n"+moi.split("CAU=[\n")[1].split("\n]\n")[0]+"\n]")
BO=NGAN[:10]+DAI[:6]
def rms(x): return float(np.sqrt(np.mean(x**2))) if len(x) else 0.0
def tu(s): return [t for t in re.sub(r"[^\w\s]"," ",unicodedata.normalize("NFC",s).lower()).split() if t]
def sai(a,b):
    A,B=tu(a),tu(b); sm=difflib.SequenceMatcher(None,A,B,autojunk=False); m=t=0
    for op,i1,i2,j1,j2 in sm.get_opcodes():
        if op in ("delete","replace"): m+=i2-i1
        if op in ("insert","replace"): t+=j2-j1
    return (m+t)/(2*max(1,len(A)))
def lo_hong(x,sr):
    o=int(sr*0.020); n=len(x)//o
    e=np.array([rms(x[i*o:(i+1)*o]) for i in range(n)])
    if not n: return 0,0.0
    ng=0.20*float(np.percentile(e,95)); im=e<ng; so=0;tong=0.0;i=0
    while i<n:
        if im[i]:
            j=i
            while j<n and im[j]: j+=1
            if (j-i)*20>=360: so+=1; tong+=(j-i)*20
            i=j
        else: i+=1
    return so,tong
def chu_cuoi(wav):
    segs,_=stt.transcribe(io.BytesIO(wav),language="vi",initial_prompt=MOI,
                          vad_filter=False,beam_size=5,word_timestamps=True)
    t=[w for s in segs for w in (s.words or [])]
    return unicodedata.normalize("NFC",t[-1].word.strip().lower().strip(".,?!")) if t else "∅"
async def main():
    tts=TS.F5TTSService(); tts.load()
    toc=tts.toc_do_cua("giong_heu")*tts.he_so_thoai()
    goc=TS.HE_SO_BU_LANG
    print(f"{'hệ số':>7}{'cuối mảnh':>12}{'từ sai':>9}{'lỗ hổng':>9}{'ms lỗ':>8}{'giây':>8}")
    print("-"*56)
    for hs in (0.85,0.95):
        TS.HE_SO_BU_LANG=hs
        dung=tongm=0; e=[]; lo=0; loms=0.0; giay=0.0
        for c in BO:
            manh=_cat_manh_nhu_pipeline(c)
            for m in manh:
                w=await tts.synthesize(m,voice="giong_heu",speed=toc,use_cache=False)
                mong=unicodedata.normalize("NFC",m.rstrip(".?!,").split()[-1].lower())
                tongm+=1; dung += (chu_cuoi(w)==mong)
            wav=await _ghep_nhu_pipeline(tts,manh,"giong_heu",toc,False)
            with wave.open(io.BytesIO(wav)) as w2:
                sr=w2.getframerate(); x=np.frombuffer(w2.readframes(w2.getnframes()),dtype=np.int16).astype(np.float32)/32768
            giay+=len(x)/sr
            a,b=lo_hong(x,sr); lo+=a; loms+=b
            segs,_=stt.transcribe(io.BytesIO(wav),language="vi",initial_prompt=MOI,
                                  vad_filter=False,beam_size=5)
            e.append(sai(normalize_for_tts(c)," ".join(s.text for s in segs)))
        print(f"{hs:>7.2f}{dung:>8}/{tongm}{sum(e)/len(e)*100:8.1f}%{lo:9}{loms:8.0f}{giay:8.1f}")
    TS.HE_SO_BU_LANG=goc
asyncio.run(main())
