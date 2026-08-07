"""Đo xem vòng gửi khung 20ms trên Windows có bám đúng nhịp không.

Nếu asyncio.sleep trên Windows thô hơn 20ms thì mỗi khung trễ một chút, cộng
dồn ăn hết 60ms mồi (LEAD) -> AudioTrack trên điện thoại hụt dữ liệu -> rè.
Vòng gửi không bao giờ gửi nhanh hơn thời gian thực nên phần trễ KHÔNG bù lại được.
"""
import asyncio, time, statistics

FRAME_MS = 20
N = 150          # 3 giây tiếng


async def do_nhip(ten: str, ngu):
    moc = []
    next_at = time.perf_counter() + 0.06     # đúng LEAD trong _write_loop
    for _ in range(N):
        now = time.perf_counter()
        delay = next_at - now
        if delay > 0:
            await ngu(delay)
        moc.append(time.perf_counter())
        next_at += FRAME_MS / 1000.0

    khoang = [(moc[i] - moc[i - 1]) * 1000 for i in range(1, len(moc))]
    tre = [(moc[i] - (moc[0] + i * FRAME_MS / 1000)) * 1000 for i in range(len(moc))]
    print(f"\n{ten}")
    print(f"  khoảng giữa hai khung: trung vị {statistics.median(khoang):6.2f} ms"
          f" | max {max(khoang):6.2f} ms")
    print(f"  trễ dồn so với lịch  : cuối {tre[-1]:7.2f} ms | max {max(tre):7.2f} ms")
    qua = sum(1 for t in tre if t > 60)
    print(f"  số khung trễ quá 60ms (hết mồi): {qua}/{len(tre)}"
          + ("   <-- ĐÂY LÀ CHỖ HỤT TIẾNG" if qua else "   ok"))


async def main():
    print(f"Chính sách vòng lặp: {type(asyncio.get_running_loop()).__name__}")
    await do_nhip("asyncio.sleep (đang dùng trong _write_loop)", asyncio.sleep)

    # so sánh: ngủ ngắn rồi quay vòng bận - chính xác hơn nhưng tốn CPU
    async def ngu_chinh_xac(d):
        moc = time.perf_counter() + d
        if d > 0.004:
            await asyncio.sleep(d - 0.004)
        while time.perf_counter() < moc:
            await asyncio.sleep(0)

    await do_nhip("ngủ thô + quay vòng bận (đối chứng)", ngu_chinh_xac)


if __name__ == "__main__":
    asyncio.run(main())
