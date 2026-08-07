"""Đo chỗ đứt sóng gây tiếng 'gắt' (lách tách).

Tiếng nổ sinh ra khi biên độ nhảy bậc: mẫu cuối mảnh này khác xa mẫu đầu mảnh
kia thì loa phải dịch chuyển đột ngột -> nghe 'tách'. Đo bằng con số chứ không
nghe đoán.
"""
import asyncio, io, sys, wave
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
P = Path(r"C:\duan\chat-ai"); sys.path.insert(0, str(P))
import numpy as np

CAU = [
    "Dạ anh chị chuẩn bị chứng minh nhân dân",
    "và sao kê lương ba tháng gần nhất ạ.",
    "Anh chị cần thêm thông tin gì không ạ?",
]

def doc(b):
    with wave.open(io.BytesIO(b)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768

async def main():
    from backend.services.tts_service import F5TTSService
    tts = F5TTSService(); tts.load()

    manh = [doc(await tts.synthesize(c, use_cache=False)) for c in CAU]

    print("Biên độ ở hai đầu mỗi mảnh (thang -1..1):")
    print(f"{'mảnh':<6}{'mẫu đầu':>10}{'mẫu cuối':>11}{'đỉnh 5ms đầu':>15}{'đỉnh 5ms cuối':>15}")
    for i, a in enumerate(manh, 1):
        n5 = int(0.005 * 24000)
        print(f"{i:<6}{a[0]:>10.4f}{a[-1]:>11.4f}"
              f"{np.abs(a[:n5]).max():>15.4f}{np.abs(a[-n5:]).max():>15.4f}")

    print("\nBậc nhảy ở ranh giới khi ghép liên tiếp:")
    for i in range(len(manh) - 1):
        buoc = abs(manh[i+1][0] - manh[i][-1])
        # Bậc trong lòng tín hiệu để so sánh: chênh lệch mẫu-kề-mẫu lớn nhất
        binh_thuong = float(np.abs(np.diff(manh[i])).max())
        print(f"  mảnh {i+1} -> {i+2}: bậc {buoc:.4f}"
              f" | bậc lớn nhất trong lòng mảnh {i+1}: {binh_thuong:.4f}"
              f" {'  <-- NHẢY BẤT THƯỜNG' if buoc > binh_thuong else ''}")

    print("\nNếu cắt ngang giữa chừng (mô phỏng barge-in - dừng ngay lập tức):")
    a = manh[0]
    for vi_tri in (0.3, 0.5, 0.7):
        k = int(len(a) * vi_tri)
        print(f"  cắt ở {vi_tri*100:.0f}%: biên độ tại điểm cắt {a[k]:+.4f}"
              f"  -> nhảy về 0 là bậc {abs(a[k]):.4f}")

asyncio.run(main())
