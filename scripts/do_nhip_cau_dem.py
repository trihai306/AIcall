import io, json, re, sys, urllib.request
sys.path.insert(0, r"C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, soundfile as sf
from pathlib import Path
from backend.services.filler_store import lay_kho
STT="http://127.0.0.1:8178/inference"
def nghe(x,sr):
    b=io.BytesIO(); sf.write(b,x,sr,format="WAV",subtype="PCM_16")
    bd=b"----x"
    body=(b"--"+bd+b"\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.wav\"\r\n"
          b"Content-Type: audio/wav\r\n\r\n"+b.getvalue()+b"\r\n--"+bd+b"--\r\n")
    r=urllib.request.Request(STT,data=body,headers={"Content-Type":"multipart/form-data; boundary=----x"})
    return json.loads(urllib.request.urlopen(r,timeout=180).read()).get("text","").strip()
theo_id={c.id: c.text for c in lay_kho().cau}
nhips=[]; cham=[]
for p in sorted((Path("data/fillers_wav")/"giong_heu").glob("*.wav")):
    goc=theo_id.get(p.name.split("__")[0])
    if not goc: continue
    x,sr=sf.read(p,dtype="float32")
    if x.ndim>1: x=x.mean(axis=1)
    n=max(1,int(sr*0.02)); k=len(x)//n
    if k<3: continue
    co=(np.abs(x[:k*n].reshape(k,n)).max(axis=1)>=0.015).sum()*0.02
    at=len([w for w in re.split(r"\s+",nghe(x,sr).strip()) if re.search(r"\w",w)])
    if at>=2 and co>0.2:
        r=at/co*60; nhips.append(r)
        cham.append((r, len(x)/sr, goc))
cham.sort()
print(f"\n  {len(nhips)} cau dem   trung vi {np.median(nhips):.0f} am tiet/phut"
      f"   khoang {min(nhips):.0f}-{max(nhips):.0f}")
print(f"  MOC: manh hoi thoai 300, nguoi that 287\n")
print("  5 CAU DEM CHAM NHAT")
for r,d,g in cham[:5]:
    print(f"    {r:>4.0f}/phut  {d:4.2f}s  {g[:40]}")
