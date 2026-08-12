"""Nội dung file là NÓI hay HÁT? Cho STT nghe vài đoạn rải đều."""
import asyncio
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, "C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")

F = Path(r"C:\Users\Admin\Desktop\giọng Hêu.wav")
RA = Path("C:/duan/chat-ai/logs/giong_moi")


async def main():
    from backend.services.audio_utils import resample_audio
    from backend.services.stt_service import STTService

    RA.mkdir(parents=True, exist_ok=True)
    for f in RA.glob("*.wav"):
        f.unlink()

    stt = STTService()
    with wave.open(str(F), "rb") as w:
        sr, nch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        for i, frac in enumerate((0.10, 0.30, 0.50, 0.70, 0.90), 1):
            w.setpos(int(n * frac))
            b = w.readframes(sr * 12)                   # 12 giây
            a = np.frombuffer(b, dtype=np.int16).astype(np.float32)
            if nch > 1:
                a = a.reshape(-1, nch).mean(axis=1)
            a = a / 32768.0

            # lưu bản 24kHz mono để nghe / dùng làm giọng mẫu
            a24 = resample_audio(a, sr, 24000)
            p = RA / f"mau_{i}_{int(frac*100)}pc.wav"
            with wave.open(str(p), "wb") as o:
                o.setnchannels(1); o.setsampwidth(2); o.setframerate(24000)
                o.writeframes((np.clip(a24, -1, 1) * 32767).astype("<i2").tobytes())

            a16 = resample_audio(a, sr, 16000)
            pcm = (np.clip(a16, -1, 1) * 32767).astype("<i2").tobytes()
            txt = await stt.transcribe(pcm, sample_rate=16000)
            print(f"  [{int(frac*100):>2}% - giây {int(n*frac/sr)}]  {txt!r}")

    print(f"\n  Mẫu 24kHz để nghe: {RA}")


asyncio.run(main())
