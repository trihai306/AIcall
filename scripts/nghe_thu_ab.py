"""Dựng hai bản nghe thử A/B: cấu hình đang chạy vs cấu hình đề xuất.

A = giong_heu speed 0.64   (đang chạy — 61% nhịp thật của người đó, 3/3 lượt có âm rác)
B = heu_c    speed 0.90    (đề xuất  — 98% nhịp thật, 0/3 âm rác)

Cùng người thu, cùng câu, cùng model. Khác đúng hai thứ: clip mẫu và tốc độ.

Chạy TRÊN MÁY WIN:
    .venv\\python.exe scripts\\nghe_thu_ab.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np              # noqa: E402
import soundfile as sf          # noqa: E402
import torch                    # noqa: E402

from backend.services.tts_service import F5TTSService, trim_silence  # noqa: E402

CAU = [
    "Dạ em chào anh chị, em gọi từ ngân hàng để tư vấn về khoản vay tín chấp ạ.",
    "Lãi suất bên em đang là từ bảy phẩy chín phần trăm một năm, tính trên dư nợ giảm dần.",
    "Hạn mức tối đa là năm trăm triệu, thời hạn vay lên tới sáu mươi tháng.",
    "Anh chị cho em xin ít phút để em tư vấn kỹ hơn được không ạ?",
]
BAN = [("A_dang_chay", "giong_heu", 0.64), ("B_de_xuat", "heu_c", 0.90)]
RA = Path("C:/tmp/nghethu")
NGHI = 0.35   # giây nghỉ giữa hai câu


def main():
    svc = F5TTSService()
    svc.load()
    from f5_tts.infer.utils_infer import infer_batch_process

    RA.mkdir(parents=True, exist_ok=True)
    for nhan, giong, sp in BAN:
        asyncio.run(svc.ensure_voice(giong))
        rw, rs, rt = svc._voices[giong]
        manh, sr = [], 24000
        for c in CAU:
            with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
                y, sr, _ = next(infer_batch_process(
                    (rw, rs), rt, [c], svc._model, svc._vocoder,
                    mel_spec_type="vocos", progress=None, nfe_step=32, speed=sp,
                    device=svc._model.device))
            y = trim_silence(np.asarray(y), sr)
            manh.append(y / max(1.0, float(np.abs(y).max())))
            manh.append(np.zeros(int(sr * NGHI), dtype=np.float32))
        x = np.concatenate(manh)
        p = RA / f"{nhan}_{giong}_sp{sp:.2f}.wav"
        sf.write(p, x, sr)
        print(f"  {nhan:<12} {giong:<11} speed {sp:.2f}  {len(x)/sr:>5.1f}s  -> {p.name}")

    print(f"\n  wav ở {RA}")


if __name__ == "__main__":
    main()
