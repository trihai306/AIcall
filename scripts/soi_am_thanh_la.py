"""Liet ke moi DOAN vuot nguong bat (700) tren kenh khach, kem dac trung de
phan biet tieng noi voi am thanh la. Chi xet khung ma kenh AI im (tranh vong).

Dac trung moi doan:
  dai_ms      : do dai doan (tinh theo hysteresis bat 700 / tat 500 nhu he thong)
  rms_dinh    : muc to nhat
  thap        : ti le nang luong < 300Hz (gio ~0.9+, tieng noi < 0.21)
  phang       : do phang pho (spectral flatness) - tieng noi thap, nhieu trang cao
  zcr         : ti le doi dau - tieng xi/ma sat cao
"""
import sys
import numpy as np
import soundfile as sf

f = sys.argv[1]
x, sr = sf.read(f, always_2d=True)
khach, ai = x[:, 0], x[:, 1]
n = int(sr * 0.02)
ON, OFF = 700.0, 500.0

def rms(seg): return float(np.sqrt(np.mean(seg ** 2))) * 32768
def dac_trung(seg):
    seg = seg - seg.mean()
    if not np.any(seg): return 0.0, 0.0, 0.0
    pho = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2 + 1e-12
    tan = np.fft.rfftfreq(len(seg), 1.0 / sr)
    thap = float(pho[tan < 300].sum() / pho.sum())
    phang = float(np.exp(np.mean(np.log(pho))) / np.mean(pho))
    zcr = float(np.mean(np.abs(np.diff(np.sign(seg))) > 0))
    return thap, phang, zcr

doan, dang, bd = [], False, 0
for i in range(0, len(khach) - n, n):
    seg = khach[i:i + n]
    ai_im = rms(ai[i:i + n]) < 200
    r = rms(seg)
    if not dang and r >= ON and ai_im:
        dang, bd, buf = True, i, []
    if dang:
        buf.append(seg)
        if r < OFF:
            dang = False
            cum = np.concatenate(buf)
            th, ph, zc = dac_trung(cum)
            doan.append((bd / sr, len(buf) * 20, rms(cum), th, ph, zc))

print(f"{f}: {len(doan)} doan vuot nguong (AI im)")
print(" giay  | dai_ms | rms_dinh | thap | phang | zcr  | nhan doan")
for t, d, r, th, ph, zc in doan:
    nhan = "GIO" if th >= 0.70 else ("ngan<130" if d < 130 else ("xi/ma-sat" if zc > 0.35 else ("nhieu-phang" if ph > 0.5 else "tieng-noi")))
    print(f"{t:6.1f} | {d:6d} | {r:8.0f} | {th:.2f} | {ph:.2f} | {zc:.2f} | {nhan}")
