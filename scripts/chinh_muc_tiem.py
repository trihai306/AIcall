"""Tìm mức phát lớn nhất mà đường tiêm không vỡ tiếng.

Đo được đường tiêm KHUẾCH ĐẠI: phát tiếng bíp đỉnh 0.336, thu lại đỉnh 0.970 -
gấp 2.9 lần, tức +9.2 dB. Tiếng TTS sau khi chuẩn mức có đỉnh tới 0.89, nhân
2.9 thành 2.6 nên bị cắt phẳng đầu sóng. Đó là tiếng "dè" người nghe báo.

Script phát cùng một câu ở nhiều mức đỉnh, thu lại qua đúng đường lên rồi chấm.
Chọn mức CAO NHẤT mà thu về vẫn dưới trần - thấp quá thì tỉ số tín/nhiễu kém và
bộ mã AMR lại có ít bit để tả giọng.

Không cần cuộc gọi: thu bằng nguồn MIC chính là đọc `AIF1TX1`, tức đường lên.

    python scripts/chinh_muc_tiem.py
"""

import argparse
import asyncio
import os
import re
import subprocess
import sys
import wave
from io import BytesIO
from pathlib import Path

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
CAU = ("Dạ em chào anh chị ạ. Em là nhân viên tư vấn của ngân hàng. "
       "Anh chị có cần em hỗ trợ thông tin gì không ạ?")


def sh(cmd: str, t: int = 90) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def wav_bytes(x: np.ndarray, rate: int) -> bytes:
    buf = BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


async def chay(a) -> int:
    from backend.config import settings
    from backend.pipeline.session_manager import CallSession
    from backend.services import adb_service
    from backend.services import phone_call_service as pcs
    from backend.services.phone_call_service import PhoneCallBridge
    from backend.services.tts_service import F5TTSService

    rate_len = settings.phone_rate_len

    print("[0] Control âm lượng của đường tiêm:")
    info = sh(f"""su -c '{MIXCTL} info "AIF1TX1 Input 2 Volume"'""")
    for d in info.splitlines()[:5]:
        print("   ", d.strip())

    print("\n[1] Dựng câu mẫu ...")
    tts = F5TTSService()
    tts.load()
    wav = await tts.synthesize(CAU, use_cache=False)
    goc, sr = pcs._wav_to_pcm(wav)
    goc = goc / (float(np.abs(goc).max()) or 1.0)      # chuẩn về đỉnh 1.0

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
        ok_inj, msg_inj = await adb_service.set_uplink_injection(SERIAL, True)
        print(f"[3] {msg_inj}")
        if not ok_inj:
            return 1

        # TẮT MICRO trong lúc đo. Không tắt thì `AIF1TX1 Input 1` bơm tiếng phòng
        # vào cùng chỗ ta đang đo, và nó át hết: lần đo trước hạ mức phát 6 lần
        # mà RMS thu về gần như không đổi (5373 -> 4729), đỉnh luôn chạm 1.000.
        # Đo nhiễu micro rồi kết luận "đường tiêm khuếch đại 9 dB" là sai.
        sh(f"""su -c '{MIXCTL} set "AIF1TX1 Input 1" None'""")
        print("    đã tắt micro để đo cho sạch")
        await asyncio.sleep(0.5)

        giay = len(goc) / sr
        print(f"\n    {'đỉnh phát':>10}{'đỉnh thu':>11}{'RMS thu':>10}{'độ lợi':>9}")
        ket = []
        for dinh in a.muc:
            thu.clear()
            await bridge.play(wav_bytes(goc * dinh, sr), xu_ly=False)
            await asyncio.sleep(giay + 1.8)
            x = np.frombuffer(b"".join(thu), dtype=np.int16).astype(np.float32) / 32768.0
            if x.size < 1000:
                print(f"    {dinh:>10.2f}   (không thu được gì)")
                continue
            d_thu = float(np.abs(x).max())
            rms = float(np.sqrt((x ** 2).mean())) * 32768.0
            loi = 20 * np.log10(max(d_thu, 1e-9) / dinh)
            vo = " VỠ" if d_thu >= 0.999 else ""
            print(f"    {dinh:>10.2f}{d_thu:>11.3f}{rms:>10.0f}{loi:>8.1f}dB{vo}")
            ket.append((dinh, d_thu, rms))
            await asyncio.sleep(0.5)

        sach = [(d, t) for d, t, _ in ket if t < 0.95]
        print("\n" + "=" * 58)
        if sach:
            d, t = max(sach, key=lambda x: x[0])
            print(f"NÊN ĐẶT đỉnh phát {d:.2f}  (thu về {t:.3f}, còn dự trữ).")
            print(f"Tức phone_dinh_toi_da = {d:.2f} thay cho 0.89.")
            db = 20 * np.log10(d / 0.89)
            print(f"phone_muc_dbfs cũng phải hạ theo {db:.1f} dB -> "
                  f"{settings.phone_muc_dbfs + db:.0f}")
        else:
            print("MỌI MỨC ĐỀU VỠ - phải hạ bằng control âm lượng của codec,")
            print("không hạ được đủ bằng đường số.")
        print("=" * 58)
    finally:
        # Trả micro về. HAL cũng tự dựng lại ở lần đổi tuyến sau, nhưng trả tay
        # thì máy dùng được ngay chứ không phải chờ.
        sh(f"""su -c '{MIXCTL} set "AIF1TX1 Input 1" ASRC1IN1L'""")
        await adb_service.set_uplink_injection(SERIAL, False)
        await bridge.stop()
        await adb_service.stop_bridge(SERIAL, port=8123)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--muc", type=float, nargs="+",
                    default=[0.89, 0.60, 0.45, 0.32, 0.22, 0.15])
    return asyncio.run(chay(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
