"""trim_silence moi co cat cut chu dau khong - STT lam trong tai."""
import difflib, io, json, re, sys, unicodedata, urllib.request
from pathlib import Path
sys.path.insert(0, r"C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, soundfile as sf
from backend.services.tts_service import trim_silence
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
x, sr = sf.read(r"C:/tmp/goi3/cuoc_goi_stereo.wav", dtype="float32"); ai = x[:,1]
moc=[]
for l in Path(r"C:/tmp/goi3/bang_tra.txt").read_text(encoding="utf-8").splitlines():
    m=re.match(r"\s+(\d):([\d.]+) - (\d):([\d.]+)\s+(\S+)\s+", l)
    if m and m.group(5)!="dem": moc.append((int(m[1])*60+float(m[2]), int(m[3])*60+float(m[4])))
manh=[ai[int(a*sr):int(b*sr)] for a,b in moc]; manh=[m for m in manh if len(m)>sr*0.3]
print(f"\n  {len(manh)} manh")
cat=0.0; gi=[]; lech=[]
for i,m in enumerate(manh):
    z = trim_silence(m, sr)
    cat += (len(m)-len(z))/sr
    g, t = nghe(m, sr), nghe(z, sr)
    r = difflib.SequenceMatcher(None, chuan(g).split(), chuan(t).split()).ratio()
    gi.append(r)
    if r < 0.97: lech.append((i, g, t))
print(f"  cat them : {cat:.2f}s tren tong {sum(len(m) for m in manh)/sr:.2f}s")
print(f"  giong STT: {np.mean(gi)*100:.1f}%   manh lech: {len(lech)}")
for i,g,t in lech[:3]:
    print(f"    manh {i}\n      goc: {g[:66]}\n      sau: {t[:66]}")
