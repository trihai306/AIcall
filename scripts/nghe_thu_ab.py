"""Dựng A/B qua đúng chuỗi âm thanh cuộc gọi 8 kHz.

A = giọng hiện tại, NFE 12 (cấu hình cũ)
B = cùng giọng, cùng tốc độ, NFE 16 (cấu hình nâng chất lượng)
C = tùy chọn: clip tham chiếu dài hơn của cùng người, để nghe trước khi đổi giọng

Chạy trên Windows khi backend đã dừng:
    set F5TTS_COMPILE=false
    .venv\\python.exe scripts\\nghe_thu_ab.py
"""
import asyncio
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np  # noqa: E402

from backend.services.phone_call_service import (  # noqa: E402
    RATE_XUONG,
    _wav_to_pcm,
    xu_ly_tieng_xuong,
)
from backend.services.tts_service import F5TTSService  # noqa: E402

CAU = [
    "Dạ, em chào anh chị. Em gọi từ ngân hàng để tư vấn về khoản vay tín chấp ạ.",
    "Lãi suất bên em đang là từ bảy phẩy chín phần trăm một năm, tính trên dư nợ giảm dần.",
    "Hạn mức tối đa là năm trăm triệu, thời hạn vay lên tới sáu mươi tháng.",
    "Anh chị cho em xin ít phút để em tư vấn kỹ hơn được không ạ?",
]
BAN = [
    ("A_cu_nfe12", "heu_a6_35", 0.98, 12),
    ("B_moi_nfe16", "heu_a6_35", 0.98, 16),
    ("C_tham_chieu_dai", "heu_c", 1.00, 16),
]
RA = Path(r"C:\tmp\nghethu")
NGHI = 0.35


def ghi_wav(path: Path, audio: np.ndarray) -> None:
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE_XUONG)
        w.writeframes(pcm.tobytes())


async def main() -> None:
    svc = F5TTSService()
    svc.load()
    RA.mkdir(parents=True, exist_ok=True)
    lang = np.zeros(int(RATE_XUONG * NGHI), dtype=np.float32)

    for nhan, giong, speed, nfe in BAN:
        await svc.ensure_voice(giong)
        manh = []
        for cau in CAU:
            wav = await svc.synthesize(
                cau, target_sr=24000, voice=giong, speed=speed,
                nfe_step=nfe, use_cache=False,
            )
            audio, sr = _wav_to_pcm(wav)
            manh.extend((xu_ly_tieng_xuong(audio, sr), lang))
        ra = np.concatenate(manh[:-1]).astype(np.float32)
        path = RA / f"{nhan}_{giong}_sp{speed:.2f}.wav"
        ghi_wav(path, ra)
        print(
            f"{nhan:<20} {giong:<11} speed={speed:.2f} nfe={nfe:<2} "
            f"{len(ra) / RATE_XUONG:>5.1f}s -> {path}"
        )


if __name__ == "__main__":
    asyncio.run(main())
