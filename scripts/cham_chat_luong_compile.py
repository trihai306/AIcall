"""compile có làm ĐỔI CHẤT LƯỢNG không? Chấm bằng CER, không tin lý thuyết suông.

Cách chấm: dựng cùng một bộ câu bằng cả hai chế độ, cho PhoWhisper đọc lại, so
với văn bản gốc. CER là thước đo khách quan cho "đọc có đúng chữ không".
Cũng dựng file để nghe.
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

RA = Path("C:/duan/chat-ai/logs/compile")

CAU = [
    "Dạ em chào anh chị ạ. Em là nhân viên tư vấn của ngân hàng.",
    "Bên em đang có chương trình vay tín chấp lãi suất ưu đãi "
    "từ sáu phẩy năm phần trăm một năm.",
    "Dạ anh chị cần chuẩn bị chứng minh nhân dân còn hiệu lực ạ.",
    "Hạn mức vay tối đa là năm trăm triệu đồng trong vòng sáu mươi tháng.",
]


def cer(goc: str, doc_ra: str) -> float:
    import difflib
    a = "".join(ch for ch in goc.lower() if ch.isalnum() or ch == " ")
    b = "".join(ch for ch in doc_ra.lower() if ch.isalnum() or ch == " ")
    if not a:
        return 1.0
    sm = difflib.SequenceMatcher(None, a, b)
    return 1.0 - sm.ratio()


async def chay(bat: bool, ten: str):
    from backend.config import settings
    from backend.services.audio_utils import resample_audio
    from backend.services.stt_service import STTService
    from backend.services.tts_service import F5TTSService

    settings.f5tts_compile = bat
    tts = F5TTSService(); tts.load()
    await tts.synthesize("khởi động một hai ba", use_cache=False)
    stt = STTService()

    ms, cers = [], []
    for i, c in enumerate(CAU):
        t0 = time.perf_counter()
        w = await tts.synthesize(c, use_cache=False)
        ms.append((time.perf_counter() - t0) * 1000)
        (RA / f"{ten}_{i}.wav").write_bytes(w)
        with wave.open(io.BytesIO(w)) as f:
            sr = f.getframerate()
            x = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        a16 = resample_audio(x, sr, 16000)
        pcm = (np.clip(a16, -1, 1) * 32767).astype("<i2").tobytes()
        doc_ra = await stt.transcribe(pcm, sample_rate=16000)
        cers.append(cer(c, doc_ra))
    return ms, cers


async def main():
    RA.mkdir(parents=True, exist_ok=True)
    for f in RA.glob("*.wav"):
        f.unlink()

    kq = {}
    for bat, ten in ((False, "khong_compile"), (True, "co_compile")):
        kq[ten] = await chay(bat, ten)

    print(f"\n  {'câu':>5}{'không compile':>26}{'có compile':>24}")
    print(f"  {'':>5}{'ms':>12}{'CER':>10}{'ms':>12}{'CER':>10}")
    print("  " + "-" * 54)
    m0, c0 = kq["khong_compile"]
    m1, c1 = kq["co_compile"]
    for i in range(len(CAU)):
        print(f"  {i:>5}{m0[i]:>12.0f}{c0[i]:>10.3f}{m1[i]:>12.0f}{c1[i]:>10.3f}")
    print("  " + "-" * 54)
    print(f"  {'TB':>5}{np.mean(m0):>12.0f}{np.mean(c0):>10.3f}"
          f"{np.mean(m1):>12.0f}{np.mean(c1):>10.3f}")
    print(f"\n  nhanh hơn {np.mean(m0)-np.mean(m1):.0f} ms "
          f"({(np.mean(m0)-np.mean(m1))/np.mean(m0)*100:.0f}%)")
    print(f"  CER lệch  {np.mean(c1)-np.mean(c0):+.4f}  "
          f"(âm = compile đọc ĐÚNG hơn; quanh 0 = không đổi)")
    print(f"\n  file nghe thử: {RA}")


asyncio.run(main())
