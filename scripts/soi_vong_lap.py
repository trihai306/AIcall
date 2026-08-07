"""Nghe lại đúng thứ đi lên modem - không cần cuộc gọi.

Mẹo: đường lên là `AIF1TX1`, mà nguồn thu MIC cũng đọc chính `AIF1TX1`. Nên khi
bật đường tiêm (`ABOX UAIF0 SPK = SIFS1` + `AIF1TX1 Input 2 = AIF1RX1`), thu
bằng nguồn 1 là thu về ĐÚNG dòng tiếng sẽ gửi cho đầu bên kia, chỉ thiếu mỗi
khâu mã hoá AMR của mạng.

Nhờ vậy chấm được chất lượng mà không tốn cuộc gọi nào, và lặp nhanh:

  - đếm chỗ đứt tiếng (khoảng lặng bất thường giữa lúc đang phát)
  - so mức và độ méo với bản gốc
  - lưu cả hai bản WAV để nghe bằng tai

Chú ý: micro thật vẫn nằm ở `Input 1` nên tiếng phòng cũng lọt vào. Phát đủ to
thì phần của ta áp đảo; kết luận dựa trên chỗ đứt tiếng chứ không dựa trên nền.

    python scripts/soi_vong_lap.py
    python scripts/soi_vong_lap.py --tone     # dùng tiếng bíp thay vì giọng
"""

import argparse
import asyncio
import math
import os
import struct
import subprocess
import sys
import wave
from io import BytesIO
from pathlib import Path

# Tần số chiều lên phải đặt TRƯỚC khi nạp backend: các hằng số khung được tính
# ngay lúc nạp module, đổi settings sau đó là không có tác dụng.
os.environ.setdefault("PHONE_RATE_LEN", "24000")

import numpy as np  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
SERIAL = "21f10e44220c7ece"
MIXCTL = "/data/local/tmp/mixctl"
RA = PROJECT / "data" / "vong_lap"
CAU = ("Dạ em chào anh chị ạ. Em là nhân viên tư vấn của ngân hàng. "
       "Anh chị có cần em hỗ trợ thông tin gì không ạ?")


def sh(cmd: str, t: int = 90) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def mix_set(ten: str, gt: str) -> None:
    sh(f"""su -c '{MIXCTL} set "{ten}" {gt}'""")


def tone(giay: float, rate: int = 24000) -> bytes:
    n = int(giay * rate)
    mau = b"".join(struct.pack("<h", int(11000 * math.sin(2 * math.pi * 440 * i / rate)))
                   for i in range(n))
    buf = BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(mau)
    return buf.getvalue()


def luu(ten: str, x: np.ndarray, rate: int) -> Path:
    RA.mkdir(parents=True, exist_ok=True)
    p = RA / ten
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    return p


def cham_dut_tieng(x: np.ndarray, rate: int) -> tuple[int, float]:
    """Đếm chỗ đứt tiếng: khoảng gần im nằm GIỮA phần đang có tiếng.

    Đứt tiếng do đói dữ liệu nghe thành rè. Chỉ tính khoảng ngắn (dưới 60ms) và
    nằm giữa hai đoạn có tiếng - khoảng lặng đầu/cuối hay giữa hai câu là bình
    thường, đếm vào thì lúc nào cũng báo hỏng.
    """
    n = int(0.005 * rate)                       # cửa sổ 5ms
    if x.size < n * 4:
        return 0, 0.0
    khung = x[:x.size // n * n].reshape(-1, n)
    muc = np.sqrt((khung ** 2).mean(axis=1))
    nguong = muc.max() * 0.06
    co_tieng = muc > nguong
    if not co_tieng.any():
        return 0, 0.0

    dau, cuoi = int(np.argmax(co_tieng)), int(len(co_tieng) - np.argmax(co_tieng[::-1]))
    trong = co_tieng[dau:cuoi]
    dut, dai, tong = 0, 0, 0
    for c in trong:
        if not c:
            dai += 1
        else:
            if 0 < dai <= int(0.06 / 0.005):
                dut += 1
                tong += dai
            dai = 0
    return dut, tong * 5.0 / 1000.0


async def chay(a) -> int:
    from backend.config import settings
    from backend.pipeline.session_manager import CallSession
    from backend.services import phone_call_service as pcs
    from backend.services import adb_service
    from backend.services.phone_call_service import PhoneCallBridge

    rate_len = settings.phone_rate_len
    print(f"[1] Dựng tiếng mẫu (chiều lên thu ở {rate_len}Hz) ...")
    if a.tone:
        wav, ten = tone(5.0), "tone"
    else:
        from backend.services.tts_service import F5TTSService
        tts = F5TTSService()
        tts.load()
        wav, ten = await tts.synthesize(CAU, use_cache=False), "giong"
    goc, sr_goc = pcs._wav_to_pcm(wav)
    p_goc = luu(f"{ten}_goc.wav", goc, sr_goc)

    ok, msg = await adb_service.start_bridge(SERIAL, port=8123, src=1)
    print(f"[2] {msg}")
    if not ok:
        return 1
    bridge = PhoneCallBridge(None, CallSession(customer_name="K"), port=8123)
    bridge.tam_dung_nghe = True
    thu: list[bytes] = []
    bridge.theo_doi_khung = thu.append
    await bridge.start()

    try:
        print("[3] Bật đường tiêm (giống hệt lúc gọi thật) ...")
        ok_inj, msg_inj = await adb_service.set_uplink_injection(SERIAL, True)
        print(f"    {msg_inj}")
        if not ok_inj:
            return 1
        await asyncio.sleep(0.5)

        print("[4] Phát và thu lại ...")
        thu.clear()
        await bridge.play(wav)
        giay = len(goc) / sr_goc
        await asyncio.sleep(giay + 2.0)

        x = np.frombuffer(b"".join(thu), dtype=np.int16).astype(np.float32) / 32768.0
        p_thu = luu(f"{ten}_qua_duong_len.wav", x, rate_len)

        dut, mat_giay = cham_dut_tieng(x, rate_len)
        rms = float(np.sqrt((x ** 2).mean())) * 32768.0
        dinh = float(np.abs(x).max())

        print(f"\n[5] Kết quả  ({giay:.1f}s phát, {x.size / rate_len:.1f}s thu)")
        print(f"    chỗ đứt tiếng   : {dut}  (tổng {mat_giay * 1000:.0f}ms mất)")
        print(f"    mức RMS thu về  : {rms:.0f}")
        print(f"    đỉnh            : {dinh:.3f}  {'ĐÃ VỠ' if dinh >= 0.999 else ''}")
        print(f"\n    gốc: {p_goc}")
        print(f"    thu: {p_thu}")

        print("\n" + "=" * 58)
        if dut > 5:
            print(f"ĐỨT TIẾNG THẬT: {dut} chỗ. Đó là tiếng dè.")
            print("Nút thắt ở nhịp gửi hoặc đệm AudioTrack của app.")
        elif dinh >= 0.999:
            print("VỠ ĐỈNH: tiếng quá to trước khi vào bộ trộn. Hạ mức.")
        else:
            print("Đường tiêm sạch trên máy. Nếu vẫn nghe dè thì phần méo do")
            print("bộ mã AMR của mạng, không phải do đường tiếng trong máy.")
        print("=" * 58)
    finally:
        await adb_service.set_uplink_injection(SERIAL, False)
        await bridge.stop()
        await adb_service.stop_bridge(SERIAL, port=8123)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tone", action="store_true")
    return asyncio.run(chay(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
