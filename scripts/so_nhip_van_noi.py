"""Thêm dấu chấm phẩy có thật sự tạo thêm nhịp nghỉ không?

Giả thiết: viết theo lối VĂN NÓI (câu ngắn, nhiều dấu phẩy, có "thì/là/à/rồi")
sẽ làm F5 nghỉ nhiều hơn và vụn hơn, nghe giống người nói chứ không giống đọc.

Nhưng đó mới là giả thiết. F5 có thể lờ dấu phẩy đi, hoặc nghỉ ở chỗ khác hẳn.
Script đọc HAI bản của cùng nội dung rồi đếm quãng nghỉ thật trong tiếng ra, để
biết viết lại có ăn thua không - trước khi tốn một cuộc gọi của người dùng.

    python scripts\\so_nhip_van_noi.py data\\kich_ban_nghe_thu.txt data\\kich_ban_van_noi.txt
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


def do_nghi(y: np.ndarray, sr: int, toi_thieu_ms: int = 60):
    """Trả danh sách độ dài (ms) các quãng lặng NẰM TRONG đoạn tiếng."""
    N = max(1, sr // 100)                       # khung 10ms
    r = np.array([np.sqrt((y[i:i + N] ** 2).mean()) for i in range(0, len(y) - N, N)])
    nguong = max(r.max() * 0.02, np.percentile(r, 10) * 3)
    im = r < nguong
    ra, i = [], 0
    while i < len(im):
        if not im[i]:
            i += 1
            continue
        j = i
        while j < len(im) and im[j]:
            j += 1
        # bỏ lặng ở hai đầu, chỉ đếm quãng nghỉ GIỮA lời
        if (j - i) * 10 >= toi_thieu_ms and i > 20 and j < len(im) - 20:
            ra.append((j - i) * 10)
        i = j
    return ra


async def main() -> int:
    import soundfile as sf

    from backend.services.tts_service import F5TTSService

    if len(sys.argv) < 3:
        print("  dùng: python scripts/so_nhip_van_noi.py <tệp A> <tệp B>")
        return 1

    tts = F5TTSService()
    print()
    for ten in sys.argv[1:3]:
        f = Path(ten)
        dong = [l.strip() for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        am_tiet = sum(len(l.split()) for l in dong)
        phay = sum(l.count(",") for l in dong)
        cham = sum(l.count(".") + l.count("?") + l.count("!") for l in dong)

        tong_giay, nghi = 0.0, []
        for l in dong:
            wav = await tts.synthesize(l, use_cache=False)
            y, sr = sf.read(io.BytesIO(wav), dtype="float32")
            tong_giay += len(y) / sr
            nghi += do_nghi(y, sr)

        print(f"  {f.name}")
        print(f"    {len(dong)} dòng | {am_tiet} âm tiết | {phay} phẩy, {cham} chấm/hỏi")
        print(f"    đọc hết {tong_giay:.1f}s -> {am_tiet/tong_giay*60:.0f} âm tiết/phút")
        if nghi:
            print(f"    {len(nghi)} quãng nghỉ trong lời | trung vị {int(np.median(nghi))}ms"
                  f" | tổng {sum(nghi)/1000:.1f}s ({sum(nghi)/10/tong_giay:.0f}% thời lượng)")
            print(f"    cứ {am_tiet/len(nghi):.1f} âm tiết lại nghỉ một lần")
        else:
            print("    KHÔNG có quãng nghỉ nào trong lời")
        print()

    print("  Văn nói giống người = nghỉ NHIỀU LẦN và NGẮN, rải đều.")
    print("  Nếu hai bản cho số quãng nghỉ ngang nhau thì F5 đang lờ dấu phẩy,")
    print("  và phải chèn quãng lặng bằng code chứ không sửa được bằng cách viết.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
