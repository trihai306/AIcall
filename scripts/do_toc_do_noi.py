"""Núm `F5TTS_SPEED` thật sự đổi nhịp nói bao nhiêu?

Chỉnh tốc độ bằng cách đoán số rồi gọi thử là tốn thời gian của người dùng - mỗi
vòng là một cuộc gọi. Script đọc CÙNG một câu ở nhiều mức, đo thời lượng và quy
ra chữ/phút, để chọn đúng mức trong một lần.

Mốc để so - ĐẾM THEO ÂM TIẾT, không phải "từ" kiểu tiếng Anh. Tiếng Việt viết
rời từng âm tiết nên `text.split()` ra âm tiết. Người Việt nói chuyện bình
thường khoảng 240-300 âm tiết/phút (4-5 âm tiết/giây); chậm rãi, dễ nghe qua
điện thoại là 220-250. Lấy nhầm mốc 130-160 của tiếng Anh thì mọi mức đều nhìn
ra "quá nhanh" và sẽ chỉnh hỏng.

Lưu ý: PHẢI tắt bộ nhớ đệm. Khoá đệm của `synthesize` KHÔNG chứa tốc độ, nên
không tắt thì mọi mức đều trả về đúng một bản ghi đã đọc từ mức đầu tiên.

Chạy TRÊN MÁY WIN:  python scripts\\do_toc_do_noi.py
"""

import asyncio
import io
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CAU = ("Dạ em chào anh chị, em là Lan bên Ngân hàng ABC. "
       "Bên em đang có chương trình vay tín chấp lãi suất bảy phẩy chín phần trăm ạ.")


async def main() -> int:
    import soundfile as sf

    from backend.config import settings
    from backend.services.tts_service import F5TTSService

    tts = F5TTSService()
    so_chu = len(CAU.split())
    goc = settings.f5tts_speed
    print(f"\n  câu {so_chu} chữ | đang đặt F5TTS_SPEED={goc}\n")
    print(f"  {'speed':>6} {'thời lượng':>11} {'chữ/phút':>9}   so với hiện tại")

    nen = None
    for sp in (0.90, 0.82, 0.76, 0.70, 0.64, 0.58):
        settings.f5tts_speed = sp
        wav = await tts.synthesize(CAU, target_sr=24000, use_cache=False)
        y, sr = sf.read(io.BytesIO(wav), dtype="float32")
        giay = len(y) / sr
        cpm = so_chu / giay * 60
        if abs(sp - goc) < 1e-9:
            nen = giay
        cs = f"{(giay/nen - 1) * 100:+.0f}%" if nen else ""
        dau = " <- hiện tại" if abs(sp - goc) < 1e-9 else ""
        print(f"  {sp:>6.2f} {giay:>10.2f}s {cpm:>9.0f}   {cs:>6}{dau}")

    settings.f5tts_speed = goc
    print("\n  Người Việt nói chuyện thường 130-160 chữ/phút, đọc chậm rãi 110-130.")
    print("  Chậm quá thì kéo dài từng từ nghe máy móc, và TTFA tăng theo đúng tỉ lệ.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
