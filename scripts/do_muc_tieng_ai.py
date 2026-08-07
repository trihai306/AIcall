"""Tiếng AI gửi ra điện thoại có ĐỦ TO không?

Soi bản ghi cuộc gọi thấy kênh AI đỉnh ~1300 trong khi kênh khách ~26000 - lệch
20 lần. Tiếng ra quá nhỏ thì trên đường GSM nó chìm gần mức nhiễu, và bộ nén
AMR-NB lẫn bộ chặn nhiễu của mạng dễ cắt cụt những đoạn nhỏ -> người nghe thấy
"đứt quãng" dù mình không hề thiếu khung nào.

Đo ba mốc trên cùng một câu, để biết chỗ nào làm nhỏ đi:
    1. TTS vừa sinh ra
    2. sau khi hạ tần về tần số gửi đi
    3. so với mức bản ghi cuộc gọi thật

Chạy TRÊN MÁY WIN:  python scripts\\do_muc_tieng_ai.py
"""

import asyncio
import sys
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CAU = "Dạ em chào anh chị, em là Lan bên Ngân hàng ABC ạ."


def cham(ten: str, a: np.ndarray):
    dinh = float(np.abs(a).max())
    rms = float(np.sqrt((a ** 2).mean()))
    dbfs = 20 * np.log10(dinh / 32768 + 1e-12)
    print(f"  {ten:<28} đỉnh {dinh:7.0f}  rms {rms:6.0f}  = {dbfs:6.1f} dBFS")


async def main() -> int:
    import io

    import soundfile as sf

    from backend.services.audio_utils import resample_lien_tuc
    from backend.services.phone_call_service import RATE_LEN, RATE_XUONG
    from backend.services.tts_service import F5TTSService

    tts = F5TTSService()
    wav = await tts.synthesize(CAU, target_sr=RATE_XUONG, use_cache=False)
    y, sr = sf.read(io.BytesIO(wav), dtype="float32")
    print(f"\n  câu thử {len(y)/sr:.2f}s @ {sr}Hz\n")
    cham("1. TTS vừa sinh", y * 32768)

    b = resample_lien_tuc(y, sr, RATE_LEN) * 32768
    cham(f"2. hạ về {RATE_LEN}Hz (như bản ghi)", b)

    print("\n  Mức đo được trong bản ghi cuộc gọi thật: kênh AI đỉnh ~1300,")
    print("  kênh khách ~26000. Nếu mốc 2 ở đây CAO hơn hẳn 1300 thì tiếng bị")
    print("  làm nhỏ ở đâu đó SAU khi ghi - tức trên đường ra điện thoại.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
