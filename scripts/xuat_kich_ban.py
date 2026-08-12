"""Xuất kịch bản thành file: bản F5 gốc, và bản đúng như khách nghe qua điện thoại."""
import asyncio
import io
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, "C:/duan/chat-ai")
sys.path.insert(0, "C:/duan/chat-ai/scripts")
sys.stdout.reconfigure(encoding="utf-8")

RA = Path("C:/duan/chat-ai/logs/kich_ban")


def doc(b):
    with wave.open(io.BytesIO(b)) as w:
        return (np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
                .astype(np.float32) / 32768), w.getframerate()


def ghi(p, x, sr):
    with wave.open(str(p), "wb") as o:
        o.setnchannels(1); o.setsampwidth(2); o.setframerate(sr)
        o.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


async def main():
    from goi_doc_kich_ban import KICH_BAN
    from backend.config import settings
    from backend.services import phone_call_service as PS
    from backend.services.audio_utils import resample_audio
    from backend.services.tts_service import F5TTSService

    RA.mkdir(parents=True, exist_ok=True)
    for f in RA.glob("*.wav"):
        f.unlink()

    tts = F5TTSService()
    tts.load()
    print(f"  giọng {settings.f5tts_ref_audio} | speed {settings.f5tts_speed}\n")

    manh, sr = [], 24000
    for i, c in enumerate(KICH_BAN, 1):
        w = await tts.synthesize(c, use_cache=False)
        x, sr = doc(w)
        manh.append(x)
        print(f"  {i}/{len(KICH_BAN)}  {len(x)/sr:5.2f}s")

    nghi = np.zeros(int(0.35 * sr), dtype=np.float32)
    day = np.concatenate([y for x in manh for y in (x, nghi)])
    ghi(RA / "1_ban_goc_F5_24kHz.wav", day, sr)
    print(f"\n  bản gốc F5   : {len(day)/sr:.1f}s @ {sr}Hz")

    # đúng chuỗi đường thoại: chuẩn mức -> 8kHz -> tăng tuần hoàn
    a = PS.chuan_muc_thoai(day)
    a8 = resample_audio(a, sr, 8000)
    if settings.phone_tang_tuan_hoan:
        a8 = PS.tang_tuan_hoan(a8, 8000)
    ghi(RA / "2_sau_xu_ly_8kHz.wav", a8, 8000)

    # rồi qua bộ mã của mạng
    from tang_tuan_hoan import lay_bo_ma_amr
    qua, duong = lay_bo_ma_amr()
    ghi(RA / "3_khach_nghe_qua_AMR.wav", qua(a8), 8000)
    print(f"  qua đường thoại: 8000Hz, bộ mã {duong}")
    print(f"\n  {RA}")


asyncio.run(main())
