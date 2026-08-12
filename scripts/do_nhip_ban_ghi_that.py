import io, json, re, sys, urllib.request
sys.path.insert(0, r"C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, soundfile as sf
STT="http://127.0.0.1:8178/inference"
def nghe(x,sr):
    b=io.BytesIO(); sf.write(b,x,sr,format="WAV",subtype="PCM_16")
    bd=b"----x"
    body=(b"--"+bd+b"\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.wav\"\r\n"
          b"Content-Type: audio/wav\r\n\r\n"+b.getvalue()+b"\r\n--"+bd+b"--\r\n")
    r=urllib.request.Request(STT,data=body,headers={"Content-Type":"multipart/form-data; boundary=----x"})
    return json.loads(urllib.request.urlopen(r,timeout=600).read()).get("text","").strip()
x,sr=sf.read(r"C:/tmp/hoithoai/hoi_thoai.wav",dtype="float32")
if x.ndim>1: x=x.mean(axis=1)
n=max(1,int(sr*0.02)); k=len(x)//n
co=(np.abs(x[:k*n].reshape(k,n)).max(axis=1)>=0.015)
giay_co=co.sum()*0.02
t=nghe(x,sr)
at=len([w for w in re.split(r"\s+",t.strip()) if re.search(r"\w",w)])
print(f"\n  ban ghi     : {len(x)/sr:.1f}s, co tieng {giay_co:.1f}s ({giay_co/(len(x)/sr)*100:.0f}%)")
print(f"  STT nghe ra : {at} am tiet")
print(f"\n  nhip THO  (ca lang) : {at/(len(x)/sr)*60:.0f} am tiet/phut")
print(f"  nhip RONG (chi tieng): {at/giay_co*60:.0f} am tiet/phut")
print(f"\n  MOC nguoi that: 220 tho / 287 rong")
