"""Chay bo khu vong tren BAN GHI THAT (trai = khach/mic, phai = AI/tham chieu).

Do ba thu:
  giam_dB  : muc kenh khach trong nhung khung AI dang noi ma khach im
             (mic < 0,9 x tham chieu) - truoc so voi sau. Day la vong thuan.
  doi_khach: thay doi tren khung AI im hon 1,8s (bo khu phai ngu) - phai = 0.
  cpu      : ms CPU cho moi giay tieng.
Va ghi kenh khach DA KHU ra wav de nghe doi chung (--ghi).

    python scripts/do_khu_vong_ban_ghi.py data/recordings/2026-08-05/1c1c3b16.opus --ghi
"""
import sys, time, argparse
import numpy as np
import soundfile as sf
sys.path.insert(0, ".")
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
from backend.services.khu_vong import KhuVong

def db(v): return 20 * np.log10(v + 1e-9)

ap = argparse.ArgumentParser(); ap.add_argument("files", nargs="+"); ap.add_argument("--ghi", action="store_true")
a = ap.parse_args()
print(f"{'file':10} | {'giam_dB':>7} | {'khung do':>8} | {'doi_khach dB':>12} | {'tre ms':>6} | {'tin':>4} | {'cpu ms/s':>8} | {'dong bang':>9}")
for f in a.files:
    x, sr = sf.read(f, always_2d=True)
    mic, ref = x[:, 0].astype(np.float32), x[:, 1].astype(np.float32)
    n = int(sr * 0.02)
    kv = KhuVong(sr=sr, khung=n)
    ra = np.zeros_like(mic)
    t = time.perf_counter()
    for i in range(0, len(mic) - n + 1, n):
        kv.them_tham_chieu(ref[i:i + n])
        ra[i:i + n] = kv.xu_ly(mic[i:i + n])
    cpu = (time.perf_counter() - t) * 1000 / (len(mic) / sr)
    # khung AI noi & khach im
    truoc, sau, doi = [], [], []
    ke_tu_ai = 10 ** 6
    for i in range(0, len(mic) - n + 1, n):
        r_ref = np.sqrt(np.mean(ref[i:i + n] ** 2)); r_mic = np.sqrt(np.mean(mic[i:i + n] ** 2)); r_ra = np.sqrt(np.mean(ra[i:i + n] ** 2))
        ke_tu_ai = 0 if r_ref * 32768 >= 300 else ke_tu_ai + 1
        if r_ref * 32768 >= 300 and r_mic < 0.9 * r_ref and r_mic * 32768 >= 100:
            truoc.append(r_mic); sau.append(r_ra)
        if ke_tu_ai * 20 > 1800:
            doi.append(abs(db(r_ra) - db(r_mic)))
    giam = db(np.mean(truoc)) - db(np.mean(sau)) if truoc else float("nan")
    print(f"{f[-13:-5]:10} | {giam:7.1f} | {len(truoc):8d} | {max(doi) if doi else 0:12.2f} | {kv.tre * 1000 / sr if kv.tre else -1:6.0f} | {kv.tin_tre:4.2f} | {cpu:8.0f} | {kv.khung_dong_bang:9d}")
    if a.ghi:
        out = f[:-5] + "_khu_vong.wav"
        sf.write(out, np.stack([ra, ref], 1), sr)
        print("   ghi:", out)
