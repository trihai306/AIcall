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
def soi(thu_muc, nhan):
    p = Path(thu_muc)
    if not (p/"cuoc_goi_stereo.wav").exists(): print(f"  {nhan}: khong co tep"); return
    x, sr = sf.read(str(p/"cuoc_goi_stereo.wav"), dtype="float32"); ai=x[:,1]
    hang=[]
    for l in (p/"bang_tra.txt").read_text(encoding="utf-8").splitlines():
        m=re.match(r"\s+(\d):([\d.]+) - (\d):([\d.]+)\s+(\S+)\s+(.*?)(\s+<==.*)?$", l)
        if m and m.group(5)!="dem":
            c=m.group(6).strip()
            if c and c!="[câu đệm]":
                hang.append((int(m[1])*60+float(m[2]), int(m[3])*60+float(m[4]), c))
    g=[]; xau=0
    for t0,t1,chu in hang:
        seg=ai[int(t0*sr):int(t1*sr)]
        if len(seg)<sr*0.2: continue
        r=difflib.SequenceMatcher(None, chuan(normalize_for_tts(chu)).split(),
                                  chuan(nghe(seg,sr)).split()).ratio()*100
        g.append(r); xau += r < 70
    print(f"  {nhan:<22} {len(g):>3} mảnh | giống TB {np.mean(g):>5.1f}% | dưới 70%: {xau} ({xau/len(g)*100:.0f}%)")
soi(r"C:/tmp/goi7", "goi7 SINH LE (trước)")
soi(r"C:/tmp/goi8", "goi8 GOP LO (sau)")
