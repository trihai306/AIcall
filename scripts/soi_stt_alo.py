"""Đoạn "alo" bị loại ở khâu nào? Chạy đúng bộ lọc của STT trên nó.

Chạy TRÊN MÁY WINDOWS (cần máy chủ PhoWhisper).
"""
import asyncio
import sys
import wave
from pathlib import Path

import numpy as np

P = Path("C:/duan/chat-ai")
sys.path.insert(0, str(P))
sys.stdout.reconfigure(encoding="utf-8")


async def main():
    import httpx
    from backend.config import settings
    from backend.services.audio_utils import pcm_to_wav, resample_audio
    from backend.services.stt_service import (DAI_TOI_THIEU, NGUONG_KHONG_TIENG,
                                              NGUONG_TU_TIN, STTService, _don_token)

    f = P / "logs/tieng_khach/khach.wav"
    with wave.open(str(f)) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)

    # đoạn có tiếng: quanh 7.3s, lấy rộng ra một chút
    doan = {
        "chỉ đoạn alo (7.2-8.2s)": x[int(7.2 * sr):int(8.2 * sr)],
        "rộng hơn (7.0-9.0s)": x[int(7.0 * sr):int(9.0 * sr)],
        "toàn bộ 13.4s": x,
    }

    stt = STTService()
    print(f"\n  Ngưỡng đang dùng: logprob <= {NGUONG_TU_TIN} bị loại,"
          f" no_speech >= {NGUONG_KHONG_TIENG} bị loại, dài < {DAI_TOI_THIEU} bị loại\n")

    for ten, seg in doan.items():
        if seg.size < 800:
            continue
        s16 = resample_audio(seg / 32768.0, sr, 16000)
        pcm = (np.clip(s16, -1, 1) * 32767).astype("<i2").tobytes()

        # gọi thẳng máy chủ để xem SỐ THÔ trước khi bị lọc
        wav = pcm_to_wav(pcm, 16000)
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.post(f"{settings.whisper_server_url}/inference",
                             files={"file": ("a.wav", wav, "audio/wav")},
                             data={"response_format": "verbose_json",
                                   "language": "vi", "temperature": "0"})
        j = r.json()
        raw = (j.get("text") or "").strip()
        seg_list = j.get("segments") or []
        no_sp = max((d.get("no_speech_prob", 0.0) for d in seg_list), default=0.0)
        lp = min((d.get("avg_logprob", 0.0) for d in seg_list), default=0.0)

        sach = _don_token(raw)
        qua = await stt.transcribe(pcm, sample_rate=16000)

        print(f"  === {ten}  ({seg.size/sr:.2f}s) ===")
        print(f"     máy chủ trả thô : {raw!r}")
        print(f"     sau khi dọn token: {sach!r}")
        print(f"     no_speech_prob   : {no_sp:.3f}")
        print(f"     avg_logprob      : {lp:.3f}   {'-> BỊ LOẠI' if lp <= NGUONG_TU_TIN else '-> qua'}")
        print(f"     STTService trả về: {qua!r}")
        print()


asyncio.run(main())
