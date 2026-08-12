"""Dựng 4 phương án đường tiếng để nghe cạnh nhau, tất cả đã qua AMR-NB."""
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
       "lãi suất ưu đãi từ sáu phẩy năm phần trăm một năm. "
       "Anh chị có cần em hỗ trợ thêm thông tin gì không ạ?")


async def main():
    from backend.services import phone_call_service as PS
    from backend.services.audio_utils import resample_audio
    from backend.services.tts_service import F5TTSService
    from tang_tuan_hoan import do_hnr, ghi_wav, lay_bo_ma_amr

    qua, _ = lay_bo_ma_amr()
    t = F5TTSService()
    t.load()
    await t.synthesize("khởi động", use_cache=False)
    w = await t.synthesize(CAU, use_cache=False)
    with wave.open(io.BytesIO(w)) as f:
        sr = f.getframerate()
        x = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16)
    x = x.astype(np.float32) / 32768

    khong_bu = resample_audio(PS.chuan_muc_thoai(x), sr, 8000)
    co_bu = resample_audio(PS.toi_uu_cho_thoai(x, sr), sr, 8000)

    pa = {
        "1_hien_tai_truoc_khi_sua": co_bu,
        "2_bu_pho_VA_tuan_hoan": PS.tang_tuan_hoan(co_bu, 8000),
        "3_khong_bu_pho_chi_chuan_muc": khong_bu,
        "4_khong_bu_pho_CO_tuan_hoan": PS.tang_tuan_hoan(khong_bu, 8000),
    }

    out = P / "logs" / "bon_phuong_an"
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.wav"):
        f.unlink()
    print()
    for ten, sig in pa.items():
        y = qua(sig)
        ghi_wav(out / f"{ten}__qua_dien_thoai.wav", y, 8000)
        print(f"    {ten:<34}{do_hnr(y, 8000):>7.2f} dB")
    print(f"\n    {out}")


asyncio.run(main())
