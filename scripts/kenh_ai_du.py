"""Kenh AI trong ban ghi co LIEN TUC khong? Dem chuoi khung >=200 dai nhat va tong giay."""
import sys, numpy as np, soundfile as sf
for f in sys.argv[1:]:
    x, sr = sf.read(f, always_2d=True); a = x[:,1]; n = int(sr*0.02)
    r = np.array([np.sqrt(np.mean(a[i:i+n]**2)) for i in range(0, len(a)-n, n)])*32768
    m = r >= 200
    # chuoi lien tiep va so lo trong (khung < 200 nam giua hai khung >=200 trong 100ms)
    lo = sum(1 for i in range(1, len(m)-1) if not m[i] and m[i-1] and m[i+1])
    print(f"{f[-13:-5]}: AI >=200 tong {m.sum()*0.02:.1f}s, lo trong 1 khung {lo}, p50 muc AI {np.median(r[m]) if m.any() else 0:.0f}")
