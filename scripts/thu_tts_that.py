"""Kiểm chứng CÁCH 3 trên tiếng F5-TTS THẬT (chạy ở máy Windows có GPU).

Vì sao cần script riêng: thử nghiệm đầu tiên chạy trên Mac phải dùng mẫu thay
thế - giọng người trộn nhiễu cho tụt về mức TTS - vì Mac không chạy được F5.
Mẫu đó có phần vòng quanh: nhiễu tự thêm vào rồi tự lọc ra. Số liệu chỉ đáng
tin khi đo trên nhiễu THẬT của mô hình khuếch tán.

Chạy trên máy Windows:
    C:/duan/chat-ai/.venv/python.exe scripts/thu_tts_that.py
    ... --nghe        # dựng thêm WAV để nghe thử
"""

import argparse
import asyncio
import io
import sys
import wave
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "scripts"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Câu thật trong kịch bản bán hàng - có số, có "Dạ", có phụ âm khó.
CAU = [
    "Dạ em chào anh chị ạ. Em là nhân viên tư vấn của ngân hàng.",
    "Bên em đang có chương trình vay tín chấp lãi suất ưu đãi "
    "từ sáu phẩy năm phần trăm một năm.",
    "Anh chị có cần em hỗ trợ thêm thông tin gì không ạ?",
]


def doc_bytes(b: bytes):
    with wave.open(io.BytesIO(b)) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return x.astype("float32") / 32768, sr


async def main() -> int:
    from tang_tuan_hoan import (do_hnr, do_meo_pho, do_phang_pho, ghi_wav,
                                lay_bo_ma_amr, resample, xu_ly)

    ap = argparse.ArgumentParser()
    ap.add_argument("--nghe", action="store_true")
    ap.add_argument("--muc", type=float, nargs=2, default=[0.4, 0.7],
                    metavar=("A_LUOC", "A_DU"))
    a = ap.parse_args()

    qua_amr, duong = lay_bo_ma_amr()
    print(f"\n  Bộ mã AMR: {duong}")

    from backend.config import settings
    from backend.services.tts_service import F5TTSService

    tts = F5TTSService()
    tts.load()
    await tts.synthesize("khởi động", use_cache=False)

    # Giọng mẫu người thật - mốc trên, đi qua đúng chuỗi để so được
    ref = PROJECT / settings.f5tts_ref_audio.lstrip("./")
    print(f"  Giọng mẫu: {ref.name}   nfe={settings.f5tts_nfe_step}")

    from tang_tuan_hoan import doc_wav
    xr, srr = doc_wav(ref)
    xr8 = resample(xr, srr, 8000)
    print(f"\n  {'=' * 72}")
    print(f"  {'':<26}{'HNR vào':>9}{'sau AMR':>9}{'phẳng sau':>11}"
          f"{'méo phổ':>10}")
    print(f"  {'-' * 72}")
    yr = qua_amr(xr8)
    print(f"  {'NGƯỜI THẬT (đích)':<26}{do_hnr(xr8, 8000):>9.2f}"
          f"{do_hnr(yr, 8000):>9.2f}{do_phang_pho(yr, 8000):>11.4f}{'-':>10}")
    print(f"  {'-' * 72}")

    al, ad = a.muc
    goc_h, xu_h = [], []
    mau = {}
    for i, cau in enumerate(CAU, 1):
        w = await tts.synthesize(cau, use_cache=False)
        x, sr = doc_bytes(w)
        x8 = resample(x, sr, 8000)
        z8 = xu_ly(x8, 8000, al, ad)

        y_goc, y_xu = qua_amr(x8), qua_amr(z8)
        h_goc, h_xu = do_hnr(y_goc, 8000), do_hnr(y_xu, 8000)
        goc_h.append(h_goc)
        xu_h.append(h_xu)
        mau[f"cau{i}_chua_xu_ly"] = y_goc
        mau[f"cau{i}_co_xu_ly"] = y_xu

        print(f"  {f'câu {i} chưa xử lý':<26}{do_hnr(x8, 8000):>9.2f}"
              f"{h_goc:>9.2f}{do_phang_pho(y_goc, 8000):>11.4f}{'-':>10}")
        print(f"  {f'câu {i} CÓ xử lý':<26}{do_hnr(z8, 8000):>9.2f}"
              f"{h_xu:>9.2f}{do_phang_pho(y_xu, 8000):>11.4f}"
              f"{do_meo_pho(x8, z8, 8000):>10.2f}")

    print(f"  {'=' * 72}")
    g, u = float(np.mean(goc_h)), float(np.mean(xu_h))
    print(f"\n  Trung bình {len(CAU)} câu, tiếng F5 THẬT qua AMR-NB:")
    print(f"    chưa xử lý          {g:>6.2f} dB")
    print(f"    có xử lý ({al}, {ad})   {u:>6.2f} dB   ({u - g:+.2f} dB)")
    print(f"    người thật (đích)   {do_hnr(yr, 8000):>6.2f} dB")

    if a.nghe:
        out = PROJECT / "logs" / "cach3_tts_that"
        out.mkdir(parents=True, exist_ok=True)
        for f in out.glob("*.wav"):
            f.unlink()
        ghi_wav(out / "0_nguoi_that__qua_dien_thoai.wav", yr, 8000)
        for ten, sig in mau.items():
            ghi_wav(out / f"{ten}__qua_dien_thoai.wav", sig, 8000)
        print(f"\n  Mẫu nghe thử: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
