import asyncio, io, json, re, sys, urllib.request
sys.path.insert(0, r"C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, soundfile as sf
from backend.pipeline.text_chunker import tach_manh
from backend.services.tts_service import F5TTSService
STT="http://127.0.0.1:8178/inference"
def nghe(x,sr):
    b=io.BytesIO(); sf.write(b,x,sr,format="WAV",subtype="PCM_16")
    bd=b"----x"
    body=(b"--"+bd+b"\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.wav\"\r\n"
          b"Content-Type: audio/wav\r\n\r\n"+b.getvalue()+b"\r\n--"+bd+b"--\r\n")
    r=urllib.request.Request(STT,data=body,headers={"Content-Type":"multipart/form-data; boundary=----x"})
    return json.loads(urllib.request.urlopen(r,timeout=300).read()).get("text","").strip()
VAN=("Dạ vâng ạ, với tình hình thu nhập của anh chị thì em có thể tư vấn hạn mức "
     "lên đến năm trăm triệu đồng, thời hạn vay linh hoạt từ mười hai đến sáu mươi "
     "tháng, và lãi suất áp dụng từ bảy phẩy chín phần trăm một năm ạ.")
svc=F5TTSService(); svc.load()
ten=svc.default_voice_name(); asyncio.run(svc.ensure_voice(ten))
ra,dem=[],""
for t in VAN.split():
    dem+=" "+t
    m,dem=tach_manh(dem, first_chunk=(not ra))
    if m: ra.append(m)
if dem.strip(): ra.append(dem.strip())
print(f"\n  {len(ra)} manh   moc nguoi that: 287 am tiet/phut (rong)\n")
print(f"  {'speed':>6} {'nhip RONG':>10} {'lech moc':>9}")
print("  "+"-"*32)
for sp in (1.20, 1.40, 1.55, 1.70):
    ws=[]
    for c in ra:
        b=asyncio.run(svc.synthesize(c, voice=ten, speed=sp))
        x,srr=sf.read(io.BytesIO(b),dtype="float32")
        ws.append(x.mean(axis=1) if x.ndim>1 else x)
    y=np.concatenate(ws)
    n=max(1,int(srr*0.02)); k=len(y)//n
    co=(np.abs(y[:k*n].reshape(k,n)).max(axis=1)>=0.015).sum()*0.02
    at=len([w for w in re.split(r"\s+",nghe(y,srr).strip()) if re.search(r"\w",w)])
    r=at/co*60
    print(f"  {sp:>6.2f} {r:>9.0f} {r-287:>+9.0f}")
print("  "+"-"*32)
