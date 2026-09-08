"""Ba phep do tren kenh khach (chi khung AI im):

 (a) Neu dem im lang BO QUA khung 'gio' (thap >= NG) thi khoang im dai nhat trong
     vung khach dang noi la bao nhieu? So voi cach chi dung nguong RMS.
 (b) An toan: trong cac doan TIENG NOI that (dai >= 200ms, thap < 0.5), bao nhieu
     % khung co thap >= NG, va chuoi lien tiep dai nhat la bao nhieu ms?
 (c) Cac doan 'gio' thuc ra la gi: tan so dinh cua chung.
"""
import sys
import numpy as np
import soundfile as sf

f = sys.argv[1]; t0 = float(sys.argv[2]); t1 = float(sys.argv[3])
x, sr = sf.read(f, always_2d=True)
khach, ai = x[:, 0], x[:, 1]
n = int(sr * 0.02)

def rms(s): return float(np.sqrt(np.mean(s ** 2))) * 32768
def pho_khung(s):
    s = s - s.mean()
    if not np.any(s): return 0.0, 0.0
    p = np.abs(np.fft.rfft(s * np.hanning(len(s)))) ** 2
    t = np.fft.rfftfreq(len(s), 1.0 / sr)
    return float(p[t < 300].sum() / (p.sum() + 1e-12)), float(t[np.argmax(p)])

khung = []
for i in range(0, len(khach) - n, n):
    s = khach[i:i + n]
    th, fd = pho_khung(s)
    khung.append((i / sr, rms(s), th, fd, rms(ai[i:i + n]) < 200))

print(f"== {f}  vung {t0}-{t1}s ==")
print("(a) khoang im dai nhat khi dem im lang:")
for OFF in (400, 500):
    for NG in (None, 0.80, 0.70):
        im, dai = 0, 0
        for t, r, th, fd, ai_im in khung:
            if not (t0 <= t <= t1): continue
            la_im = r < OFF or (NG is not None and th >= NG)
            im = im + 20 if la_im else 0
            dai = max(dai, im)
        print(f"    OFF={OFF} bo_gio={NG!s:5} -> {dai:5d}ms")

print("(b) an toan trong TIENG NOI that:")
# doan tieng noi: chuoi khung rms>=500 lien tiep, dai >= 200ms, thap trung binh < 0.5
doan, buf = [], []
for k in khung:
    if k[1] >= 500 and k[4]: buf.append(k)
    else:
        if buf: doan.append(buf); buf = []
noi = [d for d in doan if len(d) * 20 >= 200 and np.mean([q[2] for q in d]) < 0.5]
tong = sum(len(d) for d in noi)
for NG in (0.70, 0.80, 0.90):
    so = sum(1 for d in noi for q in d if q[2] >= NG)
    chuoi = 0
    for d in noi:
        c = 0
        for q in d:
            c = c + 1 if q[2] >= NG else 0
            chuoi = max(chuoi, c)
    print(f"    NG={NG}: {so}/{tong} khung ({100*so/max(tong,1):.1f}%) trong {len(noi)} doan noi; chuoi dai nhat {chuoi*20}ms")

print("(c) cac doan gio (thap>=0.80, rms>=500, AI im): tan so dinh")
fds = [fd for t, r, th, fd, ai_im in khung if th >= 0.80 and r >= 500 and ai_im and t0 <= t <= t1]
if fds:
    h, b = np.histogram(fds, bins=[0, 60, 120, 180, 240, 300])
    print("    ", {f"{int(b[i])}-{int(b[i+1])}Hz": int(h[i]) for i in range(len(h))}, f"  (n={len(fds)}, trung vi {np.median(fds):.0f}Hz)")
