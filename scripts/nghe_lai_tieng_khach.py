"""Cho STT nghe lai ban ghi TRON VEN cua khach, tach theo doan co tieng.

Muc dich: doi chung voi chu ma may nghe duoc LUC GOI (luu trong app.db).
Neu ban ghi tron cho ra chu DUNG ma luc goi ra chu RAC -> loi o khau CAT,
khong phai o model hay kenh 8kHz.
"""
import asyncio
from pathlib import Path
import sys
import numpy as np
import soundfile as sf

sys.path.insert(0, str(DU_AN))
from backend.services.stt_service import STTService, moi_tu_vung  # noqa: E402
from backend.config import settings  # noqa: E402

DU_AN = Path(__file__).resolve().parents[1]

DUONG = DU_AN / "data" / "kenh_khach_4cd44fb7.wav"
NGUONG = 0.012        # bien do coi la co tieng
TOI_THIEU_MS = 400    # doan ngan hon thi bo
NOI_KHE_MS = 600      # hai doan cach nhau duoi muc nay thi noi lai


def tim_doan(x, sr):
    khung = int(sr * 0.02)
    n = len(x) // khung
    manh = np.array([np.abs(x[i * khung:(i + 1) * khung]).max() for i in range(n)])
    co = manh >= NGUONG
    doan, dang = [], None
    for i, c in enumerate(co):
        if c and dang is None:
            dang = i
        elif not c and dang is not None:
            doan.append((dang, i))
            dang = None
    if dang is not None:
        doan.append((dang, n))
    # noi cac doan gan nhau
    gop = []
    for d in doan:
        if gop and (d[0] - gop[-1][1]) * 20 <= NOI_KHE_MS:
            gop[-1] = (gop[-1][0], d[1])
        else:
            gop.append(list(d) if False else (d[0], d[1]))
            gop[-1] = (d[0], d[1])
    ket = []
    for a, b in gop:
        if (b - a) * 20 >= TOI_THIEU_MS:
            ket.append((a * khung, b * khung))
    return ket


async def main():
    x, sr = sf.read(DUONG, dtype="float32")
    if x.ndim > 1:
        x = x[:, 0]
    print(f"file: {len(x)/sr:.1f}s @ {sr}Hz")
    print(f"stt_vung_mien = {settings.stt_vung_mien!r}")

    stt = STTService()
    print("health:", await stt.health_check())

    ket = []
    doan = tim_doan(x, sr)
    print(f"\nTim duoc {len(doan)} doan co tieng khach:\n")
    for i, (a, b) in enumerate(doan, 1):
        pcm = x[a:b]
        raw = (np.clip(pcm, -1, 1) * 32767).astype(np.int16).tobytes()
        chu = await stt.transcribe(raw, sample_rate=sr)
        ket.append(f"[{i}] {a/sr:6.2f}s -> {b/sr:6.2f}s ({(b-a)/sr:4.2f}s)  {chu!r}")
        print(f"  [{i}] xong")

    import io
    with io.open(DU_AN / "data" / "ket_nghe_lai.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(ket))
    await stt.close()

asyncio.run(main())
