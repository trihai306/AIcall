"""Gioi han LS tuyen tinh KHOP CHI TREN KHUNG VONG THUAN (tuong quan tung khung
tai moc tre >= 0.6 -> khong co khach noi de), danh gia tren khung giu lai.
So sanh 512 tap va 64 tap."""
import sys, numpy as np, soundfile as sf
sys.stdout.reconfigure(encoding="utf-8")
for f in sys.argv[1:]:
    x, sr = sf.read(f, always_2d=True); mic, ref = x[:,0].astype(np.float64), x[:,1].astype(np.float64)
    n = int(sr*0.02); L = int(0.8*sr); best=(0,0)
    for lag in range(0, L, 8):
        a = ref[:len(ref)-lag]; b = mic[lag:]
        c = abs(np.dot(a,b))/(np.linalg.norm(a)*np.linalg.norm(b)+1e-9)
        if c>best[1]: best=(lag,c)
    lag = best[0]
    vong = []
    for i in range(0, len(mic)-n-lag, n):
        r = ref[i:i+n]; m = mic[i+lag:i+lag+n]
        if np.sqrt(np.mean(r**2))*32768 < 300 or np.sqrt(np.mean(m**2))*32768 < 100: continue
        cc = max(abs(np.dot(m, ref[i+d:i+d+n]))/(np.linalg.norm(m)*np.linalg.norm(ref[i+d:i+d+n])+1e-9) for d in range(-4,5))
        if cc >= 0.6: vong.append(i)
    print(f"== {f[-13:-5]}: tre {lag*1000/sr:.0f}ms, {len(vong)} khung vong thuan ({len(vong)*0.02:.1f}s)")
    for T in (512, 64):
        rows, tgt = [], []
        for i in vong:
            for j in range(i*1, i+n, 2):
                s = j - T + 1
                if s < 0 or j+lag >= len(mic): continue
                rows.append(ref[s:j+1][::-1]); tgt.append(mic[j+lag])
        X = np.array(rows); y = np.array(tgt)
        if len(X) < 4*T: print(f"   T={T}: khong du mau ({len(X)})"); continue
        h = len(X)//2
        w, *_ = np.linalg.lstsq(X[:h], y[:h], rcond=None)
        e_h = y[:h]-X[:h]@w; e_k = y[h:]-X[h:]@w
        print(f"   T={T:3d}: giam tap hoc {10*np.log10(np.mean(y[:h]**2)/np.mean(e_h**2)):5.1f} dB | giu lai {10*np.log10(np.mean(y[h:]**2)/np.mean(e_k**2)):5.1f} dB")
