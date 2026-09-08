"""Ra moi ban ghi cuoc goi, do do on cua KENH KHACH, xep hang.

Chi xet khung ma kenh AI im (rms < 200) de khong do trung vong tieng AI.
  snr_db     : muc tieng noi (p90 khung >= 700) so voi nen (p20 khung < 500)
  xung/phut  : so khung rms>=500 co >=80% nang luong <300Hz (xung ~200Hz)
  gio_mo     : so DOAN vuot 700 khong phai tieng noi (thap>=0.7) - loai lam mo luot nham
  noi_s      : tong giay tieng noi that
"""
import glob, os, sys
import numpy as np
import soundfile as sf

def thap(s, sr):
    s = s - s.mean()
    if not np.any(s): return 0.0
    p = np.abs(np.fft.rfft(s * np.hanning(len(s)))) ** 2
    t = np.fft.rfftfreq(len(s), 1.0 / sr)
    return float(p[t < 300].sum() / (p.sum() + 1e-12))

rows = []
for f in sorted(glob.glob("data/recordings/*/*.opus")):
    try:
        x, sr = sf.read(f, always_2d=True)
    except Exception as e:
        continue
    if x.shape[1] < 2 or len(x) < sr * 5: continue
    n = int(sr * 0.02)
    khach, ai = x[:, 0], x[:, 1]
    r_all, th_all = [], []
    for i in range(0, len(khach) - n, n):
        if np.sqrt(np.mean(ai[i:i+n]**2)) * 32768 >= 200: continue
        s = khach[i:i+n]
        r = float(np.sqrt(np.mean(s**2))) * 32768
        r_all.append(r); th_all.append(thap(s, sr) if r >= 500 else 0.0)
    r_all, th_all = np.array(r_all), np.array(th_all)
    if len(r_all) < 100: continue
    phut = len(r_all) * 0.02 / 60
    nen = np.percentile(r_all[r_all < 500], 20) if np.any(r_all < 500) else 1
    noi = r_all[(r_all >= 700) & (th_all < 0.5)]
    snr = 20 * np.log10(np.percentile(noi, 90) / max(nen, 1)) if len(noi) else 0
    xung = int(np.sum((r_all >= 500) & (th_all >= 0.8)))
    # doan vuot 700 khong phai tieng noi
    gio_mo, dang, buf = 0, False, []
    for r, th in zip(r_all, th_all):
        if not dang and r >= 700: dang, buf = True, []
        if dang:
            buf.append(th)
            if r < 500:
                dang = False
                if np.mean(buf) >= 0.7: gio_mo += 1
    rows.append((xung / phut, f, snr, xung, gio_mo, len(noi) * 0.02, phut))

rows.sort(reverse=True)
print(f"{len(rows)} ban ghi. Xep theo xung 200Hz/phut (on nhat tren cung):")
print(f"{'xung/phut':>9} | {'snr_dB':>6} | {'xung':>5} | {'gio_mo':>6} | {'noi_s':>5} | {'phut':>4} | file")
for x, f, snr, xung, gm, noi, phut in rows[:25]:
    print(f"{x:9.0f} | {snr:6.1f} | {xung:5d} | {gm:6d} | {noi:5.1f} | {phut:4.1f} | {f.replace(chr(92), '/')}")
