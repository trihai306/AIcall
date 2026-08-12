"""Bitrate thấp của EDGE có làm STT nghe sai không?

Phép đo trước dùng AMR-NB 12.2k - chế độ mạng chỉ dùng khi sóng tốt. Cuộc gọi
thật chạy EDGE, nhà mạng hạ xuống 7.4k, 5.9k, thậm chí 4.75k. Đo xem CER và các
TỪ KHOÁ của kịch bản chịu được tới đâu.
"""
import asyncio
import difflib
import io
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

P = Path("C:/duan/chat-ai")
sys.path.insert(0, str(P))
sys.path.insert(0, str(P / "scripts"))
sys.stdout.reconfigure(encoding="utf-8")

CAU = [
    "Cho anh hỏi lãi suất vay tín chấp bao nhiêu",
    "Anh muốn vay hai trăm triệu trong ba mươi sáu tháng",
    "Anh có căn cước công dân và sao kê lương rồi",
    "Hạn mức tối đa của bên em là bao nhiêu",
]
TU_KHOA = ["lãi suất", "tín chấp", "căn cước", "sao kê", "hạn mức"]
CHE_DO = ["12.2k", "7.40k", "5.90k", "4.75k"]


def cer(a, b):
    a = " ".join("".join(c for c in a.lower() if c.isalnum() or c == " ").split())
    b = " ".join("".join(c for c in b.lower() if c.isalnum() or c == " ").split())
    return 1.0 - difflib.SequenceMatcher(None, a, b).ratio() if a else 1.0


def doc(b):
    with wave.open(io.BytesIO(b)) as w:
        return (np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
                .astype(np.float32) / 32768), w.getframerate()


def qua_amr(x8, br):
    from tang_tuan_hoan import doc_wav, ghi_wav
    with tempfile.TemporaryDirectory() as d:
        vao, amr, ra = (Path(d) / n for n in ("i.wav", "m.amr", "o.wav"))
        ghi_wav(vao, x8, 8000)
        for c in (["ffmpeg", "-y", "-loglevel", "error", "-i", str(vao), "-ar", "8000",
                   "-ac", "1", "-c:a", "libopencore_amrnb", "-b:a", br, str(amr)],
                  ["ffmpeg", "-y", "-loglevel", "error", "-i", str(amr), "-ar", "8000",
                   "-ac", "1", str(ra)]):
            subprocess.run(c, capture_output=True, timeout=180)
        return doc_wav(ra)[0]


async def main():
    from backend.services.audio_utils import resample_audio, resample_lien_tuc
    from backend.services.stt_service import STTService
    from backend.services.tts_service import F5TTSService

    tts = F5TTSService(); tts.load()
    await tts.synthesize("khởi động", use_cache=False)
    stt = STTService()

    tieng = []
    for c in CAU:
        x, sr = doc(await tts.synthesize(c, use_cache=False))
        tieng.append((c, resample_audio(x, sr, 8000)))

    print(f"\n  {'bitrate':<10}{'CER TB':>9}{'từ khoá mất':>14}   ví dụ nghe sai")
    print("  " + "-" * 78)
    for br in CHE_DO:
        errs, mat, tong_tk, vd = [], 0, 0, ""
        for goc, x8 in tieng:
            y = resample_lien_tuc(qua_amr(x8, br), 8000, 16000)
            pcm = (np.clip(y, -1, 1) * 32767).astype("<i2").tobytes()
            ra = await stt.transcribe(pcm, sample_rate=16000)
            errs.append(cer(goc, ra))
            tk = [t for t in TU_KHOA if t in goc.lower()]
            tong_tk += len(tk)
            thieu = [t for t in tk if t not in ra.lower()]
            mat += len(thieu)
            if thieu and not vd:
                vd = f"{thieu[0]!r} -> {ra[:40]!r}"
        print(f"  {br:<10}{np.mean(errs):>9.3f}{mat:>10}/{tong_tk}   {vd}")


asyncio.run(main())
