import difflib, io, json, re, sys, unicodedata, urllib.request
from pathlib import Path
sys.path.insert(0, r"C:/duan/chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, soundfile as sf
from backend.pipeline.text_normalizer import normalize_for_tts
STT = "http://127.0.0.1:8178/inference"
def nghe(x, sr):
    b = io.BytesIO(); sf.write(b, x, sr, format="WAV", subtype="PCM_16"); bd=b"----x"
    body=(b"--"+bd+b"\r\nContent-Disposition: form-data; name=\"file\"; "
          b"filename=\"a.wav\"\r\nContent-Type: audio/wav\r\n\r\n"+b.getvalue()+b"\r\n--"+bd+b"--\r\n")
    r=urllib.request.Request(STT,data=body,headers={"Content-Type":"multipart/form-data; boundary=----x"})
    return json.loads(urllib.request.urlopen(r,timeout=300).read()).get("text","").strip()
def chuan(s):
    s=unicodedata.normalize("NFD",s.lower()); s="".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+"," ",re.sub(r"[^\w\s]"," ",s)).strip()
x, sr = sf.read(r"C:/tmp/goi8/cuoc_goi_stereo.wav", dtype="float32"); ai = x[:,1]
hang=[]
for l in Path(r"C:/tmp/goi8/bang_tra.txt").read_text(encoding="utf-8").splitlines():
    m=re.match(r"\s+(\d):([\d.]+) - (\d):([\d.]+)\s+(\S+)\s+(.*?)(\s+<==.*)?$", l)
    if m and m.group(5)!="dem":
        c=m.group(6).strip()
        if c and c!="[câu đệm]":
            hang.append((int(m[1])*60+float(m[2]), int(m[3])*60+float(m[4]), c))
g=[]; xau=[]
for t0,t1,chu in hang:
    seg=ai[int(t0*sr):int(t1*sr)]
    if len(seg)<sr*0.2: continue
    can=normalize_for_tts(chu); t=nghe(seg,sr)
    r=difflib.SequenceMatcher(None,chuan(can).split(),chuan(t).split()).ratio()*100
    g.append(r)
    if r<70: xau.append((t0,r,can,t))
print(f"  {len(g)} manh co chu | giong trung binh {np.mean(g):.0f}% | duoi 70%: {len(xau)}")
for t0,r,can,t in sorted(xau,key=lambda z:z[1])[:4]:
    print(f"    {int(t0)//60}:{t0-60*(int(t0)//60):05.2f} {r:.0f}%\n      nói : {can[:56]}\n      nghe: {t[:56]}")
