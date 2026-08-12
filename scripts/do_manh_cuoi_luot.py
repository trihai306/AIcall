import io, json, re, sys, urllib.request
sys.path.insert(0, r"C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, soundfile as sf
from pathlib import Path
from backend.pipeline.text_normalizer import normalize_for_tts
STT="http://127.0.0.1:8178/inference"
def nghe(x,sr):
    b=io.BytesIO(); sf.write(b,x,sr,format="WAV",subtype="PCM_16")
    bd=b"----x"
    body=(b"--"+bd+b"\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.wav\"\r\n"
          b"Content-Type: audio/wav\r\n\r\n"+b.getvalue()+b"\r\n--"+bd+b"--\r\n")
    r=urllib.request.Request(STT,data=body,headers={"Content-Type":"multipart/form-data; boundary=----x"})
    return json.loads(urllib.request.urlopen(r,timeout=300).read()).get("text","").strip()
def at(s): return len([w for w in re.split(r"\s+",s.strip()) if re.search(r"\w",w)])
x,sr=sf.read(r"C:/tmp/hoithoai/hoi_thoai.wav",dtype="float32")
if x.ndim>1: x=x.mean(axis=1)
luot=[]; cur=[]
for l in Path(r"C:/tmp/hoithoai/bang_tra.txt").read_text(encoding="utf-8").splitlines():
    if re.match(r"\[\d+\]", l.strip()):
        if cur: luot.append(cur)
        cur=[]; continue
    m=re.match(r"\s+(\d):([\d.]+) - (\d):([\d.]+)\s+(\S+)\s+(.*?)\s*(<==.*)?$", l)
    if m:
        c=m.group(6).strip()
        if c and c!="[cau dem]":
            cur.append((int(m.group(1))*60+float(m.group(2)),
                        int(m.group(3))*60+float(m.group(4)), c))
if cur: luot.append(cur)
NG,KH=0.015,0.02
def rong(seg,sr):
    n=max(1,int(sr*KH)); k=len(seg)//n
    if k==0: return len(seg)/sr
    return float((np.abs(seg[:k*n].reshape(k,n)).max(axis=1)>=NG).sum()*KH)
giua, cuoi = [], []
print(f"\n  {'lượt':>5} {'vị trí':>8} {'nhịp':>6}  chữ")
print("  "+"-"*60)
for i, L in enumerate(luot, 1):
    for j, (t0,t1,c) in enumerate(L):
        seg=x[int(t0*sr):int(t1*sr)]
        if len(seg)<sr*0.2: continue
        n=at(nghe(seg,sr)); g=rong(seg,sr)
        if n<2 or g<0.2: continue
        r=n/g*60
        la_cuoi = (j==len(L)-1)
        (cuoi if la_cuoi else giua).append(r)
        if la_cuoi or j==0:
            print(f"  {i:>5} {'CUOI' if la_cuoi else 'dau':>8} {r:>5.0f}  {c[:34]}")
print("  "+"-"*60)
print(f"\n  manh GIUA luot : trung vi {np.median(giua):.0f} am tiet/phut  (n={len(giua)})")
print(f"  manh CUOI luot : trung vi {np.median(cuoi):.0f} am tiet/phut  (n={len(cuoi)})")
print(f"  chenh          : {(np.median(cuoi)-np.median(giua))/np.median(giua)*100:+.0f}%")
