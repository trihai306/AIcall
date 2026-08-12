import io, json, re, sys, urllib.request
sys.path.insert(0, r"C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, soundfile as sf
from pathlib import Path
STT="http://127.0.0.1:8178/inference"
def nghe(x,sr):
    b=io.BytesIO(); sf.write(b,x,sr,format="WAV",subtype="PCM_16")
    bd=b"----x"
    body=(b"--"+bd+b"\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.wav\"\r\n"
          b"Content-Type: audio/wav\r\n\r\n"+b.getvalue()+b"\r\n--"+bd+b"--\r\n")
    r=urllib.request.Request(STT,data=body,headers={"Content-Type":"multipart/form-data; boundary=----x"})
    return json.loads(urllib.request.urlopen(r,timeout=300).read()).get("text","").strip()
def at(s): return len([w for w in re.split(r"\s+",s.strip()) if re.search(r"\w",w)])
NG,KH=0.015,0.02
def rong(seg,sr):
    n=max(1,int(sr*KH)); k=len(seg)//n
    return float((np.abs(seg[:k*n].reshape(k,n)).max(axis=1)>=NG).sum()*KH) if k else len(seg)/sr
x,sr=sf.read(r"C:/tmp/hoithoai/hoi_thoai.wav",dtype="float32")
if x.ndim>1: x=x.mean(axis=1)
luot=[]; cur=[]; ttfa=[]
for l in Path(r"C:/tmp/hoithoai/bang_tra.txt").read_text(encoding="utf-8").splitlines():
    if re.match(r"\[\d+\]", l.strip()):
        if cur: luot.append(cur)
        cur=[]; continue
    m2=re.search(r"TTFA (\d+)ms", l)
    if m2: ttfa.append(int(m2.group(1))); continue
    m=re.match(r"\s+(\d):([\d.]+) - (\d):([\d.]+)\s+(\S+)\s+(.*?)\s*(<==.*)?$", l)
    if m:
        c=m.group(6).strip()
        if c and c!="[cau dem]":
            cur.append((int(m.group(1))*60+float(m.group(2)),
                        int(m.group(3))*60+float(m.group(4))))
if cur: luot.append(cur)
print(f"\n  {'luot':>5} {'nhip':>6} {'lang giua':>10} {'TTFA':>7}")
print("  "+"-"*36)
nhips=[]
for i,L in enumerate(luot,1):
    ns=[]; lg=0
    for t0,t1 in L:
        seg=x[int(t0*sr):int(t1*sr)]
        if len(seg)<sr*0.2: continue
        n=at(nghe(seg,sr)); g=rong(seg,sr)
        if n>=2 and g>0.2: ns.append(n/g*60)
        # lang > 250ms ben trong manh
        nn=max(1,int(sr*KH)); k=len(seg)//nn
        if k>2:
            im=np.abs(seg[:k*nn].reshape(k,nn)).max(axis=1)<NG
            j=0
            while j<k:
                if im[j]:
                    e=j
                    while e<k and im[e]: e+=1
                    if j>0 and e<k and (e-j)*20>=250: lg+=1
                    j=e
                else: j+=1
    if ns:
        nhips.append(np.median(ns))
        print(f"  {i:>5} {np.median(ns):>5.0f} {lg:>10} {ttfa[i-1] if i<=len(ttfa) else 0:>6}ms")
print("  "+"-"*36)
n=len(nhips)
print(f"\n  3 luot DAU : nhip trung vi {np.median(nhips[:3]):.0f}")
print(f"  3 luot CUOI: nhip trung vi {np.median(nhips[-3:]):.0f}")
print(f"  chenh      : {(np.median(nhips[-3:])-np.median(nhips[:3]))/np.median(nhips[:3])*100:+.0f}%")
