"""Thêm nền nhiễu nhỏ để chặn DTX của AMR - so ba mức trong một cuộc gọi.

Cơ chế nghi ngờ: micro đã tắt nên đường lên nhận IM LẶNG SỐ TUYỆT ĐỐI giữa các
câu. AMR-NB có DTX - bộ dò tiếng nói thấy im thì ngừng gửi khung tiếng, chỉ gửi
khung mô tả nền, đầu kia tự sinh tiếng nền nhân tạo. Với tín hiệu tổng hợp không
có nền, VAD dao động liên tục kể cả ở những âm nhẹ giữa câu, làm lời bị chặt vụn
và chuyển qua lại giữa tiếng thật với nền nhân tạo.

Điều này khớp với thứ đã quan sát: đổi định tuyến trong ABOX/codec sáu kiểu đều
không ảnh hưởng gì, vì DTX nằm trong bộ mã của modem, sau tất cả.

Nền nhiễu chạy LIÊN TỤC, kể cả giữa các câu - đó mới là điểm mấu chốt, vì DTX
kích hoạt đúng ở những quãng im.

    tuyến một  ->  không nền nhiễu (như hiện tại)
    tuyến hai  ->  nền -50 dBFS
    tuyến ba   ->  nền -38 dBFS

    python scripts/so_nen_nhieu.py 0396130621
"""

import argparse
import asyncio
import re
import subprocess
import sys
import wave
from io import BytesIO
from pathlib import Path

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

SERIAL = "21f10e44220c7ece"
CAU = ("Dạ em chào anh chị ạ. Em là nhân viên tư vấn của ngân hàng. "
       "Anh chị có cần em hỗ trợ thông tin gì không ạ?")
MOC = {1: "Tuyến một.", 2: "Tuyến hai.", 3: "Tuyến ba."}
NEN_DBFS = {1: None, 2: -50.0, 3: -38.0}


def sh(cmd: str, t: int = 90) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def trang_thai() -> int:
    m = re.search(r"mForegroundCallState=(\d+)", sh("dumpsys telephony.registry"))
    return int(m.group(1)) if m else -1


def dong_wav(x: np.ndarray, rate: int) -> bytes:
    buf = BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


def ghep(moc: np.ndarray, cau: np.ndarray, sr: int, nen_db: float | None,
         seed: int) -> bytes:
    """Ghép mốc + câu thành MỘT đoạn liền, có nền nhiễu chạy suốt nếu được yêu cầu.

    Phải liền một mạch: nếu gửi rời từng đoạn thì giữa chúng vẫn là im lặng tuyệt
    đối và DTX vẫn kích hoạt - đúng thứ đang muốn tránh.
    """
    im = np.zeros(int(1.2 * sr), dtype=np.float32)
    x = np.concatenate([im, moc, im, cau, im])
    if nen_db is not None:
        # Nhiễu hồng nhẹ hơn nhiễu trắng ở dải cao, nghe tự nhiên hơn và giống
        # nền phòng thật - thứ mà VAD của bộ mã vốn quen.
        r = np.random.default_rng(seed)
        trang = r.standard_normal(x.size).astype(np.float32)
        pho = np.fft.rfft(trang)
        f = np.arange(pho.size)
        f[0] = 1
        hong = np.fft.irfft(pho / np.sqrt(f), n=x.size).astype(np.float32)
        hong /= (np.abs(hong).max() or 1.0)
        x = x + hong * (10 ** (nen_db / 20))
    return dong_wav(x, sr)


async def chay(a) -> int:
    from backend.pipeline.session_manager import CallSession
    from backend.services import adb_service
    from backend.services import phone_call_service as pcs
    from backend.services.phone_call_service import PhoneCallBridge
    from backend.services.tts_service import F5TTSService

    _tts = []

    async def lay(ten_file: str, cau: str) -> bytes:
        f = PROJECT / "data" / ten_file
        if f.exists():
            return f.read_bytes()
        if not _tts:
            print("    nạp TTS ...")
            t = F5TTSService(); t.load(); _tts.append(t)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(await _tts[0].synthesize(cau, use_cache=False))
        return f.read_bytes()

    print("[1] Chuẩn bị tiếng ...")
    cau_x, sr = pcs._wav_to_pcm(await lay("mau_so_sanh.wav", CAU))
    cau_x = pcs.chuan_muc_thoai(cau_x)
    doan = {}
    for i, t in MOC.items():
        m, _ = pcs._wav_to_pcm(await lay(f"tuyen_{i}.wav", t))
        doan[i] = ghep(pcs.chuan_muc_thoai(m), cau_x, sr, NEN_DBFS[i], seed=i)

    ok, msg = await adb_service.start_bridge(SERIAL, port=8123, src=3)
    print(f"[2] {msg}")
    if not ok:
        return 1
    bridge = PhoneCallBridge(None, CallSession(customer_name="K"), port=8123)
    bridge.tam_dung_nghe = True
    await bridge.start()

    canh = None
    try:
        print(f"\n[3] Gọi {a.so} ... HÃY BẮT MÁY")
        sh("input keyevent KEYCODE_WAKEUP")
        sh("wm dismiss-keyguard")
        await asyncio.sleep(0.6)
        sh(f"am start -a android.intent.action.CALL -d tel:{a.so} "
           f"--ei com.android.phone.extra.slot 1")
        truoc = None
        for i in range(45):
            await asyncio.sleep(1)
            t = trang_thai()
            if t != truoc:
                print(f"    {i}s: trạng thái {t}")
                truoc = t
            if t == 1:
                break
        else:
            print("    không ai bắt máy")
            return 1
        await asyncio.sleep(2.0)

        ok_inj, msg_inj = await adb_service.set_uplink_injection(SERIAL, True)
        print(f"    {msg_inj}")
        if not ok_inj:
            return 1

        async def giu():
            while True:
                await asyncio.sleep(4)
                try:
                    await adb_service.set_uplink_injection(SERIAL, True)
                except Exception:
                    pass
        canh = asyncio.create_task(giu())
        await asyncio.sleep(1.0)

        for so in (a.tuyen or [1, 2, 3]):
            if trang_thai() != 1:
                print("    cuộc gọi kết thúc giữa chừng")
                break
            n = NEN_DBFS[so]
            print(f"\n    --- tuyến {so}: "
                  f"{'không nền nhiễu' if n is None else f'nền {n:.0f} dBFS'}")
            await bridge.play(doan[so], xu_ly=False)
            await asyncio.sleep(len(doan[so]) / (sr * 2) + 2.0)

        print("\n    TUYẾN NÀO NGHE SẠCH NHẤT? (một / hai / ba)")
        for _ in range(max(0, a.giay // 5)):
            if trang_thai() != 1:
                break
            await asyncio.sleep(5)
    finally:
        if canh is not None:
            canh.cancel()
        print("\n[4] Dọn dẹp ...")
        await adb_service.set_uplink_injection(SERIAL, False)
        sh("input keyevent KEYCODE_ENDCALL")
        await bridge.stop()
        await adb_service.stop_bridge(SERIAL, port=8123)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("so")
    ap.add_argument("--tuyen", type=int, nargs="*")
    ap.add_argument("--giay", type=int, default=10)
    return asyncio.run(chay(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
