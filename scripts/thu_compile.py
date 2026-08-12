"""torch.compile có nhanh hơn không, và tiếng ra có KHÁC không?

Đây là hướng tăng tốc duy nhất KHÔNG đánh đổi chất lượng: cùng trọng số, cùng
phép toán, chỉ hợp nhất kernel. Nếu tiếng ra khác nhiều thì có gì đó sai.

Cũng đo mức dùng GPU trong lúc sinh tiếng: nếu GPU chưa chạy hết thì nút thắt
nằm ở chỗ khác chứ không phải sức tính.
"""
import asyncio
import io
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, "C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")

CAU = ("Dạ em chào anh chị ạ. Bên em đang có chương trình vay tín chấp "
       "lãi suất ưu đãi từ sáu phẩy năm phần trăm một năm.")


def doc(b):
    with wave.open(io.BytesIO(b)) as w:
        return (np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
                .astype(np.float32) / 32768), w.getframerate()


class DoGPU(threading.Thread):
    """Lấy mẫu mức dùng GPU trong lúc chạy."""
    def __init__(self):
        super().__init__(daemon=True)
        self.chay, self.mau = True, []

    def run(self):
        while self.chay:
            try:
                r = subprocess.run(
                    ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,power.draw",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=5)
                p = [x.strip() for x in r.stdout.strip().split(",")]
                self.mau.append((float(p[0]), float(p[1]), float(p[2])))
            except Exception:
                pass
            time.sleep(0.2)


async def chay_mot_lan(bat_compile: bool):
    from backend.config import settings
    from backend.services.tts_service import F5TTSService
    settings.f5tts_compile = bat_compile
    tts = F5TTSService()
    t_nap = time.perf_counter()
    tts.load()
    await tts.synthesize("khởi động một hai ba", use_cache=False)   # gồm cả biên dịch
    nap_ms = (time.perf_counter() - t_nap) * 1000

    do = DoGPU(); do.start()
    ms, tieng = [], None
    for i in range(4):
        t0 = time.perf_counter()
        w = await tts.synthesize(CAU, use_cache=False)
        ms.append((time.perf_counter() - t0) * 1000)
        if i == 0:
            tieng = w
    do.chay = False; do.join(timeout=2)
    u = np.array(do.mau) if do.mau else np.zeros((1, 3))
    return nap_ms, ms, tieng, u


async def main():
    print("  === KHÔNG compile (đang chạy) ===")
    nap0, ms0, w0, u0 = await chay_mot_lan(False)
    print(f"    nạp + làm nóng {nap0:>8.0f} ms")
    print(f"    sinh tiếng     {['%.0f' % m for m in ms0]}  -> TB {np.mean(ms0[1:]):.0f} ms")
    print(f"    GPU dùng       {u0[:,0].max():.0f}% đỉnh, {u0[:,0].mean():.0f}% TB")
    print(f"    VRAM           {u0[:,1].max():.0f} MB | điện {u0[:,2].max():.0f} W")

    print("\n  === CÓ compile ===")
    try:
        nap1, ms1, w1, u1 = await chay_mot_lan(True)
    except Exception as e:
        print(f"    [!] không bật được: {type(e).__name__}: {str(e)[:160]}")
        return
    print(f"    nạp + biên dịch{nap1:>8.0f} ms   (chỉ tốn một lần lúc khởi động)")
    print(f"    sinh tiếng     {['%.0f' % m for m in ms1]}  -> TB {np.mean(ms1[1:]):.0f} ms")
    print(f"    GPU dùng       {u1[:,0].max():.0f}% đỉnh, {u1[:,0].mean():.0f}% TB")
    print(f"    VRAM           {u1[:,1].max():.0f} MB | điện {u1[:,2].max():.0f} W")

    a, b = np.mean(ms0[1:]), np.mean(ms1[1:])
    print(f"\n  => nhanh hơn {a-b:.0f} ms ({(a-b)/a*100:.0f}%)"
          if b < a else f"\n  => CHẬM hơn {b-a:.0f} ms - không đáng bật")

    # tiếng ra có khác không
    x0, sr0 = doc(w0); x1, sr1 = doc(w1)
    n = min(len(x0), len(x1))
    print(f"\n  Tiếng ra: dài {len(x0)/sr0:.2f}s vs {len(x1)/sr1:.2f}s")
    if n > 1000:
        d = x0[:n] - x1[:n]
        print(f"    sai khác RMS {np.sqrt((d**2).mean()):.5f} "
              f"(mức tín hiệu {np.sqrt((x0[:n]**2).mean()):.5f})")
        print("    * F5 có lấy mẫu ngẫu nhiên nên hai lần chạy vốn đã khác nhau;")
        print("      con số này chỉ để bắt trường hợp compile làm HỎNG hẳn.")


asyncio.run(main())
