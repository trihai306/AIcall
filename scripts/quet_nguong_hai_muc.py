"""Quet lai voi hai nguong. In ro cho lech de tu minh nhin, khong chi tin %."""
import difflib, io, json, re, sys, unicodedata, urllib.request
from pathlib import Path
sys.path.insert(0, r"C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, soundfile as sf
from backend.services import tts_service as T

STT = "http://127.0.0.1:8178/inference"
def nghe(x, sr):
    b = io.BytesIO(); sf.write(b, x, sr, format="WAV", subtype="PCM_16")
    bd = b"----x"
    body = (b"--"+bd+b"\r\nContent-Disposition: form-data; name=\"file\"; "
            b"filename=\"a.wav\"\r\nContent-Type: audio/wav\r\n\r\n"+b.getvalue()
            + b"\r\n--"+bd+b"--\r\n")
    r = urllib.request.Request(STT, data=body,
        headers={"Content-Type": "multipart/form-data; boundary=----x"})
    return json.loads(urllib.request.urlopen(r, timeout=300).read()).get("text","").strip()
def chuan(s):
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s)).strip()

x, sr = sf.read(r"C:/tmp/goithu/cuoc_goi_stereo.wav", dtype="float32"); ai = x[:, 1]
moc = []
for l in Path(r"C:/tmp/goithu/bang_tra.txt").read_text(encoding="utf-8").splitlines():
    m = re.match(r"\s+(\d):([\d.]+) - (\d):([\d.]+)\s+(\S+)\s+", l)
    if m and m.group(5) != "dem":
        moc.append((int(m[1])*60+float(m[2]), int(m[3])*60+float(m[4])))
manh = [ai[int(a*sr):int(b*sr)] for a, b in moc]
manh = [m for m in manh if len(m) > sr*0.3]
tong = sum(len(m) for m in manh)/sr
goc = [nghe(m, sr) for m in manh]
print(f"\n  {len(manh)} manh, tong {tong:.2f}s\n")
print(f"  {'rong':>6} {'day':>6} {'cat di':>8} {'giong':>8} {'lech':>5}")
print("  " + "-" * 40)
tot = None
for rong, day in ((0.20,0.07),(0.20,0.09),(0.25,0.07),(0.25,0.09),(0.30,0.07),(0.20,1.0)):
    cat = 0.0; gi = []; lech = []
    for i,(m, g) in enumerate(zip(manh, goc)):
        z = T.cat_lang_bia(m, sr, ti_le_lang=rong, ti_le_day=day)
        cat += (len(m)-len(z))/sr
        t = nghe(z, sr)
        r = difflib.SequenceMatcher(None, chuan(g).split(), chuan(t).split()).ratio()
        gi.append(r)
        if r < 0.97: lech.append((i, g, t))
    nhan = f"{rong*100:>5.0f}% {day*100:>5.0f}%" if day <= 1 else f"{rong*100:>5.0f}%  KHONG"
    print(f"  {nhan} {cat:>7.2f}s {np.mean(gi)*100:>7.1f}% {len(lech):>5}")
    if lech and tot is None:
        tot = lech
print("  " + "-" * 40)
print("\n  ('day = KHONG' = bo dieu kien cham day, de doi chung)")
if tot:
    print(f"\n  CHO LECH dau tien gap phai:")
    for i, g, t in tot[:3]:
        print(f"    manh {i}")
        print(f"      goc : {g[:70]}")
        print(f"      sau : {t[:70]}")
