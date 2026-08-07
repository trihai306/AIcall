"""Đo GIÁ PHẢI TRẢ khi nới ngưỡng mảnh đầu: mảnh đầu dài thêm thì khách chờ thêm bao lâu.

Thời gian khách chờ tiếng đầu (TTFA) = LLM sinh xong N từ + TTS sinh mảnh đó.
Phần LLM tính được từ tốc độ token; phần TTS phải đo thật vì nó không tuyến tính.

Chạy xen kẽ các mức và bỏ lượt khởi động - đo nguội nhóm đầu sai tới 50% vì GPU
chưa lên xung.

    python scripts/do_gia_manh_dau.py
"""
import asyncio, pathlib, statistics, sys, time

GOC = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))

# Mảnh đầu thực tế trong hội thoại tổng đài, cắt sẵn ở các độ dài cần so.
MAU = {
    6:  ["Dạ, lãi suất vay tín chấp",
         "Dạ em chào anh, em gọi",
         "Anh vay 500 triệu thì trả",
         "Dạ khoản vay này không cần"],
    9:  ["Dạ, lãi suất vay tín chấp bên em hiện",
         "Dạ em chào anh, em gọi từ ngân hàng",
         "Anh vay 500 triệu thì trả góp 36 tháng",
         "Dạ khoản vay này không cần tài sản đảm"],
    12: ["Dạ, lãi suất vay tín chấp bên em hiện tại là sáu",
         "Dạ em chào anh, em gọi từ ngân hàng để tư vấn",
         "Anh vay 500 triệu thì trả góp 36 tháng anh nhé, lãi",
         "Dạ khoản vay này không cần tài sản đảm bảo, anh yên"],
}
LUOT = 4          # lượt đo mỗi câu, chưa kể lượt khởi động


async def main():
    from backend.services.tts_service import F5TTSService
    tts = F5TTSService(); tts.load()

    async def do(t):
        t0 = time.perf_counter()
        await tts.synthesize(t, use_cache=False, fast=True)   # fast=True: đúng mảnh đầu
        return (time.perf_counter() - t0) * 1000

    print("khởi động ...")
    for _ in range(2):
        await do(MAU[9][0])

    ket = {k: [] for k in MAU}
    # xen kẽ các mức trong từng lượt, không đo hết mức này rồi mới sang mức kia
    for lan in range(LUOT):
        for k in MAU:
            for cau in MAU[k]:
                ket[k].append(await do(cau))
        print(f"  xong lượt {lan + 1}/{LUOT}")

    print(f"\n{'số từ':>6} {'TTS trung vị':>14} {'so với 6 từ':>14}   (n={len(ket[6])} mẫu/mức)")
    goc = statistics.median(ket[6])
    for k in sorted(ket):
        m = statistics.median(ket[k])
        print(f"{k:>6} {m:>11.0f} ms {m - goc:>+11.0f} ms")

    print("\nPhần LLM: ở 142 token/s, mỗi từ tiếng Việt ~1.4 token")
    for k in sorted(ket):
        print(f"  {k:>2} từ -> LLM cần ~{k * 1.4 / 142 * 1000:.0f} ms")

    print("\nTỔNG chênh so với mức 6 từ (TTS + LLM):")
    for k in sorted(ket):
        if k == 6:
            continue
        d = (statistics.median(ket[k]) - goc) + (k - 6) * 1.4 / 142 * 1000
        print(f"  {k:>2} từ: {d:+.0f} ms")


if __name__ == "__main__":
    asyncio.run(main())
