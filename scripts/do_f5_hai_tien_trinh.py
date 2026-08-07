"""Chạy F5-TTS ở HAI TIẾN TRÌNH có đỡ bị cộng dồn không?

Bối cảnh: TTS là chỗ nghẽn khi nhiều cuộc gọi cùng lúc - mọi mảnh tiếng xếp một
hàng vì `ThreadPoolExecutor(max_workers=1)`. Nới lên 2 LUỒNG thì vỡ ngay
(F5-TTS không an toàn đa luồng, hai suy luận giẫm lên tensor điều kiện chung).
Còn lại một đường: mỗi bản model một TIẾN TRÌNH riêng.

NHƯNG ĐỪNG CHO LÀ NÓ SẼ NHANH GẤP ĐÔI. Hai tiến trình vẫn dùng CHUNG MỘT GPU;
GPU chạy kernel của các tiến trình bằng cách chia thời gian, nên rất có thể mỗi
bên chậm đi đúng bằng phần được lợi. Phải đo mới biết.

Cách đo, chỉ đổi MỘT biến:
    A. một tiến trình sinh 2N câu
    B. hai tiến trình, mỗi bên N câu, bắt đầu CÙNG LÚC
So tổng thời gian tường. B nhanh hơn A đáng kể thì tách tiến trình mới đáng làm.

    python scripts/do_f5_hai_tien_trinh.py
    python scripts/do_f5_hai_tien_trinh.py --cau 6
"""

import argparse
import multiprocessing as mp
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CAU = [
    "Dạ hiện bên em lãi suất từ bảy phẩy chín phần trăm một năm ạ",
    "Anh chị định vay khoảng bao nhiêu ạ",
    "Dạ chỉ cần căn cước và sao kê lương ba tháng gần nhất ạ",
    "Giải ngân trong vòng hai mươi bốn giờ sau khi phê duyệt ạ",
    "Dạ em xin phép gửi thông tin qua tin nhắn ạ",
    "Hạn mức tối đa của bên em là năm trăm triệu đồng ạ",
]


def worker(so_cau: int, hang_doi, san_sang, chay):
    """Một tiến trình: nạp model, báo sẵn sàng, chờ hiệu lệnh, rồi sinh `so_cau`."""
    sys.path.insert(0, str(PROJECT))
    import asyncio

    from backend.services.tts_service import F5TTSService

    tts = F5TTSService()
    tts.load()                       # gồm cả warmup (và biên dịch nếu bật)

    vram = 0
    try:
        import torch
        vram = torch.cuda.memory_allocated() // 1024 ** 2
    except Exception:
        pass

    san_sang.put(vram)
    chay.wait()                      # tất cả cùng xuất phát

    async def chay_het():
        moc = []
        for i in range(so_cau):
            t0 = time.perf_counter()
            await tts.synthesize(CAU[i % len(CAU)], use_cache=False)
            moc.append((time.perf_counter() - t0) * 1000)
        return moc

    hang_doi.put(asyncio.run(chay_het()))


def chay_muc(n_tien_trinh: int, tong_cau: int) -> tuple[float, list, list]:
    """Trả (giây tường, danh sách ms từng câu, VRAM mỗi tiến trình)."""
    ctx = mp.get_context("spawn")
    hang_doi, san_sang = ctx.Queue(), ctx.Queue()
    chay = ctx.Event()
    moi_ben = tong_cau // n_tien_trinh

    ps = [ctx.Process(target=worker, args=(moi_ben, hang_doi, san_sang, chay))
          for _ in range(n_tien_trinh)]
    for p in ps:
        p.start()

    vram = [san_sang.get() for _ in ps]       # chờ tất cả nạp xong
    t0 = time.perf_counter()
    chay.set()
    ms = []
    for _ in ps:
        ms += hang_doi.get()
    giay = time.perf_counter() - t0
    for p in ps:
        p.join(timeout=30)
    return giay, ms, vram


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cau", type=int, default=6, help="tổng số câu mỗi mức")
    a = ap.parse_args()

    import statistics

    sys.path.insert(0, str(PROJECT))
    from backend.config import settings

    print(f"\n  compile={settings.f5tts_compile} | nfe={settings.f5tts_nfe_step}"
          f" | tổng {a.cau} câu mỗi mức")
    print("  (mỗi tiến trình phải nạp model riêng, lần đầu lâu vì còn biên dịch)\n")
    print(f"  {'tiến trình':>12}{'tổng thời gian':>17}{'ms/câu trung vị':>18}"
          f"{'VRAM mỗi bên':>15}  nhanh gấp")
    print("  " + "-" * 82)

    moc_mot = None
    for n in (1, 2):
        giay, ms, vram = chay_muc(n, a.cau)
        moc_mot = moc_mot or giay
        print(f"  {n:>12}{giay:>15.1f}s{statistics.median(ms):>16.0f}ms"
              f"{f'{statistics.median(vram)}MB':>15}  {moc_mot/giay:>8.2f}x")

    print("\n  Nhanh gấp ~2x  -> GPU chạy song song thật, tách tiến trình ĐÁNG làm.")
    print("  Nhanh gấp ~1x  -> GPU chỉ chia thời gian, tách ra KHÔNG được gì mà")
    print("                    còn tốn thêm VRAM và một lần biên dịch nữa.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
