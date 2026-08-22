"""Manh cang DAI thi nhip cang khong deu? Do doi chung."""
import base64, io, json, re, sys, urllib.parse, urllib.request, wave
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
TTS="http://127.0.0.1:8100/api/voices/test-tts"; GIONG="giong_heu"
KHUNG=0.010; MUOT=50; CACH=0.10; NG=0.20; N=4

CAP = [
    ("DAI  (19 am tiet, nguyen manh)",
     ["Em nhận được thông tin anh chị đang quan tâm đến gói vay thế chấp sổ đỏ bên em."]),
    ("TACH (lam 2 manh)",
     ["Em nhận được thông tin anh chị đang quan tâm,",
      "đến gói vay thế chấp sổ đỏ bên em."]),
    ("DAI  (22 am tiet, nguyen manh)",
     ["Không biết hiện tại anh chị đang có nhu cầu vay để làm gì và dự kiến cần vay khoảng bao nhiêu ạ?"]),
    ("TACH (lam 2 manh)",
     ["Không biết hiện tại anh chị đang có nhu cầu vay để làm gì,",
      "và dự kiến cần vay khoảng bao nhiêu ạ?"]),
]

def sinh(t):
    d=urllib.parse.urlencode({"text":t,"voice_name":GIONG,"cat_manh":"false"}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS,data=d),timeout=300) as r: return json.load(r)
def env_of(b64):
    with wave.open(io.BytesIO(base64.b64decode(b64))) as w:
        sr=w.getframerate(); x=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)/32768
    n=max(1,int(sr*KHUNG)); k=len(x)//n
    rms=np.sqrt((x[:k*n].reshape(k,n)**2).mean(axis=1))
    w2=max(1,int(MUOT/(KHUNG*1000)))
    return np.convolve(rms,np.ones(w2)/w2,mode="same")
def dinh(env):
    ng=env.max()*NG; cach=int(CACH/KHUNG); ra=[]
    for i in range(1,len(env)-1):
        if env[i]>=ng and env[i]>=env[i-1] and env[i]>env[i+1]:
            if ra and i-ra[-1]<cach:
                if env[i]>env[ra[-1]]: ra[-1]=i
            else: ra.append(i)
    return np.array(ra)*KHUNG

for nhan, manh in CAP:
    spread=[]
    for _ in range(N):
        ds=[]
        for m in manh:
            r=sinh(m)
            if r.get("error"): break
            d=dinh(env_of(r["audio"]))
            if len(d)>=8:
                W=5
                ds += [60.0*W/(d[i+W]-d[i]) for i in range(len(d)-W)]
        if len(ds)>3:
            spread.append((max(ds)-min(ds))/ (sum(ds)/len(ds)) * 100)
    if spread:
        print(f"{nhan:34} do lech nhip: {sum(spread)/len(spread):5.0f}%  "
              f"(tung lan: {', '.join(f'{s:.0f}' for s in spread)})")
