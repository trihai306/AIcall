"""Trong luc AI noi, kenh khach vuot nguong VAD bao nhieu % khung? (vong co mo duoc luot khong)"""
import sys, numpy as np, soundfile as sf
sys.stdout.reconfigure(encoding="utf-8")
print(f"{'file':10} | {'khung AI noi':>12} | {'khach>=700':>10} | {'khach>=500':>10} | {'>=700 lien 4 khung':>18}")
for f in sys.argv[1:]:
    x, sr = sf.read(f, always_2d=True); k, a = x[:,0], x[:,1]; n = int(sr*0.02)
    ra = np.array([np.sqrt(np.mean(a[i:i+n]**2)) for i in range(0, len(a)-n, n)])*32768
    rk = np.array([np.sqrt(np.mean(k[i:i+n]**2)) for i in range(0, len(k)-n, n)])*32768
    m = ra >= 500
    on = (rk >= 700) & m; off = (rk >= 500) & m
    # chuoi >= 4 khung lien tiep >= 700 trong luc AI noi (du de MO luot / can nhac cat loi)
    chuoi, c, dem = 0, 0, 0
    for v in on:
        c = c + 1 if v else 0
        if c == 4: dem += 1
    print(f"{f[-13:-5]:10} | {int(m.sum()):12d} | {100*on.sum()/max(m.sum(),1):9.1f}% | {100*off.sum()/max(m.sum(),1):9.1f}% | {dem:18d}")
