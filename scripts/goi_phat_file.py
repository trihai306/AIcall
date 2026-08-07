"""Đẩy FILE THU SẴN vào cuộc gọi - thí nghiệm đối chứng cho tiếng "dè".

Câu hỏi cần trả lời: "dè" sinh ra Ở ĐÂU?
  - Nếu bản thu NGƯỜI THẬT đẩy vào cuộc gọi cũng dè  -> lỗi ở ĐƯỜNG TIÊM/máy,
    không phải ở tiếng TTS. Mọi cố gắng chỉnh TTS đều vô ích.
  - Nếu người thật nghe sạch mà TTS dè             -> lỗi ở TÍN HIỆU ta tạo ra.

Phát CẢ HAI trong CÙNG một cuộc gọi, cách nhau một khoảng im, để tai so trực
tiếp. Gọi hai lần rồi so trí nhớ thì sóng và mức mỗi lần một khác, không kết
luận được.

    python scripts/goi_phat_file.py 0396130621
    python scripts/goi_phat_file.py 0396130621 --tho     # KHÔNG xử lý gì
    python scripts/goi_phat_file.py 0396130621 --file duong/dan.wav
"""

import argparse
import asyncio
import re
import subprocess
import sys
import wave
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
SERIAL = "21f10e44220c7ece"

TEN_TRANG_THAI = {0: "rảnh", 1: "ĐÃ NỐI MÁY", 2: "đang giữ máy", 3: "đang quay số",
                  4: "đang đổ chuông bên kia", 5: "có cuộc gọi đến",
                  6: "cuộc gọi chờ", 7: "đã ngắt", 8: "đang ngắt"}


def sh(cmd: str, t: int = 60) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def trang_thai() -> int:
    m = re.search(r"mForegroundCallState=(\d+)", sh("dumpsys telephony.registry"))
    return int(m.group(1)) if m else -1


def doc_wav_bytes(p: Path) -> bytes:
    """Trả nguyên khối WAV. `play()` tự bóc và đổi tần số."""
    return p.read_bytes()


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
    ap.add_argument("--file", help="WAV muốn phát; bỏ trống thì dùng giọng mẫu")
    ap.add_argument("--tho", action="store_true",
                    help="gửi thẳng, KHÔNG chuẩn mức / tăng tuần hoàn")
    ap.add_argument("--duong", choices=["codec", "usb"], default=None)
    ap.add_argument("--giay", type=int, default=25)
    a = ap.parse_args()

    from backend.config import settings
    from backend.pipeline.session_manager import CallSession
    from backend.pipeline.streaming_pipeline import StreamingPipeline
    from backend.services import adb_service
    from backend.services.llm_service import LLMService
    from backend.services.phone_call_service import PhoneCallBridge
    from backend.services.rag_service import RAGService
    from backend.services.stt_service import STTService
    from backend.services.tts_service import F5TTSService

    ref = Path(a.file) if a.file else (
        PROJECT / settings.f5tts_ref_audio.lstrip("./"))
    if not ref.exists():
        print(f"Không thấy file: {ref}")
        return 1
    with wave.open(str(ref)) as w:
        giay_ref = w.getnframes() / w.getframerate()
    cau_txt = ref.with_suffix(".txt")
    cau = (cau_txt.read_text(encoding="utf-8").strip() if cau_txt.exists()
           else "Dạ em chào anh chị ạ. Em là nhân viên tư vấn của ngân hàng.")

    print(f"Bản thu người thật : {ref.name}  ({giay_ref:.1f}s)")
    print(f"Câu TTS sẽ đọc     : {cau[:60]}")
    print(f"Xử lý              : {'KHÔNG (gửi thô)' if a.tho else 'có (như đường thật)'}")
    print(f"Mức / tuần hoàn    : {settings.phone_muc_dbfs} dBFS / "
          f"{settings.phone_tang_tuan_hoan}\n")

    print("Nạp model ...")
    tts = F5TTSService()
    tts.load()
    wav_tts = await tts.synthesize(cau, use_cache=False)
    wav_ref = doc_wav_bytes(ref)

    pipeline = StreamingPipeline(stt=STTService(), llm=LLMService(),
                                 tts=tts, rag=RAGService())
    bridge = PhoneCallBridge(pipeline, CallSession(customer_name="Khách"),
                             port=8123)
    bridge.tam_dung_nghe = True

    print(f"[1] Bật cầu tiếng ...")
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
                print(f"    {i}s: {TEN_TRANG_THAI.get(t, f'mã {t}')}")
                truoc = t
            if t == 1:
                noi = True
                print(f"    -> mạng {sh('getprop gsm.network.type')}")
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

        xu = not a.tho
        print(f"\n[4] >>> PHÁT 1/2: BẢN THU NGƯỜI THẬT <<<")
        await bridge.play(wav_ref, xu_ly=xu)
        await asyncio.sleep(giay_ref + 2.5)

        print(f"[5] >>> PHÁT 2/2: TIẾNG TTS, cùng câu <<<")
        await bridge.play(wav_tts, xu_ly=xu)

        print(f"\n[6] Giữ máy {a.giay}s ...")
        for _ in range(a.giay // 3):
            await asyncio.sleep(3)
            if trang_thai() != 1:
                print("    cuộc gọi đã kết thúc")
                break
    finally:
        print("\n[7] Dọn dẹp ...")
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
