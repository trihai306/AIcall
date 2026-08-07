"""Ép xung GPU lên thì TTS nhanh thêm bao nhiêu? Suy ra bằng cách HẠ xung xuống.

Không cần overclock để trả lời. Khoá xung ở nhiều mức rồi đo độ trễ TTS: quan hệ
giữa xung và độ trễ cho biết tải này NHẠY tới đâu với xung.

    độ trễ tỉ lệ nghịch với xung  -> tải bị giới hạn bởi TÍNH TOÁN
                                     ép xung +10% sẽ được ~9%, OC đáng cân nhắc
    độ trễ gần như không đổi      -> tải bị giới hạn bởi CHỜ ĐỢI (phóng kernel,
                                     đồng bộ CPU-GPU). Ép xung vô ích.

Hạ xung là thao tác AN TOÀN và trả lại được (`--reset-gpu-clocks`). Script tự trả
về trạng thái cũ ở cuối, kể cả khi lỗi giữa chừng.

    python scripts/do_do_nhay_xung.py
    python scripts/do_do_nhay_xung.py --muc 900 1500 2100 2900
"""

import argparse
import asyncio
import statistics
import subprocess
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CAU = [
    "Dạ hiện bên em lãi suất từ bảy phẩy chín phần trăm một năm ạ",
    "Anh chị định vay khoảng bao nhiêu ạ",
    "Dạ chỉ cần căn cước và sao kê lương ba tháng gần nhất ạ",
    "Giải ngân trong vòng hai mươi bốn giờ sau khi phê duyệt ạ",
]

# Trạng thái cũ của dự án: start_services.ps1 khoá sàn 1500, trần để tối đa.
KHOA_CU = "1500,3090"


def smi(*args: str) -> tuple[int, str]:
    r = subprocess.run(["nvidia-smi", *args], capture_output=True, text=True,
                       timeout=30)
    return r.returncode, (r.stdout + r.stderr).strip()


def xung_hien_tai() -> float:
    _, out = smi("--query-gpu=clocks.sm", "--format=csv,noheader,nounits")
    try:
        return float(out.splitlines()[0])
    except Exception:
        return -1.0


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--muc", type=int, nargs="+", default=[900, 1500, 2100, 2900])
    ap.add_argument("--lap", type=int, default=6, help="số câu mỗi mức")
    a = ap.parse_args()

    from backend.config import settings
    from backend.services.tts_service import F5TTSService

    ma, out = smi("--query-gpu=clocks.max.sm", "--format=csv,noheader,nounits")
    if ma != 0:
        print(f"  không chạy được nvidia-smi: {out[:120]}")
        return 1
    tran = float(out.splitlines()[0])
    print(f"\n  trần xung của card: {tran:.0f} MHz | compile={settings.f5tts_compile}"
          f" | nfe={settings.f5tts_nfe_step}")

    tts = F5TTSService(); tts.load()

    async def do_mot_muc() -> float:
        for c in CAU[:2]:                       # nạp nóng ở mức xung này
            await tts.synthesize(c, use_cache=False)
        moc = []
        for i in range(a.lap):
            t0 = time.perf_counter()
            await tts.synthesize(CAU[i % len(CAU)], use_cache=False)
            moc.append((time.perf_counter() - t0) * 1000)
        return statistics.median(moc)

    ket: list[tuple[float, float, float]] = []
    try:
        print(f"\n  {'khoá xung':>11}{'xung thật':>12}{'TTS trung vị':>15}"
              f"{'so với mức cao nhất':>22}")
        print("  " + "-" * 64)
        for muc in sorted(a.muc):
            ma, out = smi(f"--lock-gpu-clocks={muc},{muc}")
            if ma != 0:
                print(f"  {muc:>9}    không khoá được: {out[:60]}")
                continue
            await asyncio.sleep(1.5)
            ms = await do_mot_muc()
            that = xung_hien_tai()
            ket.append((muc, that, ms))
            print(f"  {muc:>9}{that:>11.0f}{ms:>13.0f}ms", flush=True)
    finally:
        # TRẢ LẠI trạng thái cũ dù có lỗi gì: để máy kẹt ở 900MHz là làm hỏng mọi
        # cuộc gọi sau đó, mà không ai biết vì sao.
        smi("--reset-gpu-clocks")
        smi(f"--lock-gpu-clocks={KHOA_CU}")
        print(f"\n  đã trả xung về khoá cũ {KHOA_CU} (như start_services.ps1)")

    if len(ket) >= 2:
        (x0, _, t0), (x1, _, t1) = ket[0], ket[-1]
        # Nếu độ trễ tỉ lệ nghịch hoàn toàn với xung thì t0/t1 = x1/x0.
        ly_thuyet = x1 / x0
        that_te = t0 / t1
        do_nhay = (that_te - 1) / (ly_thuyet - 1) if ly_thuyet > 1 else 0
        print(f"\n  Xung {x0:.0f} -> {x1:.0f} MHz (gấp {ly_thuyet:.2f}x)")
        print(f"  Độ trễ {t0:.0f} -> {t1:.0f} ms (nhanh gấp {that_te:.2f}x)")
        print(f"  ĐỘ NHẠY VỚI XUNG: {do_nhay:.0%}")
        print()
        if do_nhay >= 0.7:
            print("  -> Tải bị giới hạn bởi TÍNH TOÁN. Overclock +10% xung sẽ được")
            print(f"     khoảng {10*do_nhay:.0f}% tốc độ. Đáng cân nhắc.")
        elif do_nhay >= 0.35:
            print("  -> Nửa nạc nửa mỡ. Overclock +10% chỉ được vài phần trăm,")
            print("     đổi lại rủi ro treo máy giữa cuộc gọi.")
        else:
            print("  -> Tải bị giới hạn bởi CHỜ ĐỢI, không phải tính toán.")
            print("     ÉP XUNG GẦN NHƯ VÔ ÍCH - hạ xung hơn ba lần mà độ trễ")
            print("     đổi rất ít, nên đẩy lên cũng đổi rất ít.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
