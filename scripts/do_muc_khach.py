"""Đo mức kênh khách theo thời gian trên bản ghi, để xem nó có bao giờ đủ im không."""
import sys
import numpy as np
import soundfile as sf

f = sys.argv[1]
x, sr = sf.read(f, always_2d=True)
print(f"file: {f}  sr={sr}  kênh={x.shape[1]}  dài={len(x)/sr:.1f}s")
khach = x[:, 0]
buoc = int(sr * 0.1)
print("giay | rms | tren nguong tat 400?")
for i in range(0, len(khach) - buoc, buoc):
    seg = khach[i:i + buoc]
    rms = float(np.sqrt(np.mean(seg ** 2))) * 32768
    t = i / sr
    if 14 <= t <= 34:
        print(f"{t:5.1f} | {rms:9.0f} | {'CO' if rms >= 400 else '.'}")
