"""F5 có NGHỈ ở dấu câu không, hay đọc liền một mạch?

Người dùng kêu "nói nhanh" hai lần dù đã hạ tốc độ hai nấc. Có hai nguyên nhân
khác hẳn nhau, chữa ngược nhau:

  A. TỪNG CHỮ trôi nhanh      -> hạ `F5TTS_SPEED` (đang làm)
  B. KHÔNG NGHỈ ở dấu câu     -> kéo chậm cả câu KHÔNG chữa được, chỉ làm giọng
                                 nghe lê thê mà vẫn dồn dập. Phải chèn quãng
                                 lặng ở dấu phẩy/chấm.

Người thật nghỉ khoảng 150-300ms ở dấu phẩy và 400-700ms ở dấu chấm. Script đọc
một câu có nhiều dấu, rồi đo quãng lặng THẬT SỰ có trong tiếng ra.

Chạy TRÊN MÁY WIN:  python scripts\\do_nhip_ngat_cau.py
"""

import asyncio
import io
import sys
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CAU = ("Dạ em chào anh, em là Lan bên Ngân hàng ABC. "
       "Bên em có gói vay tín chấp, lãi suất bảy phẩy chín phần trăm, "
       "hạn mức tới sáu trăm triệu. Anh có quan tâm không ạ?")


async def main() -> int:
    import soundfile as sf

    from backend.config import settings
    from backend.services.tts_service import F5TTSService

    tts = F5TTSService()
    wav = await tts.synthesize(CAU, target_sr=24000, use_cache=False)
    y, sr = sf.read(io.BytesIO(wav), dtype="float32")

    N = sr // 100                                  # khung 10ms
    r = np.array([np.sqrt((y[i:i + N] ** 2).mean()) for i in range(0, len(y) - N, N)])
    nguong = max(r.max() * 0.02, np.percentile(r, 10) * 3)
    im = r < nguong

    lang, i = [], 0
    while i < len(im):
        if not im[i]:
            i += 1
            continue
        j = i
        while j < len(im) and im[j]:
            j += 1
        if (j - i) * 10 >= 80:                     # từ 80ms trở lên mới đáng kể
            lang.append((i * 10, (j - i) * 10))
        i = j

    n_phay = CAU.count(",")
    n_cham = CAU.count(".") + CAU.count("?")
    print(f"\n  speed={settings.f5tts_speed} | câu dài {len(y)/sr:.2f}s"
          f" | {n_phay} dấu phẩy, {n_cham} dấu chấm/hỏi\n")
    trong = [(t, d) for t, d in lang if 200 < t < len(y) / sr * 1000 - 200]
    for t, d in trong:
        print(f"    nghỉ {d:>4}ms tại {t/1000:5.2f}s")
    print(f"\n  {len(trong)} quãng nghỉ trong câu / {n_phay + n_cham - 1} chỗ đáng lẽ phải nghỉ")
    if len(trong) < (n_phay + n_cham - 1) * 0.6:
        print("  -> F5 ĐANG ĐỌC LIỀN MẠCH. Hạ tốc độ không chữa được cảm giác dồn dập;")
        print("     phải chèn quãng lặng ở dấu câu (tách câu ra đọc rồi ghép, hoặc")
        print("     chèn im lặng giữa các mảnh trong `streaming_pipeline`).")
    else:
        print("  -> Đã có nhịp ngắt. Cảm giác nhanh là do tốc độ đọc, cứ hạ tiếp speed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
