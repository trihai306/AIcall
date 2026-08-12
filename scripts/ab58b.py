import asyncio, io, re, sys, time
from pathlib import Path
sys.path.insert(0, r"C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, soundfile as sf, urllib.request, json
from backend.services.tts_service import F5TTSService
STT="http://127.0.0.1:8178/inference"; NG,KH=0.015,0.02
def nghe(x,sr):
    b=io.BytesIO(); sf.write(b,x,sr,format="WAV",subtype="PCM_16")
    bd=b"----x"
    body=(b"--"+bd+b"\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.wav\"\r\n"
          b"Content-Type: audio/wav\r\n\r\n"+b.getvalue()+b"\r\n--"+bd+b"--\r\n")
    r=urllib.request.Request(STT,data=body,headers={"Content-Type":"multipart/form-data; boundary=----x"})
    return json.loads(urllib.request.urlopen(r,timeout=180).read()).get("text","").strip()
def at(s): return len([t for t in re.split(r"\s+",s.strip()) if re.search(r"\w",t)])
def ct(x,sr):
    n=max(1,int(sr*KH)); k=len(x)//n
    if k==0: return len(x)/sr
    return float((np.abs(x[:k*n].reshape(k,n)).max(axis=1)>=NG).sum()*KH)
VAN=("Dạ vâng ạ, với tình hình thu nhập của anh chị thì em có thể tư vấn hạn mức "
     "lên đến năm trăm triệu đồng, thời hạn vay linh hoạt từ mười hai đến sáu mươi "
     "tháng, và lãi suất áp dụng từ bảy phẩy chín phần trăm một năm tính trên dư nợ "
     "giảm dần ạ. Anh chị chuẩn bị giúp em chứng minh nhân dân, sổ hộ khẩu và sao kê "
     "lương ba tháng gần nhất thì bên em xử lý rất nhanh ạ.")
RA=Path(r"C:/tmp/ab58b"); RA.mkdir(parents=True,exist_ok=True)
svc=F5TTSService(); svc.load()
ten=svc.default_voice_name(); asyncio.run(svc.ensure_voice(ten))
tu=VAN.split()
print(f"\n  {'cat':>6} {'manh':>5} {'lech nhip':>10} {'sinh':>7}  tep")
print("  "+"-"*54)
for n in (5,8):
    manh,nhips,t0=[],[],time.perf_counter()
    for i in range(0,len(tu),n):
        b=asyncio.run(svc.synthesize(" ".join(tu[i:i+n]),voice=ten))
        x,sr=sf.read(io.BytesIO(b),dtype="float32")
        if x.ndim>1: x=x.mean(axis=1)
        g=ct(x,sr); a=at(nghe(x,sr))
        if a>=2 and g>0.2: nhips.append(a/g*60)
        manh.append(x)
    y=np.concatenate(manh); d=float(np.abs(y).max())
    if d>1.0: y/=d
    p=RA/f"cat_{n}_tu_bo_dau.wav"; sf.write(p,y,sr)
    tv=float(np.median(nhips)); lech=(max(nhips)-min(nhips))/tv*100
    print(f"  {n:>4} tu {len(manh):>5} {lech:>9.0f}% {time.perf_counter()-t0:>6.2f}s  {p.name}")
print("  "+"-"*54)
