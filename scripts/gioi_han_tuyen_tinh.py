"""Gioi han tren cua khu vong TUYEN TINH tren ban ghi that: khop binh phuong toi
thieu (Wiener/LS) 512 tap voi tre uoc luong, tren cac khung AI noi. Day la muc
tot nhat ma bat ky NLMS nao co the dat (LS con 'nhin thay tuong lai').
Cung in phan bo rms_mic/rms_ref va tuong quan tung khung de hieu Geigel."""
import sys, numpy as np, soundfile as sf
sys.stdout.reconfigure(encoding="utf-8")
for f in sys.argv[1:]:
    x, sr = sf.read(f, always_2d=True); mic, ref = x[:,0].astype(np.float64), x[:,1].astype(np.float64)
    n = int(sr*0.02); T = 512
    # tre: tuong quan cheo toan cuoc, lag 0..800ms
    L = int(0.8*sr); best=(0,0)
    for lag in range(0, L, 8):
        a = ref[:len(ref)-lag]; b = mic[lag:]
        c = abs(np.dot(a,b))/(np.linalg.norm(a)*np.linalg.norm(b)+1e-9)
        if c>best[1]: best=(lag,c)
    lag = best[0]
    # khung AI noi
    ra = np.array([np.sqrt(np.mean(ref[i:i+n]**2)) for i in range(0,len(ref)-n,n)])*32768
    rm = np.array([np.sqrt(np.mean(mic[i+lag:i+lag+n]**2)) if i+lag+n<len(mic) else 0 for i in range(0,len(ref)-n,n)])*32768
    act = np.where((ra>=300))[0]
    ti_le = rm[act]/np.maximum(ra[act],1)
    print(f"== {f[-13:-5]}: tre {lag*1000/sr:.0f}ms corr {best[1]:.2f}; khung AI noi {len(act)}; ti le mic/ref: p10 {np.percentile(ti_le,10):.2f} p50 {np.percentile(ti_le,50):.2f} p90 {np.percentile(ti_le,90):.2f}; % khung Geigel(>0.9) bao noi de: {100*np.mean(ti_le>0.9):.0f}%")
    # LS: dung mau trong cac khung AI noi (chon nua dau de hoc, nua sau de kiem)
    rows, tgt = [], []
    for i in act:
        for j in range(i*n, i*n+n, 4):           # lay thua 1/4 mau cho nhe
            s = j - T + 1
            if s < 0 or j+lag >= len(mic): continue
            rows.append(ref[s:j+1][::-1]); tgt.append(mic[j+lag])
    X = np.array(rows); y = np.array(tgt)
    h = len(X)//2
    w, *_ = np.linalg.lstsq(X[:h], y[:h], rcond=None)
    for ten, sl in (("hoc", slice(0,h)), ("kiem", slice(h,None))):
        e = y[sl] - X[sl]@w
        print(f"   LS 512 tap, tap {ten}: giam {10*np.log10(np.mean(y[sl]**2)/np.mean(e**2)):.1f} dB")
    # tuong quan tung khung o tre do (max trong +-2 mau)
    cs=[]
    for i in act:
        m_ = mic[i*n+lag:i*n+lag+n]; 
        if len(m_)<n: continue
        cc=max(abs(np.dot(m_, ref[i*n+d:i*n+d+n]))/(np.linalg.norm(m_)*np.linalg.norm(ref[i*n+d:i*n+d+n])+1e-9) for d in (-2,-1,0,1,2))
        cs.append(cc)
    print(f"   tuong quan tung khung tai tre: p10 {np.percentile(cs,10):.2f} p50 {np.percentile(cs,50):.2f} p90 {np.percentile(cs,90):.2f}")
