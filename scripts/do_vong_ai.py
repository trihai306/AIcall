"""Do tieng AI VONG vao kenh khach.

Trong luc kenh AI dang phat (rms >= 500), tuong quan cheo giua kenh AI va kenh
khach o do tre 0-600ms. Neu khach im ma kenh khach van 'nghe theo' AI voi do tre
on dinh -> vong. Bao:
  lag_ms      : do tre cho tuong quan cao nhat
  corr        : he so tuong quan chuan hoa tai do tre do (0 = khong lien quan)
  khach/AI dB : muc kenh khach so voi muc kenh AI trong luc AI noi (vong cang to cang gan 0)
  khach_im dB : muc kenh khach luc CA HAI im (nen)
"""
import sys, numpy as np, soundfile as sf
sys.stdout.reconfigure(encoding="utf-8")
def db(v): return 20*np.log10(max(v,1e-9))
print(f"{'file':10} | {'lag_ms':>6} | {'corr':>5} | {'khach/AI dB':>11} | {'khach_im dB':>11} | {'AI dB':>6}")
for f in sys.argv[1:]:
    x, sr = sf.read(f, always_2d=True); k, a = x[:,0], x[:,1]
    n = int(sr*0.02)
    ra = np.array([np.sqrt(np.mean(a[i:i+n]**2)) for i in range(0, len(a)-n, n)])
    rk = np.array([np.sqrt(np.mean(k[i:i+n]**2)) for i in range(0, len(k)-n, n)])
    ai_noi = ra*32768 >= 500
    ca_im = (ra*32768 < 200) & (rk*32768 < 200)
    if ai_noi.sum() < 50: print(f"{f[-13:-5]:10} | AI noi < 1s, bo"); continue
    # ghep cac doan AI noi (bo 300ms dau/cuoi moi doan de tranh khach chen)
    idx = np.where(ai_noi)[0]
    best = (0, 0.0)
    A = a - a.mean(); K = k - k.mean()
    for lag_ms in range(0, 620, 20):
        L = int(sr*lag_ms/1000)
        num = den_a = den_k = 0.0
        for i in idx[::3]:
            s, e = i*n, i*n+n
            if e+L >= len(K): continue
            aa, kk = A[s:e], K[s+L:e+L]
            num += float(np.dot(aa, kk)); den_a += float(np.dot(aa,aa)); den_k += float(np.dot(kk,kk))
        c = num/np.sqrt(den_a*den_k+1e-12)
        if abs(c) > abs(best[1]): best = (lag_ms, c)
    L = int(sr*best[0]/1000)
    rk_shift = np.array([np.sqrt(np.mean(k[i*n+L:i*n+L+n]**2)) if i*n+L+n < len(k) else 0 for i in idx])
    print(f"{f[-13:-5]:10} | {best[0]:6d} | {best[1]:5.2f} | {db(np.median(rk_shift))-db(np.median(ra[idx])):11.1f} | {db(np.median(rk[ca_im])) if ca_im.any() else float('nan'):11.1f} | {db(np.median(ra[idx])):6.1f}")
