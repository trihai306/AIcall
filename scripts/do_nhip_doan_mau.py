"""Đo NHỊP NÓI của đoạn mẫu, và nhịp F5 sinh ra ở từng tốc độ.

Vì sao cần: MFCC chứng minh F5 chép ĐÚNG âm sắc (0.992 với chính mình, 0.73 với
người khác). Nhưng MFCC lấy trung bình theo thời gian nên MÙ HOÀN TOÀN với nhịp
điệu. Mà tai người đánh giá "có giống người đó không" dựa rất nhiều vào nhịp.

Dự án ép speed=0.64, tức chậm hơn nhịp tự nhiên của đoạn mẫu 36%. Cùng chất
giọng nhưng sai nhịp thì nghe vẫn ra người khác.

Script trả lời: đoạn mẫu nói nhanh cỡ nào, và speed nào cho ra đúng nhịp đó.

Chạy TRÊN MÁY WIN:
    .venv\\python.exe scripts\\do_nhip_doan_mau.py
"""
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np              # noqa: E402
import soundfile as sf          # noqa: E402
import torch                    # noqa: E402

from backend.services.tts_service import F5TTSService, trim_silence  # noqa: E402

CAU = "Lãi suất vay tín chấp của bên em là từ bảy phẩy chín phần trăm một năm"
TOC = [0.64, 0.80, 0.90, 1.00]
RA = Path("C:/tmp/nhip")


def am_tiet(s: str) -> int:
    """Tiếng Việt: mỗi tiếng cách nhau bởi khoảng trắng = 1 âm tiết."""
    return len([t for t in re.split(r"\s+", s.strip()) if re.search(r"\w", t)])


def main():
    svc = F5TTSService()
    svc.load()
    from f5_tts.infer.utils_infer import infer_batch_process

    RA.mkdir(parents=True, exist_ok=True)
    print("\n  NHỊP CỦA CÁC ĐOẠN MẪU\n")
    print(f"  {'giọng':<14} {'giây':>6} {'âm tiết':>8} {'âm tiết/giây':>13} {'âm tiết/phút':>13}")
    print("  " + "-" * 58)

    thu_muc = Path("models/tts/ref_voices")
    nhip_mau = {}
    for w in sorted(thu_muc.glob("*.wav")):
        t = w.with_suffix(".txt")
        if not t.exists():
            continue
        x, sr = sf.read(w)
        if x.ndim > 1:
            x = x.mean(axis=1)
        giay = len(trim_silence(np.asarray(x, dtype=np.float32), sr)) / sr
        n = am_tiet(t.read_text(encoding="utf-8"))
        r = n / giay
        nhip_mau[w.stem] = r
        print(f"  {w.stem:<14} {giay:>6.2f} {n:>8} {r:>13.2f} {r*60:>13.0f}")

    ten = svc.default_voice_name()
    asyncio.run(svc.ensure_voice(ten))
    rw, rs, rt = svc._voices[ten]
    n_cau = am_tiet(CAU)

    print(f"\n  F5 SINH RA VỚI GIỌNG '{ten}' — nhịp đoạn mẫu {nhip_mau.get(ten, 0)*60:.0f} âm tiết/phút\n")
    print(f"  {'speed':>6} {'giây':>7} {'âm tiết/phút':>13}   so với đoạn mẫu")
    print("  " + "-" * 58)

    for sp in TOC:
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
            x, sr, _ = next(infer_batch_process(
                (rw, rs), rt, [CAU], svc._model, svc._vocoder,
                mel_spec_type="vocos", progress=None, nfe_step=32, speed=sp,
                device=svc._model.device))
        x = trim_silence(np.asarray(x), sr)
        giay = len(x) / sr
        r = n_cau / giay * 60
        goc = nhip_mau.get(ten, 0) * 60
        sf.write(RA / f"speed_{sp:.2f}.wav", x / max(1.0, float(np.abs(x).max())), sr)
        print(f"  {sp:>6.2f} {giay:>7.2f} {r:>13.0f}   {r/goc*100 if goc else 0:>5.0f}% nhịp gốc")

    print(f"\n  wav ở {RA}")
    print("\n  Đọc bảng: speed nào cho ra ~100% nhịp gốc thì đó là nhịp THẬT của người đó.")
    print("  Muốn AI nói chậm hơn mà VẪN giống người đó => phải thu đoạn mẫu")
    print("  của chính người đó đọc CHẬM, rồi chạy speed=1.0.")


if __name__ == "__main__":
    main()
