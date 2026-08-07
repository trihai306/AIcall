"""Giọng mới gọi ra không nghe thấy gì - tại tiếng sinh ra đã câm, hay tại đường
tiêm hỏng?

Hai nguyên nhân này nhìn từ ngoài giống hệt nhau ("cuộc gọi im lặng") nhưng cách
chữa khác hẳn, nên phải tách trước khi sửa. Script chỉ đo khâu SINH: cho từng
giọng đọc cùng một câu, in mức và đỉnh ở từng chặng của đường thoại.

Giọng mẫu hỏng (quá ngắn, quá nhỏ, lời mẫu không khớp tiếng) làm F5 sinh ra tiếng
rất nhỏ hoặc gần như im - lúc đó đường tiêm hoàn toàn bình thường mà khách vẫn
không nghe thấy gì.

    python scripts/do_giong_co_tieng_khong.py
    python scripts/do_giong_co_tieng_khong.py --giong giong_nam giong_heu
"""

import argparse
import asyncio
import io
import sys
import wave
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "scripts"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

RA = PROJECT / "logs" / "do_giong"
CAU = ("Dạ em chào anh chị ạ. Em là nhân viên tư vấn của ngân hàng. "
       "Anh chị có cần em hỗ trợ thông tin gì không ạ?")


def muc(x: np.ndarray) -> tuple[float, float]:
    """(đỉnh dBFS, RMS phần có tiếng dBFS)."""
    if x.size == 0:
        return -99.0, -99.0
    dinh = float(np.abs(x).max())
    co = np.abs(x) > 0.02 * max(dinh, 1e-9)
    rms = float(np.sqrt((x[co] ** 2).mean())) if co.any() else 0.0
    return (20 * np.log10(dinh + 1e-9), 20 * np.log10(rms + 1e-9))


def ghi(p: Path, x: np.ndarray, sr: int):
    p.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--giong", nargs="+", default=["giong_nam", "giong_heu"])
    a = ap.parse_args()

    from backend.config import settings
    from backend.services import phone_call_service as PS
    from backend.services.audio_utils import resample_audio
    from backend.services.tts_service import F5TTSService

    tts = F5TTSService(); tts.load()
    RA.mkdir(parents=True, exist_ok=True)
    for p in RA.glob("*"):
        p.unlink()

    print(f"\n  câu: {CAU[:56]}...")
    print(f"  mức đích của đường thoại: PHONE_MUC_DBFS = {settings.phone_muc_dbfs}\n")
    print(f"  {'giọng':<14}{'mẫu':>7}{'đỉnh':>9}{'RMS':>9}   {'sau chuẩn mức 8k':>18}")
    print("  " + "-" * 74)

    for ten in a.giong:
        that = await tts.ensure_voice(ten)
        if that != ten:
            print(f"  {ten:<14}  KHÔNG nạp được -> rơi về '{that}'")
            continue
        ref = next((v for v in tts.list_voices() if v["name"] == ten), {})
        wav = await tts.synthesize(CAU, voice=ten, use_cache=False)
        with wave.open(io.BytesIO(wav)) as w:
            sr = w.getframerate()
            x = (np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
                 .astype(np.float32) / 32768.0)

        d, r = muc(x)
        # Đúng chuỗi của `phone_call_service.play`
        y = resample_audio(PS.chuan_muc_thoai(x), sr, 8000)
        if settings.phone_tang_tuan_hoan:
            y = PS.tang_tuan_hoan(y, 8000)
        d8, r8 = muc(y)

        ghi(RA / f"{ten}_1_goc.wav", x, sr)
        ghi(RA / f"{ten}_2_vao_cuoc_goi.wav", y, 8000)
        print(f"  {ten:<14}{ref.get('duration', 0):>6.1f}s{d:>9.1f}{r:>9.1f}   "
              f"đỉnh {d8:>6.1f}  RMS {r8:>6.1f}   ({len(x)/sr:.1f}s)")

    print("\n  Đọc kết quả: RMS gốc dưới -40 dBFS hoặc đỉnh dưới -20 là giọng mẫu")
    print("  có vấn đề, không phải đường tiêm. Hai giọng ngang nhau -> lỗi ở khâu")
    print(f"  tiêm tiếng vào cuộc gọi.\n  {RA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
