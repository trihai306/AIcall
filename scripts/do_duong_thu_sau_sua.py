"""Chạy lại đường thu CỦA BACKEND trên tiếng cuộc gọi thật, sau khi bỏ đổi tần.

Không gọi lại điện thoại, mà bơm bản ghi vào đúng `_read_loop` đang chạy trong
backend: cùng VAD, cùng mốc đoán trước 100ms, cùng `set_audio`. Khác với
`do_gui_8k_thang.py` (chỉ so từng đoạn đã cắt sẵn), ở đây kiểm cả những chỗ dễ
sót khi đổi định dạng đệm:

  - `session.audio_rate` có tới được hai chỗ gọi STT không
  - `do_hut_tieng` còn báo hụt gấp đôi nữa không
  - đoán trước giữa lượt có đọc ra đúng chữ không

    python scripts/do_duong_thu_sau_sua.py
"""

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


async def main() -> int:
    import soundfile as sf

    from backend.pipeline.session_manager import CallSession
    from backend.services import phone_call_service as PS
    from backend.services.stt_service import STTService
    from soi_tung_luot import cat_luot

    goc = PROJECT / "data" / "recordings"
    tep = sorted(goc.rglob("*.opus")) + sorted(goc.rglob("*.wav"))
    if not tep:
        print("  không thấy bản ghi nào")
        return 1
    f = max(tep, key=lambda p: p.stat().st_mtime)

    x, sr = sf.read(str(f), dtype="float32", always_2d=True)
    khach = x[:, 0]
    luot, _, _ = cat_luot(khach, sr, PS)
    stt = STTService()

    ss = CallSession(product="vay tín chấp")
    print(f"\n  {f.name} | audio_rate mặc định = {ss.audio_rate}")
    ss.audio_rate = PS.RATE_LEN
    print(f"  sau khi mở đường thoại      = {ss.audio_rate}\n")

    for i, (bd, kt, talk, du_dai) in enumerate(luot, 1):
        if not du_dai:
            continue
        seg = khach[bd:kt]
        pcm = (np.clip(seg, -1, 1) * 32767).astype("<i2").tobytes()

        # Giữa lượt: đúng như `_read_loop` đặt lại cả lượt mỗi 100ms
        nua = len(pcm) // 2 // 2 * 2
        ss.set_audio(pcm[:nua])
        giua = (await stt.transcribe(ss.peek_audio(),
                                     sample_rate=ss.audio_rate)).strip()
        # Chốt lượt
        ss.set_audio(pcm)
        hut = ss.do_hut_tieng()
        cuoi = (await stt.transcribe(ss.take_audio(),
                                     sample_rate=ss.audio_rate)).strip()

        print(f"  lượt {i} ({talk}ms):")
        print(f"    đoán giữa lượt  {giua!r}")
        print(f"    chốt lượt       {cuoi!r}")
        if hut:
            # `giay_nhan` phải bằng ĐỘ DÀI ĐOẠN (kể cả lặng hai đầu), không phải
            # `talk` (chỉ phần có tiếng). Trước khi sửa, chỗ này chốt cứng 16kHz
            # nên báo đúng một nửa - nhìn ra như mất trắng nửa lượt.
            print(f"    đệm đọc ra {hut['giay_nhan']}s"
                  f"  (đoạn dài {len(seg)/sr:.2f}s, có tiếng {talk/1000:.2f}s)")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
