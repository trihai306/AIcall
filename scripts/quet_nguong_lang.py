"""Quet TI_LE_LANG tren ban ghi that, lay STT lam trong tai.

Chon nguong LON NHAT ma STT nghe lai van ra dung chu nhu ban goc. Lon hon thi
cat duoc nhieu im lang hon, nhung qua tay se an vao chu - STT bat duoc dieu do.
"""
import difflib, io, json, re, sys, unicodedata, urllib.request
from pathlib import Path
sys.path.insert(0, r"C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, soundfile as sf
from backend.services.tts_service import cat_lang_bia

STT = "http://127.0.0.1:8178/inference"
W = r"C:/tmp/goithu/cuoc_goi_stereo.wav"; B = r"C:/tmp/goithu/bang_tra.txt"

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

x, sr = sf.read(W, dtype="float32"); ai = x[:, 1]
moc = []
for l in Path(B).read_text(encoding="utf-8").splitlines():
    m = re.match(r"\s+(\d):([\d.]+) - (\d):([\d.]+)\s+(\S+)\s+", l)
    if m and m.group(5) != "dem":
        moc.append((int(m[1])*60+float(m[2]), int(m[3])*60+float(m[4])))
manh = [ai[int(a*sr):int(b*sr)] for a, b in moc]
manh = [m for m in manh if len(m) > sr*0.3]
print(f"\n  {len(manh)} manh, tong {sum(len(m) for m in manh)/sr:.2f}s")
goc = [nghe(m, sr) for m in manh]
print(f"  da lay STT ban goc\n")
print(f"  {'ti le':>7} {'cat di':>8} {'con lai':>8} {'giong STT':>10} {'manh lech':>10}")
print("  " + "-" * 50)
for ti in (0.06, 0.12, 0.15, 0.18, 0.22, 0.26, 0.32):
    tong_cat = 0.0; giong = []; lech = 0
    for m, g in zip(manh, goc):
        z = cat_lang_bia(m, sr, ti_le_lang=ti)
        tong_cat += (len(m) - len(z)) / sr
        t = nghe(z, sr)
        r = difflib.SequenceMatcher(None, chuan(g).split(), chuan(t).split()).ratio()
        giong.append(r)
        if r < 0.97: lech += 1
    co = "  <== an vao chu" if lech else ""
    print(f"  {ti*100:>6.0f}% {tong_cat:>7.2f}s "
          f"{sum(len(m) for m in manh)/sr - tong_cat:>7.2f}s "
          f"{np.mean(giong)*100:>9.1f}% {lech:>10}{co}")
print("  " + "-" * 50)
