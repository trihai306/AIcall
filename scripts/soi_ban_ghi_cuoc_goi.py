"""Cuộc gọi ghi được 45 giây mà báo "0 lượt" - khách có nói không, hay VAD điếc?

Bản ghi của hệ thống là STEREO: kênh trái tiếng KHÁCH, kênh phải tiếng AI (xem
`services/recorder.py`). Nên nó là bằng chứng đầy đủ nhất về một cuộc gọi - đo
thẳng trên đó thay vì gọi lại để đoán.

Script tách hai kênh, đo mức từng bên, rồi chạy ĐÚNG logic VAD của `_read_loop`
trên kênh khách và phiên âm từng lượt cắt được. Ba kết cục, ba hướng sửa khác
hẳn nhau:

    kênh khách gần như im     -> khách không nói, hoặc đường thu vẫn hỏng
    có tiếng nhưng dưới ngưỡng -> ngưỡng VAD quá cao cho cuộc gọi này
    cắt được lượt, STT ra chữ  -> lỗi nằm sau đó, ở pipeline

    python scripts/soi_ban_ghi_cuoc_goi.py
    python scripts/soi_ban_ghi_cuoc_goi.py --file data/recordings/2026-08-05/abc.opus
"""

import argparse
import asyncio
import sys
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "scripts"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def muc(x: np.ndarray) -> tuple[float, float, float]:
    """(đỉnh int16, RMS int16 phần có tiếng, % thời lượng có tiếng)."""
    if x.size == 0:
        return 0.0, 0.0, 0.0
    d = float(np.abs(x).max()) * 32768
    co = np.abs(x) > 0.02 * max(float(np.abs(x).max()), 1e-9)
    r = float(np.sqrt((x[co] ** 2).mean())) * 32768 if co.any() else 0.0
    return d, r, 100.0 * co.mean()


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="")
    a = ap.parse_args()

    import soundfile as sf

    from backend.services import phone_call_service as PS
    from backend.services.audio_utils import resample_lien_tuc
    from backend.services.stt_service import STTService
    from soi_tung_luot import cat_luot

    if a.file:
        f = Path(a.file)
    else:
        goc = PROJECT / "data" / "recordings"
        tep = sorted(goc.rglob("*.opus")) + sorted(goc.rglob("*.wav"))
        if not tep:
            print(f"  không thấy bản ghi nào trong {goc}")
            return 1
        f = max(tep, key=lambda p: p.stat().st_mtime)

    x, sr = sf.read(str(f), dtype="float32", always_2d=True)
    print(f"\n  {f.name}: {len(x)/sr:.1f}s @ {sr}Hz, {x.shape[1]} kênh")

    khach = x[:, 0]
    bot = x[:, 1] if x.shape[1] > 1 else np.zeros_like(khach)
    for ten, k in (("KHÁCH (kênh trái)", khach), ("AI    (kênh phải)", bot)):
        d, r, pct = muc(k)
        print(f"  {ten}: đỉnh {d:6.0f}  RMS {r:6.0f}  có tiếng {pct:4.1f}% thời lượng")

    # Dòng thời gian từng giây: chỗ nào có tiếng, bên nào nói. Cần vì tổng thể
    # "0,4% có tiếng" không phân biệt được "khách im" với "khách nói nhưng máy
    # chỉ nhận được vài mảnh vụn".
    N = sr
    print("\n  Từng giây (K = khách, A = AI; số là RMS thang int16):")
    dong = []
    for i in range(0, min(len(khach), len(bot)) - N + 1, N):
        rk = np.sqrt((khach[i:i + N] ** 2).mean()) * 32768
        rb = np.sqrt((bot[i:i + N] ** 2).mean()) * 32768
        ky = "K" if rk >= 300 else ("a" if rb >= 300 else ".")
        if rk >= 300 and rb >= 300:
            ky = "X"
        dong.append(f"{ky}{max(rk, rb):.0f}" if ky != "." else ".")
    for i in range(0, len(dong), 20):
        print(f"    {i:>3}s | " + " ".join(dong[i:i + 20]))

    luot, nen, ng_on = cat_luot(khach, sr, PS)
    print(f"\n  nền kênh {nen:.0f} -> ngưỡng bật {ng_on:.0f} "
          f"(sàn cứng VAD_RMS_ON={PS.VAD_RMS_ON})")
    print(f"  cắt được {len(luot)} lượt\n")

    if not luot:
        # Không cắt được lượt nào: cho biết ĐỈNH cao nhất trong các khung, để
        # phân biệt "khách im" với "khách nói nhưng nhỏ hơn ngưỡng".
        N = sr * PS.FRAME_MS // 1000
        rms = np.array([np.sqrt((khach[i:i + N] ** 2).mean()) * 32768
                        for i in range(0, len(khach) - N, N)])
        print(f"  khung to nhất: {rms.max():.0f} (ngưỡng {ng_on:.0f})")
        print(f"  số khung vượt ngưỡng: {(rms >= ng_on).sum()}/{len(rms)}")
        if rms.max() < ng_on:
            print("  -> Khách KHÔNG hề nói, hoặc tiếng về quá nhỏ so với ngưỡng.")
        return 0

    stt = STTService()
    print(f"  {'#':>3}{'giây':>13}{'dài':>8}  kết quả")
    print("  " + "-" * 78)
    for i, (bd, kt, talk, du_dai) in enumerate(luot, 1):
        seg = khach[bd:kt]
        if not du_dai:
            print(f"  {i:>3}{bd/sr:>7.1f}-{kt/sr:<5.1f}{talk:>6}ms  BỎ: ngắn hơn MIN_TURN_MS")
            continue
        y = resample_lien_tuc(seg, sr, 16000)
        pcm = (np.clip(y, -1, 1) * 32767).astype("<i2").tobytes()
        nghe = (await stt.transcribe(pcm)).strip()
        ket = repr(nghe) if nghe else "BỎ: STT không nhận ra"
        print(f"  {i:>3}{bd/sr:>7.1f}-{kt/sr:<5.1f}{talk:>6}ms  {ket}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
