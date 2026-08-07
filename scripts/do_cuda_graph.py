"""CUDA graphs (`mode="reduce-overhead"`) có nhanh hơn compile mặc định không?

Đo GPU lúc chạy TTS cho thấy: xung 94% trần nhưng điện chỉ 46% giới hạn, không
có lý do hãm nào. Nghĩa là GPU RẢNH phần lớn thời gian, đang chờ giữa các kernel
nhỏ - F5 chạy 32 lượt transformer nối tiếp, mỗi lượt quá bé để lấp đầy GPU. Đó
là nghẽn ĐỘ TRỄ PHÓNG KERNEL, và CUDA graphs sinh ra đúng để chữa: gom cả chuỗi
thành một lần phóng.

NHƯNG CUDA graphs cần shape CỐ ĐỊNH, mà câu dài ngắn khác nhau. Rất có thể nó
phải bắt lại đồ thị mỗi lần đổi độ dài và thành CHẬM HƠN. Phải đo.

Mỗi chế độ chạy trong TIẾN TRÌNH RIÊNG: torch.compile không gỡ ra được, nạp hai
chế độ trong cùng một tiến trình là đo nhầm.

    python scripts/do_cuda_graph.py
"""

import multiprocessing as mp
import statistics
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Cố ý DÀI NGẮN KHÁC NHAU: đó là điều kiện thật của cuộc gọi, và cũng là chỗ
# CUDA graphs dễ gãy nhất.
CAU = [
    "Dạ vâng ạ",
    "Anh chị định vay khoảng bao nhiêu ạ",
    "Dạ hiện bên em lãi suất từ bảy phẩy chín phần trăm một năm ạ",
    "Dạ chỉ cần căn cước và sao kê lương ba tháng gần nhất ạ, anh chị đang làm ở đâu ạ",
    "Em nghe rõ ạ",
    "Giải ngân trong vòng hai mươi bốn giờ sau khi phê duyệt ạ",
]


def worker(che_do: str, hang_doi):
    import os
    import time
    sys.path.insert(0, str(PROJECT))
    os.environ["F5TTS_COMPILE"] = "true"
    os.environ["F5TTS_COMPILE_MODE"] = che_do
    import asyncio

    from backend.services.tts_service import F5TTSService

    try:
        t_nap = time.perf_counter()
        tts = F5TTSService(); tts.load()
        nap = time.perf_counter() - t_nap

        async def chay():
            moc = []
            for vong in range(2):          # vòng 1 còn biên dịch, vòng 2 mới là số thật
                lan = []
                for c in CAU:
                    t0 = time.perf_counter()
                    await tts.synthesize(c, use_cache=False)
                    lan.append((time.perf_counter() - t0) * 1000)
                moc.append(lan)
            return moc

        v1, v2 = asyncio.run(chay())
        hang_doi.put({"che_do": che_do, "nap_s": nap, "vong1": v1, "vong2": v2})
    except Exception as e:
        hang_doi.put({"che_do": che_do, "loi": f"{type(e).__name__}: {e}"})


def main() -> int:
    ctx = mp.get_context("spawn")
    print(f"\n  {len(CAU)} câu dài ngắn khác nhau, chạy 2 vòng mỗi chế độ\n")
    print(f"  {'chế độ':<20}{'nạp':>8}{'vòng 1':>12}{'vòng 2':>12}"
          f"{'câu ngắn':>11}{'câu dài':>11}")
    print("  " + "-" * 78)

    moc = {}
    for che_do in ("", "reduce-overhead"):
        q = ctx.Queue()
        p = ctx.Process(target=worker, args=(che_do, q))
        p.start()
        try:
            kq = q.get(timeout=900)
        except Exception:
            kq = {"che_do": che_do, "loi": "hết giờ chờ"}
        p.join(timeout=60)
        if p.is_alive():
            p.terminate()

        ten = che_do or "mặc định"
        if "loi" in kq:
            print(f"  {ten:<20}  LỖI: {kq['loi'][:56]}")
            continue
        v2 = kq["vong2"]
        moc[ten] = statistics.median(v2)
        print(f"  {ten:<20}{kq['nap_s']:>7.0f}s"
              f"{statistics.median(kq['vong1']):>10.0f}ms"
              f"{statistics.median(v2):>10.0f}ms"
              f"{min(v2):>9.0f}ms{max(v2):>9.0f}ms")

    if len(moc) == 2:
        a, b = moc.get("mặc định"), moc.get("reduce-overhead")
        print(f"\n  reduce-overhead nhanh gấp {a/b:.2f}x so với mặc định"
              if b else "")
        print("  Dưới 1.10x thì đừng đổi: CUDA graphs bắt lại đồ thị mỗi lần đổi")
        print("  độ dài câu, rủi ro cao mà lợi không đáng.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
