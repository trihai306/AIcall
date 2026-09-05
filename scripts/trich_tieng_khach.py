"""Trich TAT CA luot khach noi tu cac ban ghi cuoc goi THAT.

Dung lam bo do STT trung thuc: tieng nay da di qua GSM/AMR that, khac han giong
F5 cho qua `_mo_phong_kenh_thoai` (ham do tu ghi la "chi mo phong bang thong,
KHONG mo phong nen AMR, nen day la can tren").

Ban ghi 2 kenh: TRAI = khach, PHAI = AI (xem `recorder.py`). Luot khach that =
kenh khach manh VA kenh AI im - khong loc theo kenh AI thi vong tieng AI lot
sang kenh khach se bi cham nham thanh loi cua khach.

Chay:  .venv\\python.exe scripts\\trich_tieng_khach.py
"""
import sys
import wave
from pathlib import Path

import numpy as np

DU_AN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DU_AN))
sys.stdout.reconfigure(encoding="utf-8")

GHI = DU_AN / "data" / "recordings"
RA = DU_AN / "data" / "tieng_khach_that"
SR = 16000
KHUNG = 0.02                  # 20ms
NGUONG_KHACH = 0.10           # bien do coi la khach that su noi
NGUONG_AI = 0.02              # tren muc nay coi nhu AI dang noi
NOI_KHE_MS = 700
TOI_THIEU_MS = 350
DEM_MS = 350                  # dem truoc/sau, dung mot moc voi `dem_truoc.py`


def doc_2_kenh(f: Path):
    import subprocess
    tam = RA / "_tam.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(f), "-ar", str(SR),
                    "-f", "wav", str(tam), "-y"], check=True)
    with wave.open(str(tam)) as w:
        n, kenh = w.getnframes(), w.getnchannels()
        x = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768
    tam.unlink(missing_ok=True)
    return (x.reshape(-1, kenh) if kenh > 1 else np.stack([x, np.zeros_like(x)], 1))


def tim_luot(khach, ai):
    K = int(SR * KHUNG)
    n = len(khach) // K
    mk = np.array([np.abs(khach[i*K:(i+1)*K]).max() for i in range(n)])
    ma = np.array([np.abs(ai[i*K:(i+1)*K]).max() for i in range(n)])
    co = mk >= NGUONG_KHACH
    doan, dang = [], None
    for i, c in enumerate(co):
        if c and dang is None:
            dang = i
        elif not c and dang is not None:
            doan.append((dang, i)); dang = None
    if dang is not None:
        doan.append((dang, n))
    gop = []
    for a, b in doan:
        if gop and (a - gop[-1][1]) * KHUNG * 1000 < NOI_KHE_MS:
            gop[-1] = (gop[-1][0], b)
        else:
            gop.append((a, b))
    ket = []
    for a, b in gop:
        if (b - a) * KHUNG * 1000 < TOI_THIEU_MS:
            continue
        if ma[a:b].max() >= NGUONG_AI:      # AI dang noi -> nhieu kha nang la vong
            continue
        ket.append((a * K, b * K))
    return ket


def main():
    RA.mkdir(parents=True, exist_ok=True)
    dem = 0
    for f in sorted(GHI.rglob("*.opus")):
        try:
            x = doc_2_kenh(f)
        except Exception as e:
            print(f"  bo qua {f.name}: {e}")
            continue
        khach, ai = x[:, 0], x[:, 1]
        luot = tim_luot(khach, ai)
        print(f"{f.parent.name}/{f.stem}: {len(luot)} luot khach")
        for i, (a, b) in enumerate(luot, 1):
            a2 = max(0, a - int(DEM_MS / 1000 * SR))
            b2 = min(len(khach), b + int(DEM_MS / 1000 * SR))
            pcm = (np.clip(khach[a2:b2], -1, 1) * 32767).astype(np.int16)
            ten = RA / f"{f.parent.name}_{f.stem}_{i:02d}.wav"
            with wave.open(str(ten), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
                w.writeframes(pcm.tobytes())
            dem += 1
    print(f"\n-> {dem} luot khach, luu o {RA}")

main()
