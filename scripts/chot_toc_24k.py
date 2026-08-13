"""Chot toc doc tren DUNG pham vi: 24kHz, cau kich ban that, thuoc do theo TU."""
import base64, difflib, io, json, re, statistics, sys, unicodedata, urllib.parse, urllib.request, wave
from pathlib import Path
import numpy as np
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from backend.pipeline.text_normalizer import normalize_for_tts
from backend.services.stt_service import moi_tu_vung
TTS="http://127.0.0.1:8100/api/voices/test-tts"; STT="http://127.0.0.1:8178/inference"
TOC="http://127.0.0.1:8100/api/voices/giong_heu/speed"; GIONG="giong_heu"; MOI=moi_tu_vung("nam")
src=open(r"C:\duan\chat-ai\scripts\nghe_lai_30_cau.py",encoding="utf-8").read()
exec("NGAN=["+src.split("CAU=[")[1].split("]\n")[0]+"]")
moi=open(r"C:\duan\chat-ai\scripts\cau_moi_12s.py",encoding="utf-8").read()
exec("MOI12=[\n"+moi.split("CAU=[\n")[1].split("\n]\n")[0]+"\n]")
CAU=NGAN[:16]+MOI12[:8]
def dat(v):
    req=urllib.request.Request(TOC,data=json.dumps({"speed":v}).encode(),
        headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=60) as r: return json.load(r)
def sinh(t):
    d=urllib.parse.urlencode({"text":t,"voice_name":GIONG,"qua_dien_thoai":"false"}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS,data=d),timeout=600) as r:
        j=json.load(r)
    return (None,None) if j.get("error") else (base64.b64decode(j["audio"]), j)
def nghe(wav):
    import uuid
    ranh=uuid.uuid4().hex; b=io.BytesIO()
    w=lambda s: b.write(s if isinstance(s,bytes) else s.encode("utf-8"))
    w(f"--{ranh}\r\n"); w('Content-Disposition: form-data; name="file"; filename="a.wav"\r\n')
    w("Content-Type: application/octet-stream\r\n\r\n"); w(wav); w("\r\n")
    for k,v in (("language","vi"),("response_format","json"),("prompt",MOI)):
        w(f"--{ranh}\r\n"); w(f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n')
    w(f"--{ranh}--\r\n")
    req=urllib.request.Request(STT,data=b.getvalue(),
        headers={"Content-Type":f"multipart/form-data; boundary={ranh}"})
    with urllib.request.urlopen(req,timeout=600) as r: return json.load(r).get("text","").strip()
VT={"vê bê banh":"vpbank","tê pê banh":"tpbank","em bê banh":"mbbank"}
def chuan(s):
    s=" ".join(re.sub(r"[^\w\s]"," ",unicodedata.normalize("NFC",s).lower()).split())
    for a,b in VT.items(): s=s.replace(a,b)
    return s
def sai(a,b):
    A,B=chuan(a).split(),chuan(b).split()
    sm=difflib.SequenceMatcher(None,A,B,autojunk=False); m=t=0
    for op,i1,i2,j1,j2 in sm.get_opcodes():
        if op in ("delete","replace"): m+=i2-i1
        if op in ("insert","replace"): t+=j2-j1
    return (m+t)/(2*max(1,len(A)))
goc=float(Path(r"C:\duan\chat-ai\models\tts\ref_voices\giong_heu.speed").read_text().strip())
print(f"{'tốc':>6}{'â.tiết/ph':>11}{'câu đạt':>10}{'từ sai':>9}")
print("-"*38)
try:
    for v in (0.90,0.94,0.98,1.02):
        dat(v); e=[];nh=[]
        for c in CAU:
            wav,j=sinh(c)
            if not wav: continue
            mong=normalize_for_tts(c); e.append(sai(mong,nghe(wav)))
            g=j["duration_ms"]/1000; nh.append(len(chuan(mong).split())/g*60)
        print(f"{v:>6.2f}{sum(nh)/len(nh):11.0f}{sum(x<=0.05 for x in e):7}/{len(e)}{sum(e)/len(e)*100:8.1f}%")
finally:
    dat(goc); print(f"\nĐã trả tốc về {goc}")
