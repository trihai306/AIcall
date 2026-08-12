"""Đoạn mẫu dài bao nhiêu thì tốn thêm bao nhiêu thời gian sinh tiếng?

F5 chạy ODE trên CẢ đoạn mẫu lẫn đoạn sinh, nên ref dài là thuế đánh vào MỌI
lượt nói. Trước khi bàn chuyện fine-tune để tăng tốc, phải biết cắt ngắn ref
không thôi đã lấy lại được bao nhiêu.
"""
import asyncio
import io
import sys
import time
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, "C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")

RA = Path("C:/duan/chat-ai/models/tts/ref_voices")
CAU = ("Dạ em chào anh chị ạ. Bên em đang có chương trình vay tín chấp "
       "lãi suất ưu đãi từ sáu phẩy năm phần trăm một năm.")


async def main():
    from backend.config import settings
    from backend.services.stt_service import STTService
    from backend.services.tts_service import F5TTSService

    goc = RA / "giong_heu.wav"
    with wave.open(str(goc)) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    print(f"  đoạn mẫu gốc: {len(x)/sr:.1f}s\n")

    stt = STTService()
    from backend.services.audio_utils import resample_audio

    # cắt các độ dài khác nhau, LẤY TỪ ĐẦU để giữ câu liền mạch
    bien = {}
    for giay in (3.0, 4.5, 6.0, 8.4):
        seg = x[:int(giay * sr)]
        p = RA / f"_thu_{giay:.1f}s.wav"
        with wave.open(str(p), "wb") as o:
            o.setnchannels(1); o.setsampwidth(2); o.setframerate(sr)
            o.writeframes((np.clip(seg, -1, 1) * 32767).astype("<i2").tobytes())
        a16 = resample_audio(seg, sr, 16000)
        pcm = (np.clip(a16, -1, 1) * 32767).astype("<i2").tobytes()
        loi = (await stt.transcribe(pcm, sample_rate=16000)).strip()
        bien[giay] = (p, loi)
        print(f"  ref {giay:.1f}s -> lời: {loi[:60]!r}")

    print(f"\n  {'ref':>6}{'lần 1':>10}{'lần 2':>10}{'lần 3':>10}{'trung bình':>12}")
    print("  " + "-" * 50)
    for giay, (p, loi) in bien.items():
        settings.f5tts_ref_audio = f"./models/tts/ref_voices/{p.name}"
        settings.f5tts_ref_text = loi
        tts = F5TTSService()
        tts.load()
        await tts.synthesize("khởi động", use_cache=False)      # làm nóng
        ms = []
        for _ in range(3):
            t0 = time.perf_counter()
            await tts.synthesize(CAU, use_cache=False)
            ms.append((time.perf_counter() - t0) * 1000)
        print(f"  {giay:>5.1f}s{ms[0]:>10.0f}{ms[1]:>10.0f}{ms[2]:>10.0f}"
              f"{np.mean(ms):>12.0f} ms")

    # mốc: giọng cũ 3.8s
    settings.f5tts_ref_audio = "./models/tts/ref_voices/giong_ngan.wav"
    settings.f5tts_ref_text = "Xin chào anh chị, em là nhân viên tư vấn ngân hàng."
    tts = F5TTSService(); tts.load()
    await tts.synthesize("khởi động", use_cache=False)
    ms = []
    for _ in range(3):
        t0 = time.perf_counter()
        await tts.synthesize(CAU, use_cache=False)
        ms.append((time.perf_counter() - t0) * 1000)
    print(f"  {'cũ 3.8s':>6}{ms[0]:>9.0f}{ms[1]:>10.0f}{ms[2]:>10.0f}{np.mean(ms):>12.0f} ms")

    for p, _ in bien.values():
        p.unlink(missing_ok=True)


asyncio.run(main())
