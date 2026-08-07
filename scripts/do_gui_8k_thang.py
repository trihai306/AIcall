"""Có cần TỰ đổi tần 8k->16k không, hay gửi thẳng 8kHz cho Whisper?

`faster-whisper` nhận cả file WAV rồi tự đổi tần theo header bằng bộ giải mã của
nó (`pho_server._transcribe_sync` đưa nguyên `io.BytesIO(audio_bytes)` vào
`model.transcribe`). Nếu chất lượng ngang hoặc hơn thì bỏ hẳn khâu đổi tần bên
mình là hơn:

  - hết chuyện điểm gãy ở ranh giới khối (thứ vừa biến "cần" thành "tần")
  - bỏ luôn việc nâng lại CẢ lượt mỗi 100ms - việc đó tăng theo BÌNH PHƯƠNG
    độ dài lượt, là điểm yếu của bản vá hiện tại
  - ít code hơn, và dùng một bộ đổi tần đã được kiểm kỹ thay vì bộ của mình

So ba cách trên cùng một lượt tiếng thật, kèm giờ giấc:
  A. gửi thẳng 8kHz          - để Whisper tự lo
  B. tự nâng cả đoạn một lần - bản đang chạy sau khi sửa
  C. tự nâng theo khối 100ms - bản CŨ, để đối chiếu

    python scripts/do_gui_8k_thang.py
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "scripts"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def pcm(x: np.ndarray) -> bytes:
    return (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()


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
            print("  không thấy bản ghi nào")
            return 1
        f = max(tep, key=lambda p: p.stat().st_mtime)

    x, sr = sf.read(str(f), dtype="float32", always_2d=True)
    khach = x[:, 0]
    luot, _, _ = cat_luot(khach, sr, PS)
    if not luot:
        print("  bản ghi không có lượt nào của khách")
        return 1

    stt = STTService()
    print(f"\n  {f.name} | {len(luot)} lượt\n")

    n_xet = n_khac = 0
    for i, (bd, kt, talk, du_dai) in enumerate(luot, 1):
        if not du_dai:
            continue
        n_xet += 1
        seg = khach[bd:kt]

        # A: gửi nguyên 8kHz, khai đúng tần số trong header WAV
        t0 = time.perf_counter()
        a8 = (await stt.transcribe(pcm(seg), sample_rate=8000)).strip()
        ta = (time.perf_counter() - t0) * 1000

        # B: tự nâng cả đoạn một lần (bản đang chạy)
        t0 = time.perf_counter()
        y = resample_lien_tuc(seg, 8000, 16000)
        tb_nang = (time.perf_counter() - t0) * 1000
        b16 = (await stt.transcribe(pcm(y))).strip()

        # C: tự nâng theo khối 100ms (bản cũ, đã biết là hỏng)
        n = 800
        manh = [resample_lien_tuc(seg[j:j + n], 8000, 16000)
                for j in range(0, len(seg), n)]
        c16 = (await stt.transcribe(pcm(np.concatenate(manh)))).strip()

        print(f"  lượt {i} ({talk}ms):")
        print(f"    A gửi thẳng 8kHz   {a8!r}")
        print(f"    B nâng cả đoạn     {b16!r}   (nâng {tb_nang:.1f}ms)")
        print(f"    C nâng theo khối   {c16!r}")
        if a8 != b16:
            n_khac += 1
            print("    ^^ A và B KHÁC NHAU")
        print()

    print(f"  A khác B ở {n_khac}/{n_xet} lượt.")
    if not n_khac:
        print("  -> Giống hệt: bỏ hẳn khâu đổi tần bên mình, để Whisper tự lo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
