"""So các cách cắt mảnh để tạo tiếng, trên cùng một đoạn văn.

VÌ SAO CÓ SCRIPT NÀY

Người dùng nghe thấy ở chỗ nối hai mảnh: "có 1 điểm chậm và vẫn có dấu chấm".
Đó không phải ảo giác - F5 sinh MỖI MẢNH như một câu trọn vẹn, nên cuối mảnh nó
hạ giọng kết câu rồi kéo dài âm cuối, đúng lúc câu chưa hết. Đo trên bản ghi
cuộc gọi thật: âm tiết cuối mảnh dài trung vị 1,05 lần âm thường, mảnh tệ nhất
3,00 lần.

Đánh đổi nằm ở đây, và không có cách nào thoát:

    mảnh NHỎ  -> tiếng đầu ra sớm (TTFA thấp) nhưng nhiều chỗ nối, nhiều chỗ
                 hạ giọng giả
    mảnh TO   -> ngữ điệu liền mạch nhưng khách chờ lâu hơn mới nghe thấy tiếng

CÁCH THỨ BA - "tăng dần" - ăn được cả hai đầu, và đó là thứ script này muốn
chứng minh: CHỈ MẢNH ĐẦU cần nhỏ. Khi mảnh đầu đã phát rồi thì máy còn cả giây
tiếng trong tay, mà TTS sinh nhanh gấp 3,5 lần thời gian phát - nên mảnh sau tha
hồ to. Mảnh to hơn thì ít chỗ nối hơn, tức ít "điểm chậm" hơn.

CÁCH ĐO

    TTFA        bao lâu thì có mảnh ĐẦU TIÊN - đây là cái khách cảm nhận
    chỗ nối     mỗi chỗ nối là một chỗ có thể nghe ra "điểm chậm"
    âm cuối     âm tiết cuối mảnh dài gấp mấy lần âm tiết thường. Càng gần 1
                càng tự nhiên; to là đang hạ giọng kết câu giữa chừng
    tổng sinh   thời gian GPU, chỉ để biết cái giá

Bản "cả câu một lần" là CHUẨN VÀNG về ngữ điệu - không dùng thật được vì TTFA
bằng cả đoạn, nhưng để biết trần chất lượng ở đâu.

CHẠY TRÊN MÁY WIN:
    .venv\\python.exe scripts\\so_cach_tao_voice.py
    .venv\\python.exe scripts\\so_cach_tao_voice.py --tep doan.txt --ra C:\\tmp\\socach
"""
import argparse
import asyncio
import io
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np              # noqa: E402
import soundfile as sf          # noqa: E402

from backend.pipeline.text_chunker import tach_manh            # noqa: E402
from backend.services.tts_service import F5TTSService          # noqa: E402

DOAN = (
    "Dạ anh muốn vay tín chấp thì lãi suất sẽ là từ 7.9%/năm nha anh. "
    "Hạn mức tối đa là năm trăm triệu đồng, còn giấy tờ thì anh chuẩn bị "
    "chứng minh nhân dân, sổ hộ khẩu và sao kê lương ba tháng gần nhất. "
    "Thời gian giải ngân trong vòng 24 giờ sau khi hồ sơ được phê duyệt, "
    "anh yên tâm nhé."
)

# Cách cắt: tên -> hàm trả về cỡ mảnh cho mảnh thứ i (0 là mảnh đầu).
# None nghĩa là "lấy hết phần còn lại".
CACH = {
    "1_deu_5":     lambda i: 5,
    "2_deu_16":    lambda i: 16,
    "3_tang_dan":  lambda i: (5, 10, 20)[i] if i < 3 else None,
    "4_ca_cau":    lambda i: None,
}


def cat(van: str, co_manh) -> list[str]:
    """Cắt y hệt vòng stream của pipeline, nhưng cỡ mảnh thay đổi theo thứ tự."""
    ra, dem = [], ""
    for tu in van.split():
        dem = f"{dem} {tu}" if dem else tu
        while True:
            n = co_manh(len(ra))
            if n is None:              # lấy hết phần còn lại -> đợi tới cuối
                break
            m, dem = tach_manh(dem, n=n)
            if m is None:
                break
            ra.append(m)
    if dem.strip():
        ra.append(dem.strip())
    return ra


def am_tiet(y: np.ndarray, sr: int):
    """(dài âm tiết cuối, trung vị âm tiết giữa) tính bằng ms, hoặc None.

    Tìm đỉnh năng lượng làm nhân âm tiết, ranh giới là đáy giữa hai đỉnh.
    """
    h = max(1, int(sr * 0.01))
    k = len(y) // h
    if k < 25:
        return None
    e = np.array([float(np.sqrt((y[i * h:(i + 1) * h] ** 2).mean())) for i in range(k)])
    e = np.convolve(e, np.ones(5) / 5, mode="same")
    dinh = [i for i in range(3, k - 3)
            if e[i] == max(e[max(0, i - 7):i + 8]) and e[i] > e.max() * 0.20]
    if len(dinh) < 4:
        return None
    ranh = [0] + [int(np.argmin(e[a:b]) + a) for a, b in zip(dinh, dinh[1:])] + [k]
    d = np.diff(ranh) * 10.0
    return float(d[-1]), float(np.median(d[:-1]))


async def chay(svc, ten: str, manh: list[str]) -> dict:
    """Sinh từng mảnh, đo mốc, nối lại."""
    khuc, ttfa, t0 = [], None, time.perf_counter()
    for m in manh:
        b = await svc.synthesize(m, voice=ten, use_cache=False)
        if ttfa is None:
            ttfa = (time.perf_counter() - t0) * 1000
        x, sr = sf.read(io.BytesIO(b), dtype="float32")
        khuc.append(x.mean(axis=1) if x.ndim > 1 else x)
    tong = (time.perf_counter() - t0) * 1000
    ty = [am_tiet(x, sr) for x in khuc]
    ty = [c / g for c, g in (t for t in ty if t) if g > 0]
    return {
        "manh": len(manh), "ttfa": ttfa, "tong": tong,
        "tieng": np.concatenate(khuc), "sr": sr,
        "am_cuoi": float(np.median(ty)) if ty else float("nan"),
        "cuoi_to_nhat": float(max(ty)) if ty else float("nan"),
    }


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tep", help="tệp chứa đoạn văn, mặc định dùng đoạn mẫu")
    ap.add_argument("--ra", default="C:/tmp/socach")
    ap.add_argument("--lap", type=int, default=1, help="lặp mấy lần rồi lấy trung vị")
    a = ap.parse_args()

    van = Path(a.tep).read_text(encoding="utf-8").strip() if a.tep else DOAN
    ra = Path(a.ra)
    ra.mkdir(parents=True, exist_ok=True)

    svc = F5TTSService()
    svc.load()
    ten = svc.default_voice_name()
    await svc.ensure_voice(ten)
    await svc.synthesize("hâm nóng máy", voice=ten, use_cache=False)   # bỏ lượt nguội

    print(f"\n  đoạn {len(van.split())} từ, giọng {ten}\n")
    print(f"  {'cách':<14} {'mảnh':>5} {'chỗ nối':>8} {'TTFA':>8} {'tổng sinh':>10} "
          f"{'âm cuối':>8} {'to nhất':>8}")
    print("  " + "-" * 70)
    for ten_cach, co in CACH.items():
        manh = cat(van, co)
        ket = None
        for _ in range(a.lap):
            ket = await chay(svc, ten, manh)
        y = ket["tieng"]
        sf.write(ra / f"{ten_cach}.wav", y / max(1.0, float(np.abs(y).max())), ket["sr"])
        print(f"  {ten_cach:<14} {ket['manh']:>5} {ket['manh']-1:>8} "
              f"{ket['ttfa']:>7.0f}ms {ket['tong']:>9.0f}ms "
              f"{ket['am_cuoi']:>7.2f}x {ket['cuoi_to_nhat']:>7.2f}x")
    print("  " + "-" * 70)
    print("\n  'âm cuối' = âm tiết cuối mảnh dài gấp mấy lần âm tiết thường.")
    print("  Càng gần 1 càng tự nhiên; to là đang hạ giọng kết câu giữa chừng.")
    print(f"\n  {ra}")


if __name__ == "__main__":
    asyncio.run(main())
