"""Phan bo 'phan nang luong giai thich duoc' cua tung khung mic khi khop LS CUC BO
K tap quanh mot moc tre (+-8 mau), tren cac khung AI noi & mic >= 500.
Muc dich: dat nguong 'khung nay la vong'."""
import sys, numpy as np, soundfile as sf
sys.stdout.reconfigure(encoding="utf-8")
K = 8
for f in sys.argv[1:]:
    x, sr = sf.read(f, always_2d=True); mic, ref = x[:,0].astype(np.float64), x[:,1].astype(np.float64)
    n = int(sr*0.02); L = int(0.8*sr); best=(0,0)
    for lag in range(0, L, 8):
        a = ref[:len(ref)-lag]; b = mic[lag:]
        c = abs(np.dot(a,b))/(np.linalg.norm(a)*np.linalg.norm(b)+1e-9)
        if c>best[1]: best=(lag,c)
    lag = best[0]
    fr = []
    for i in range(0, len(mic)-n, n):
        rr = np.sqrt(np.mean(ref[i:i+n]**2))*32768; rm = np.sqrt(np.mean(mic[i+lag:i+lag+n]**2))*32768 if i+lag+n<len(mic) else 0
        if rr < 300 or rm < 500: continue
        m = mic[i+lag:i+lag+n]
        bestf = 0.0
        for d in range(-8, 9, 2):
            s = i + d
            if s - K < 0 or s+n > len(ref): continue
            X = np.stack([ref[s-k:s-k+n] for k in range(K)], 1)
            w, *_ = np.linalg.lstsq(X, m, rcond=None)
            e = m - X@w
            bestf = max(bestf, 1 - np.dot(e,e)/np.dot(m,m))
        fr.append(bestf)
    fr = np.array(fr)
    print(f"{f[-13:-5]}: {len(fr)} khung AI noi & mic>=500 | phan giai thich duoc p10 {np.percentile(fr,10):.2f} p50 {np.percentile(fr,50):.2f} p90 {np.percentile(fr,90):.2f} | >=0.5: {100*np.mean(fr>=0.5):.0f}%  >=0.3: {100*np.mean(fr>=0.3):.0f}%")
