import sys, numpy as np, soundfile as sf
sys.path.insert(0, "."); from backend.services.loc_gio import ty_le_dai_thap
x, sr = sf.read(sys.argv[1], always_2d=True); k = x[:,0]; n = int(sr*0.02)
t0, t1 = float(sys.argv[2]), float(sys.argv[3])
for i in range(int(t0*sr), int(t1*sr), n):
    s = k[i:i+n]; r = float(np.sqrt(np.mean(s**2)))*32768
    if r >= 400: print(f"{i/sr:6.2f}s rms {r:6.0f} thap {ty_le_dai_thap(s, sr):.2f}")
