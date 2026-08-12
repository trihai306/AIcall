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
def rong(y,sr):
    n=max(1,int(sr*KH)); k=len(y)//n
    return float((np.abs(y[:k*n].reshape(k,n)).max(axis=1)>=NG).sum()*KH) if k else len(y)/sr
# Kenh PHAI cua ban stereo = AI
x,sr=sf.read(r"C:/tmp/goithu/cuoc_goi_stereo.wav",dtype="float32")
ai = x[:,1] if x.ndim>1 else x
rows=[]
for l in Path(r"C:/tmp/goithu/bang_tra.txt").read_text(encoding="utf-8").splitlines():
    m=re.match(r"\s+(\d):([\d.]+) - (\d):([\d.]+)\s+(\S+)\s+(.*?)\s*(<==.*)?$", l)
    if m and m.group(6).strip() and "đệm" not in m.group(6):
        rows.append((int(m.group(1))*60+float(m.group(2)),
                     int(m.group(3))*60+float(m.group(4)), m.group(6).strip()))
ket=[]
for t0,t1,c in rows:
    seg=ai[int(t0*sr):int(t1*sr)]
    if len(seg)<sr*0.2: continue
    n=at(nghe(seg,sr)); g=rong(seg,sr)
    if n>=2 and g>0.2: ket.append((n/g*60, t0, c))
ket.sort()
print(f"\n  {len(ket)} manh   trung vi {np.median([k[0] for k in ket]):.0f} am tiet/phut\n")
print("  5 MANH CHAM NHAT")
for r,t,c in ket[:5]:
    print(f"    {r:>4.0f}/phut  {int(t)//60}:{t-60*(int(t)//60):05.2f}  {c[:46]}")
print("\n  5 MANH NHANH NHAT")
for r,t,c in ket[-5:]:
    print(f"    {r:>4.0f}/phut  {int(t)//60}:{t-60*(int(t)//60):05.2f}  {c[:46]}")
print(f"\n  lech nhanh/cham: {ket[-1][0]/ket[0][0]:.2f} lan")
