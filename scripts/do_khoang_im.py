"""Do khoang im dai nhat cua kenh khach, dung khung 20ms nhu he thong."""
import sys
import numpy as np
import soundfile as sf

f = sys.argv[1]
nguong = float(sys.argv[2]) if len(sys.argv) > 2 else 400.0
x, sr = sf.read(f, always_2d=True)
khach = x[:, 0]
n = int(sr * 0.02)
im_ms = 0
cac_khoang = []          # (giay_bat_dau, do_dai_ms)
bd = 0.0
for i in range(0, len(khach) - n, n):
    seg = khach[i:i + n]
    rms = float(np.sqrt(np.mean(seg ** 2))) * 32768
    t = i / sr
    if rms < nguong:
        if im_ms == 0:
            bd = t
        im_ms += 20
    else:
        if im_ms > 0:
            cac_khoang.append((bd, im_ms))
        im_ms = 0
if im_ms:
    cac_khoang.append((bd, im_ms))

print(f"nguong tat = {nguong:.0f}, tong {len(cac_khoang)} khoang im")
print("Cac khoang im >= 400ms:")
for bd, d in cac_khoang:
    if d >= 400:
        print(f"  giay {bd:5.1f} -> im {d:5.0f}ms {'  <== DU 1000ms, luot phai dong' if d >= 1000 else ''}")
