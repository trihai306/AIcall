"""Dò mức âm lượng: phát NHIỀU mức trong CÙNG một cuộc gọi để chọn bằng tai.

Vì sao gộp vào một cuộc: mỗi cuộc gọi sóng và tuyến một khác, gọi bốn lần rồi
so trí nhớ thì không kết luận được mức nào vừa. Phát liền nhau trong một cuộc
thì tai so trực tiếp.

Mỗi đoạn tự xưng số thứ tự ("Mức một", "Mức hai"...) nên không lẫn thứ tự.

Bỏ qua `chuan_muc_thoai` của đường thật (gọi `play(xu_ly=False)`) vì script tự
chuẩn mức tới đúng con số muốn thử; để nó chạy nữa thì mức bị ghi đè về
`phone_muc_dbfs` và cả bốn đoạn ra như nhau.

    python scripts/goi_do_muc.py 0396130621
    python scripts/goi_do_muc.py 0396130621 --muc -30 -34 -38 -42
"""

import argparse
import asyncio
import io
import re
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
SERIAL = "21f10e44220c7ece"

CAU = "Bên em đang có chương trình vay tín chấp lãi suất ưu đãi."
SO_CHU = {1: "một", 2: "hai", 3: "ba", 4: "bốn", 5: "năm", 6: "sáu"}
TEN_TT = {0: "rảnh", 1: "ĐÃ NỐI MÁY", 2: "đang giữ máy", 3: "đang quay số",
          4: "đang đổ chuông bên kia", 7: "đã ngắt", 8: "đang ngắt"}


def sh(cmd: str, t: int = 60) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def trang_thai() -> int:
    m = re.search(r"mForegroundCallState=(\d+)", sh("dumpsys telephony.registry"))
    return int(m.group(1)) if m else -1


def bo_wav(x: np.ndarray, sr: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def chuan_toi_muc(x: np.ndarray, dbfs: float, dinh_toi_da: float) -> np.ndarray:
    """Chuẩn RMS tới `dbfs`, nhưng không để đỉnh vượt trần."""
    rms = float(np.sqrt((x ** 2).mean())) or 1e-9
    dinh = float(np.abs(x).max()) or 1e-9
    he_so = min(10 ** (dbfs / 20) / rms, dinh_toi_da / dinh)
    return (x * he_so).astype(np.float32)


async def giu_duong_tiem(adb_service, duong, chu_ky: float = 5.0):
    while True:
        await asyncio.sleep(chu_ky)
        try:
            await adb_service.set_uplink_injection(SERIAL, True, duong)
        except Exception:
            pass


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("so")
    ap.add_argument("--muc", type=float, nargs="+",
                    default=[-26, -30, -34, -38],
                    help="các mức dBFS muốn thử, theo thứ tự phát")
    ap.add_argument("--duong", choices=["codec", "usb"], default=None)
    a = ap.parse_args()

    from backend.config import settings
    from backend.pipeline.session_manager import CallSession
    from backend.pipeline.streaming_pipeline import StreamingPipeline
    from backend.services import adb_service, phone_call_service as PS
    from backend.services.audio_utils import resample_audio
    from backend.services.llm_service import LLMService
    from backend.services.phone_call_service import PhoneCallBridge
    from backend.services.rag_service import RAGService
    from backend.services.stt_service import STTService
    from backend.services.tts_service import F5TTSService

    print("Nạp model ...")
    tts = F5TTSService()
    tts.load()

    # Dựng sẵn từng đoạn, mỗi đoạn tự xưng số thứ tự
    doan = []
    for i, dbfs in enumerate(a.muc, 1):
        w = await tts.synthesize(f"Mức {SO_CHU.get(i, i)}. {CAU}", use_cache=False)
        with wave.open(io.BytesIO(w)) as f:
            sr = f.getframerate()
            x = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16)
        x = x.astype(np.float32) / 32768
        x8 = resample_audio(x, sr, PS.RATE_XUONG)
        if settings.phone_tang_tuan_hoan and PS.RATE_XUONG <= PS.NGUONG_HEP_BANG:
            x8 = PS.tang_tuan_hoan(x8, PS.RATE_XUONG)
        x8 = chuan_toi_muc(x8, dbfs, settings.phone_dinh_toi_da)
        doan.append((dbfs, bo_wav(x8, PS.RATE_XUONG),
                     len(x8) / PS.RATE_XUONG, float(np.abs(x8).max())))
        print(f"    mức {i}: {dbfs:>6.1f} dBFS   đỉnh {doan[-1][3]:.3f}   "
              f"{doan[-1][2]:.1f}s")

    pipeline = StreamingPipeline(stt=STTService(), llm=LLMService(),
                                 tts=tts, rag=RAGService())
    bridge = PhoneCallBridge(pipeline, CallSession(customer_name="Khách"),
                             port=8123)
    bridge.tam_dung_nghe = True

    print("\n[1] Bật cầu tiếng ...")
    ok, msg = await adb_service.start_bridge(SERIAL, port=8123, src=3)
    print(f"    {msg}")
    if not ok:
        return 1
    await bridge.start()

    giu = None
    try:
        print(f"[2] Gọi {a.so} ...")
        sh("input keyevent KEYCODE_WAKEUP")
        sh("wm dismiss-keyguard")
        await asyncio.sleep(0.6)
        sh(f"am start -a android.intent.action.CALL -d tel:{a.so} "
           f"--ei com.android.phone.extra.slot 1")

        print("[3] Chờ bắt máy (tối đa 45s) — HÃY BẮT MÁY ...")
        truoc, noi = None, False
        for i in range(45):
            await asyncio.sleep(1)
            t = trang_thai()
            if t != truoc:
                print(f"    {i}s: {TEN_TT.get(t, f'mã {t}')}")
                truoc = t
            if t == 1:
                noi = True
                break
        if not noi:
            print("    không ai bắt máy")
            return 1

        await asyncio.sleep(1.5)
        ok_i, msg_i = await adb_service.set_uplink_injection(SERIAL, True, a.duong)
        print(f"    {msg_i}")
        if not ok_i:
            return 1
        giu = asyncio.create_task(giu_duong_tiem(adb_service, a.duong))

        print()
        for i, (dbfs, wav, giay, dinh) in enumerate(doan, 1):
            if trang_thai() != 1:
                print("    cuộc gọi đã kết thúc")
                break
            print(f"[4.{i}] >>> MỨC {i}: {dbfs:.0f} dBFS <<<")
            await bridge.play(wav, xu_ly=False)
            await asyncio.sleep(giay + 2.0)

        print("\n[5] Giữ máy thêm 8s ...")
        await asyncio.sleep(8)
    finally:
        print("\n[6] Dọn dẹp ...")
        if giu is not None:
            giu.cancel()
        sh("input keyevent KEYCODE_ENDCALL")
        await bridge.stop()
        await adb_service.set_uplink_injection(SERIAL, False, a.duong)
        await adb_service.stop_bridge(SERIAL, port=8123)
        print("    xong")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
