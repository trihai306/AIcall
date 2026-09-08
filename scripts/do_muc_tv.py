"""Trong luot bi keo dai 15s: muc khach (dinh) so voi muc nen TV. Neu tach nhau ro
thi nguong tat tuong doi theo dinh luot se dong duoc luot."""
import sys, numpy as np, soundfile as sf
sys.stdout.reconfigure(encoding="utf-8")
f, t0, t1 = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
x, sr = sf.read(f, always_2d=True); k = x[:,0]; n = int(sr*0.02)
r = np.array([np.sqrt(np.mean(k[i:i+n]**2))*32768 for i in range(int(t0*sr), int(t1*sr)-n, n)])
print(f"vung {t0}-{t1}s: {len(r)} khung; p50 {np.percentile(r,50):.0f} p75 {np.percentile(r,75):.0f} p90 {np.percentile(r,90):.0f} p99 {np.percentile(r,99):.0f} dinh {r.max():.0f}")
h, b = np.histogram(r, bins=[0,200,350,500,700,1000,1500,2500,4000,8000,32768])
print("phan bo:", {f"{int(b[i])}-{int(b[i+1])}": int(h[i]) for i in range(len(h))})
# mo phong: OFF = max(500, ti_le * dinh_luot_toi_nay); dinh cap nhat trong luot; dong khi im >= 1000ms
for ti_le in (0.0, 0.10, 0.15, 0.20, 0.30):
    dinh, im, dong = 0.0, 0, None
    for j, v in enumerate(r):
        dinh = max(dinh, v)
        off = max(500.0, ti_le*dinh)
        im = im + 20 if v < off else 0
        if im >= 1000 and dong is None: dong = (j*20 - 1000)/1000
    print(f"  OFF = max(500, {ti_le:.2f} x dinh): dong luot sau {dong if dong is not None else 'KHONG'} s (dinh {dinh:.0f})")
# in duong muc thoi gian 200ms
duong = [f"{np.max(r[i:i+10]):5.0f}" for i in range(0, len(r), 10)]
print("dinh moi 200ms:", " ".join(duong))
