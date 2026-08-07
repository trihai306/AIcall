"""Ghi lại ĐÚNG thứ máy nhận được từ khách trong cuộc gọi, rồi chấm.

Vì sao cần: nhiều cuộc gọi thật kết thúc với 0 lượt hoặc lượt có bản phiên âm
RỖNG. Ba khả năng, mắt thường không phân biệt được:
  a) tiếng khách KHÔNG về tới máy (đường thu hỏng)
  b) có về nhưng quá nhỏ so với ngưỡng VAD -> không mở lượt nào
  c) mở lượt được nhưng STT không đọc ra chữ (nhiễu, hoặc bị lọc avg_logprob)

Script móc vào `theo_doi_khung` của cầu tiếng để giữ lại từng khung 20ms, ghi ra
WAV, rồi báo: nền kênh, ngưỡng VAD tính được, mức đỉnh, bao nhiêu khung vượt
ngưỡng, và cuối cùng đưa cả file cho STT đọc thử.

Nhờ vậy trả lời được câu "khách nói mà máy có nghe thấy không" bằng số, không
phải đoán.

    python scripts/ghi_tieng_khach.py 0396130621
    python scripts/ghi_tieng_khach.py 0396130621 --giay 40
"""

import argparse
import asyncio
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

TEN_TT = {0: "rảnh", 1: "ĐÃ NỐI MÁY", 2: "giữ máy", 3: "đang quay số",
          4: "đổ chuông bên kia", 7: "đã ngắt", 8: "đang ngắt"}


def sh(cmd: str, t: int = 60) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def trang_thai() -> int:
    m = re.search(r"mForegroundCallState=(\d+)", sh("dumpsys telephony.registry"))
    return int(m.group(1)) if m else -1


async def giu_duong_tiem(adb_service, duong):
    while True:
        await asyncio.sleep(5.0)
        try:
            await adb_service.set_uplink_injection(SERIAL, True, duong)
        except Exception:
            pass


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("so")
    ap.add_argument("--giay", type=int, default=35)
    ap.add_argument("--duong", choices=["codec", "usb"], default=None)
    ap.add_argument("--src", type=int, default=3,
                    help="3 = chỉ tiếng khách; 4 = cả hai chiều")
    a = ap.parse_args()

    from backend.config import settings
    from backend.pipeline.session_manager import CallSession
    from backend.pipeline.streaming_pipeline import StreamingPipeline
    from backend.services import adb_service, phone_call_service as PS
    from backend.services.llm_service import LLMService
    from backend.services.phone_call_service import PhoneCallBridge
    from backend.services.rag_service import RAGService
    from backend.services.stt_service import STTService
    from backend.services.tts_service import F5TTSService

    print("Nạp model ...")
    stt = STTService()
    tts = F5TTSService()
    tts.load()
    pipeline = StreamingPipeline(stt=stt, llm=LLMService(), tts=tts,
                                 rag=RAGService())
    bridge = PhoneCallBridge(pipeline, CallSession(customer_name="Khách"),
                             port=8123)
    bridge.tam_dung_nghe = True

    khung: list[bytes] = []
    bridge.theo_doi_khung = khung.append      # giữ lại mọi khung nhận được

    print(f"[1] Bật cầu tiếng (nguồn {a.src}) ...")
    ok, msg = await adb_service.start_bridge(SERIAL, port=8123, src=a.src)
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

        print("[3] Chờ bắt máy — HÃY BẮT MÁY ...")
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
        giu = asyncio.create_task(giu_duong_tiem(adb_service, a.duong))

        khung.clear()
        bridge.tam_dung_nghe = False
        print(f"\n[4] AI chào, rồi GHI tiếng khách trong {a.giay}s")
        print("    >>> HÃY NÓI VÀI CÂU VÀO MÁY <<<\n")
        wav = await tts.synthesize(
            "Dạ em chào anh chị ạ. Anh chị nói thử vài câu giúp em ạ.",
            use_cache=False)
        await bridge.play(wav)

        for _ in range(a.giay // 2):
            await asyncio.sleep(2)
            if trang_thai() != 1:
                print("    cuộc gọi đã kết thúc")
                break
    finally:
        if giu is not None:
            giu.cancel()
        sh("input keyevent KEYCODE_ENDCALL")
        await bridge.stop()
        await adb_service.set_uplink_injection(SERIAL, False, a.duong)
        await adb_service.stop_bridge(SERIAL, port=8123)

    # ---- chấm ----------------------------------------------------------
    if not khung:
        print("\n[!] KHÔNG nhận được khung nào — đường thu hỏng hẳn.")
        return 1

    pcm = b"".join(khung)
    x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    giay = len(x) / PS.RATE_LEN
    out = PROJECT / "logs" / "tieng_khach"
    out.mkdir(parents=True, exist_ok=True)
    f_wav = out / "khach_nói.wav"
    with wave.open(str(f_wav), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(PS.RATE_LEN)
        w.writeframes(pcm)

    N = PS.FRAME_SAMPLES_LEN
    khung_rms = np.array([np.sqrt((x[i:i + N] ** 2).mean())
                          for i in range(0, len(x) - N, N)])
    nen = float(np.percentile(khung_rms, 75))
    nguong = max(PS.VAD_RMS_ON, nen * PS.VAD_HE_SO_ON)
    vuot = int((khung_rms >= nguong).sum())

    print(f"\n  {'=' * 60}")
    print(f"  ĐÃ NHẬN {len(khung)} khung = {giay:.1f}s tiếng")
    print(f"  {'=' * 60}")
    print(f"    nền kênh (phân vị 75)   {nen:>8.0f}")
    print(f"    ngưỡng VAD tính ra      {nguong:>8.0f}   (= max(700, nền×3))")
    print(f"    RMS trung vị            {np.median(khung_rms):>8.0f}")
    print(f"    RMS cao nhất            {khung_rms.max():>8.0f}")
    print(f"    khung vượt ngưỡng       {vuot:>8d} / {len(khung_rms)}")
    print(f"    cần {PS.VAD_ON_FRAMES} khung LIÊN TIẾP mới mở một lượt")
    if khung_rms.max() < nguong:
        print(f"\n    [!] KHÔNG khung nào vượt ngưỡng -> không lượt nào được mở.")
        print(f"        Tiếng khách quá nhỏ so với nền, hoặc nền quá cao.")
    print(f"\n    file: {f_wav}")

    # đưa cho STT đọc thử
    print(f"\n  STT đọc thử toàn bộ đoạn ghi ...")
    try:
        from backend.services.audio_utils import resample_audio
        x16 = resample_audio(x / 32768.0, PS.RATE_LEN, 16000)
        pcm16 = (np.clip(x16, -1, 1) * 32767).astype("<i2").tobytes()
        kq = await stt.transcribe(pcm16, sample_rate=16000)
        print(f"    -> {kq!r}")
    except Exception as e:
        print(f"    (không chạy được STT: {e})")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
