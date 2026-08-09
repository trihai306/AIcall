"""Đo âm rác ở ĐẦU tiếng AI, bằng cách cho STT nghe lại chính nó.

Vì sao cần script này: các phép đo phổ tần, biên độ, quãng đứt đều KHÔNG bắt
được lỗi này - đã thử cả bốn và đều báo "sạch", trong khi khách nghe rõ. Cho STT
nghe lại rồi so với chữ gốc là cách duy nhất lôi nó ra.

Lỗi trông thế này (đo 08-08, giọng có đoạn mẫu 2,21s):
    chữ gốc  : Lãi suất vay tín chấp của bên em là từ bảy phẩy chín phần trăm
    nghe lại : hướng hiếu kể nhìn lãi suất vay tín chấp của bm là từ bảy phẩy
               ^^^^^^^^^^^^^^^^^^^ F5 bịa ra, không có trong chữ gốc

Chạy TRÊN MÁY WIN, cần backend và máy chủ STT đang chạy:
    .venv\\python.exe scripts\\do_am_rac.py
    .venv\\python.exe scripts\\do_am_rac.py --giong fosd_1 --lan 5
"""
import argparse
import asyncio
import io
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np              # noqa: E402
import soundfile as sf          # noqa: E402
import torch                    # noqa: E402

from backend.config import settings                                  # noqa: E402
from backend.services.tts_service import F5TTSService, trim_silence  # noqa: E402

STT = "http://127.0.0.1:8178/inference"

# Câu thử: đủ dài để nghe rõ, có số để soi luôn chuyện đọc sai số.
CAU = "Lãi suất vay tín chấp của bên em là từ bảy phẩy chín phần trăm một năm"
# Chữ ĐẦU TIÊN của câu thật. Phiên âm không bắt đầu bằng cụm này = có âm rác
# chen trước.
DAU = "lãi suất"


def nghe_lai(x: np.ndarray, sr: int) -> str:
    b = io.BytesIO()
    sf.write(b, x, sr, format="WAV", subtype="PCM_16")
    bd = b"----x"
    body = (b"--" + bd + b"\r\nContent-Disposition: form-data; name=\"file\"; "
            b"filename=\"a.wav\"\r\nContent-Type: audio/wav\r\n\r\n"
            + b.getvalue() + b"\r\n--" + bd + b"--\r\n")
    r = urllib.request.Request(
        STT, data=body,
        headers={"Content-Type": "multipart/form-data; boundary=----x"})
    return json.loads(urllib.request.urlopen(r, timeout=180).read()).get("text", "").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--giong", default=None, help="tên giọng, mặc định lấy giọng đang dùng")
    ap.add_argument("--lan", type=int, default=5, help="thử mấy lần (F5 lấy mẫu ngẫu nhiên)")
    a = ap.parse_args()

    svc = F5TTSService()
    svc.load()
    ten = a.giong or svc.default_voice_name()
    asyncio.run(svc.ensure_voice(ten))
    rw, rs, rt = svc._voices[ten]
    dai_ref = rw.shape[-1] / rs

    from f5_tts.infer.utils_infer import infer_batch_process

    print(f"giọng     : {ten}")
    print(f"đoạn mẫu  : {dai_ref:.2f}s" + ("   <-- NGẮN QUÁ, dưới 3s" if dai_ref < 3 else ""))
    print(f"chữ gốc   : {CAU}\n")

    rac = tran = 0
    for i in range(a.lan):
        with torch.inference_mode():
            x, sr, _ = next(infer_batch_process(
                (rw, rs), rt, [CAU], svc._model, svc._vocoder,
                mel_spec_type="vocos", progress=None,
                nfe_step=settings.f5tts_nfe_step,
                speed=svc.toc_do_cua(ten), device=svc._model.device))
        x = np.asarray(x)
        dinh = float(np.abs(x).max())
        t = nghe_lai(trim_silence(x, sr), sr).lower()
        co_rac = not t.startswith(DAU)
        rac += co_rac
        tran += dinh > 1.0
        print(f"  {i+1}: {'CÓ RÁC' if co_rac else 'sạch  '} | đỉnh {dinh:.2f}"
              f"{' VƯỢT TRẦN' if dinh > 1.0 else '         '} | {t[:56]}")

    print(f"\n  âm rác      : {rac}/{a.lan}")
    print(f"  vượt trần   : {tran}/{a.lan}")
    print("\n  ĐẠT" if rac == 0 and tran == 0 else
          "\n  CHƯA ĐẠT - xem docs/thu-lai-giong-mau.md")


if __name__ == "__main__":
    main()
