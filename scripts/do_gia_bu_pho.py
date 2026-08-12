"""Bộ bù phổ `toi_uu_cho_thoai` tốn bao nhiêu HNR?

Nghi vấn: đo trên đường tiếng thật ra HNR nền 4.41 dB, trong khi đo tiếng F5
trần trụi ra 6.42 dB. Khác biệt duy nhất là bộ bù phổ (lọc trầm 200Hz + nâng
2.2kHz 6dB). Nếu đúng nó ăn mất ~2 dB thì phải cân nhắc, vì nó tồn tại vì lý do
khác (loa thoại không phát được trầm, và chống vỡ tiếng).
"""
import asyncio
import io
import sys
import wave
from pathlib import Path

import numpy as np

P = Path("C:/duan/chat-ai")
sys.path.insert(0, str(P))
sys.path.insert(0, str(P / "scripts"))
sys.stdout.reconfigure(encoding="utf-8")

CAU = ("Dạ em chào anh chị ạ. Bên em đang có chương trình vay tín chấp "
       "lãi suất ưu đãi từ sáu phẩy năm phần trăm một năm.")


async def main():
    from backend.services import phone_call_service as PS
    from backend.services.audio_utils import resample_audio
    from backend.services.tts_service import F5TTSService
    from tang_tuan_hoan import do_hnr, do_phang_pho, lay_bo_ma_amr

    qua, _ = lay_bo_ma_amr()
    t = F5TTSService()
    t.load()
    await t.synthesize("khởi động", use_cache=False)
    w = await t.synthesize(CAU, use_cache=False)
    with wave.open(io.BytesIO(w)) as f:
        sr = f.getframerate()
        x = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16)
    x = x.astype(np.float32) / 32768

    print()
    print(f"    {'':<36}{'HNR':>8}{'phẳng':>10}{'đỉnh':>8}")
    print("    " + "-" * 62)
    for ten, fn in (
        ("KHÔNG bù phổ (chỉ chuẩn mức)", lambda s: PS.chuan_muc_thoai(s)),
        ("CÓ bù phổ (toi_uu_cho_thoai)", lambda s: PS.toi_uu_cho_thoai(s, sr)),
    ):
        a = resample_audio(fn(x), sr, 8000)
        y = qua(a)
        print(f"    {ten:<36}{do_hnr(y, 8000):>8.2f}"
              f"{do_phang_pho(y, 8000):>10.4f}{np.abs(a).max():>8.3f}")
        b = PS.tang_tuan_hoan(a, 8000)
        y2 = qua(b)
        print(f"    {'  + tăng tuần hoàn':<36}{do_hnr(y2, 8000):>8.2f}"
              f"{do_phang_pho(y2, 8000):>10.4f}{np.abs(b).max():>8.3f}")
    print("    " + "-" * 62)
    print("    Bù phổ tồn tại để chống vỡ tiếng và bù loa thoại thiếu trầm —")
    print("    đừng tắt chỉ vì HNR, phải nghe cả hai.")


asyncio.run(main())
