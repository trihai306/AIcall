"""Bật VAD và beam 5 thì STT chậm thêm bao nhiêu?

STT nằm trên đường găng của độ trễ hội thoại, nên mọi thứ thêm vào đây đều phải
trả giá. Đo trên chính các câu thật (FPT FOSD) chứ không phải câu tự dựng.

Bỏ lần chạy đầu: lần đầu còn tốn nạp nhân CUDA và cấp phát bộ nhớ, tính vào là
số cao giả tạo.

    python scripts/do_tre_stt.py
"""

import argparse
import asyncio
import statistics
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(Path(__file__).resolve().parent))


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--so-cau", type=int, default=8)
    a = ap.parse_args()

    from do_loc_nhieu import tai_mau, wav_bytes
    from backend.services.stt_service import STTService
    import httpx

    stt = STTService()
    if not await stt.health_check():
        print("Máy chủ STT chưa chạy")
        return 1

    mau = tai_mau(a.so_cau)
    print(f"Đo trên {len(mau)} câu, dài "
          f"{min(x.size for x, _ in mau)/16000:.1f}-"
          f"{max(x.size for x, _ in mau)/16000:.1f}s\n")

    async with httpx.AsyncClient(timeout=60) as cli:
        # Hâm nóng: lần đầu tốn nạp nhân CUDA, tính vào là số cao giả tạo.
        await cli.post(f"{stt.base_url}/inference",
                       files={"file": ("a.wav", wav_bytes(mau[0][0], 16000), "audio/wav")},
                       data={"language": "vi", "response_format": "json"})

        do = []
        for x, _ in mau:
            w = wav_bytes(x, 16000)
            t0 = time.perf_counter()
            await cli.post(f"{stt.base_url}/inference",
                           files={"file": ("a.wav", w, "audio/wav")},
                           data={"language": "vi", "response_format": "verbose_json",
                                 "temperature": "0"})
            do.append((time.perf_counter() - t0) * 1000)
            print(f"    {x.size/16000:>5.1f}s tiếng ->{do[-1]:>7.0f} ms")

    print(f"\n    trung vị {statistics.median(do):.0f} ms"
          f"   trung bình {statistics.mean(do):.0f} ms"
          f"   cao nhất {max(do):.0f} ms")
    await stt.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
