"""GPU có đang bị hãm không - đo xung, điện, nhiệt NGAY LÚC TTS đang chạy.

Đừng áp mẹo tăng tốc rồi mới xem có ăn thua. Trước hết phải biết GPU đang chạy ở
đâu so với trần của nó: nếu lúc suy luận nó đã bám sát xung tối đa và không báo
lý do hãm nào, thì mọi cách "ép GPU" đều vô nghĩa và chỗ nghẽn nằm chỗ khác.

Script lấy mẫu `nvidia-smi` liên tục trong lúc chạy một loạt câu TTS, rồi in:
  - xung SM lúc rảnh so với lúc chạy, và so với trần
  - điện tiêu thụ so với giới hạn (chạm trần điện = bị hãm vì điện)
  - nhiệt độ (chạm ngưỡng = bị hãm vì nóng)
  - `clocks_throttle_reasons` - máy tự khai vì sao nó hạ xung

    python scripts/soi_gpu_khi_chay.py
"""

import asyncio
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TRUONG = ("clocks.sm,clocks.max.sm,power.draw,power.limit,temperature.gpu,"
          "utilization.gpu,clocks_throttle_reasons.active")
CAU = [
    "Dạ hiện bên em lãi suất từ bảy phẩy chín phần trăm một năm ạ",
    "Anh chị định vay khoảng bao nhiêu ạ",
    "Dạ chỉ cần căn cước và sao kê lương ba tháng gần nhất ạ",
    "Giải ngân trong vòng hai mươi bốn giờ sau khi phê duyệt ạ",
]


def lay_mau() -> list[str] | None:
    r = subprocess.run(
        ["nvidia-smi", f"--query-gpu={TRUONG}", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=10)
    if r.returncode != 0:
        return None
    return [c.strip() for c in r.stdout.strip().splitlines()[0].split(",")]


def gom(dung: threading.Event, kho: list):
    while not dung.is_set():
        m = lay_mau()
        if m:
            kho.append(m)
        time.sleep(0.15)


def tom_tat(ten: str, kho: list):
    if not kho:
        print(f"  {ten}: không lấy được mẫu")
        return
    sm = [float(m[0]) for m in kho]
    tran = float(kho[0][1])
    dien = [float(m[2]) for m in kho]
    gh = float(kho[0][3])
    nhiet = [float(m[4]) for m in kho]
    util = [float(m[5]) for m in kho]
    print(f"  {ten}")
    print(f"    xung SM  : trung vị {statistics.median(sm):>6.0f} / cao nhất "
          f"{max(sm):>6.0f} / trần {tran:.0f} MHz"
          f"   ({100*statistics.median(sm)/tran:.0f}% trần)")
    print(f"    điện     : trung vị {statistics.median(dien):>6.1f} / giới hạn "
          f"{gh:.0f} W   ({100*statistics.median(dien)/gh:.0f}% giới hạn)")
    print(f"    nhiệt    : {statistics.median(nhiet):.0f}°C"
          f"   |  util báo: {statistics.median(util):.0f}%")
    ly_do = {m[6] for m in kho if m[6] and m[6] not in ("Not Active", "N/A", "0x0000000000000000")}
    print(f"    máy khai bị hãm vì: {', '.join(sorted(ly_do)) if ly_do else 'KHÔNG'}")


async def main() -> int:
    from backend.config import settings
    from backend.services.tts_service import F5TTSService

    if lay_mau() is None:
        print("  không chạy được nvidia-smi")
        return 1

    print(f"\n  compile={settings.f5tts_compile} | nfe={settings.f5tts_nfe_step}")

    kho_ranh: list = []
    dung = threading.Event()
    t = threading.Thread(target=gom, args=(dung, kho_ranh), daemon=True)
    t.start()
    time.sleep(3.0)                       # đo lúc rảnh
    dung.set(); t.join()

    tts = F5TTSService(); tts.load()

    kho_chay: list = []
    dung2 = threading.Event()
    t2 = threading.Thread(target=gom, args=(dung2, kho_chay), daemon=True)
    t2.start()
    moc = []
    for i in range(8):
        t0 = time.perf_counter()
        await tts.synthesize(CAU[i % len(CAU)], use_cache=False)
        moc.append((time.perf_counter() - t0) * 1000)
    dung2.set(); t2.join()

    print()
    tom_tat("LÚC RẢNH", kho_ranh)
    print()
    tom_tat("LÚC CHẠY TTS", kho_chay)
    print(f"\n  TTS: trung vị {statistics.median(moc):.0f}ms / {len(moc)} câu")
    print("\n  Đọc kết quả:")
    print("   - xung lúc chạy đã sát trần và không khai lý do hãm -> GPU KHÔNG bị")
    print("     hãm, ép thêm vô ích, chỗ nghẽn nằm ở phần mềm.")
    print("   - chạm giới hạn điện hoặc nhiệt -> nới giới hạn điện mới có tác dụng.")
    print("   - xung thấp mà điện/nhiệt đều thấp -> tải quá vụn, GPU không kịp")
    print("     leo xung; chữa bằng khoá xung sàn chứ không phải nới điện.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
