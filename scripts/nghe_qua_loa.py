"""Tiếng ra tới LOA điện thoại đã dè chưa? Không cần cuộc gọi.

Cả ba tuyến tiêm đều dè như nhau, nên định tuyến và mức đã bị loại. Nghi phạm
còn lại là tầng AudioTrack của Android. Phép thử này tách đúng đoạn đó:

    PC -> TCP -> app -> AudioTrack -> LOA NGOÀI -> micro máy -> PC

Không có bộ mã AMR, không có đường tiêm, không có codec thoại. Nếu bản thu về đã
dè thì lỗi nằm trước cả cuộc gọi, ở chính đường PC -> AudioTrack. Nếu sạch thì
AudioTrack vô can và phải soi tiếp phía codec/đường lên.

Bản thu sẽ có tiếng phòng - đó là chuyện đương nhiên của vòng âm học, đừng chấm
nó vì nền ồn. Chấm xem GIỌNG có rè, vỡ, đứt quãng không.

    python scripts/nghe_qua_loa.py
"""

import argparse
import asyncio
import os
import subprocess
import sys
import wave
from pathlib import Path

# Thu ở 24kHz để nhìn được cả phần trên 4kHz; đặt trước khi nạp backend vì các
# hằng số khung tính ngay lúc nạp module.
os.environ.setdefault("PHONE_RATE_LEN", "24000")

import numpy as np  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
SERIAL = "21f10e44220c7ece"
RA = PROJECT / "data" / "qua_loa"
CAU = ("Dạ em chào anh chị ạ. Em là nhân viên tư vấn của ngân hàng. "
       "Anh chị có cần em hỗ trợ thông tin gì không ạ?")


def sh(cmd: str, t: int = 90) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def ghi(p: Path, x: np.ndarray, sr: int) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    return p


async def chay(a) -> int:
    from backend.config import settings
    from backend.pipeline.session_manager import CallSession
    from backend.services import adb_service
    from backend.services import phone_call_service as pcs
    from backend.services.phone_call_service import PhoneCallBridge
    from backend.services.tts_service import F5TTSService

    kho = PROJECT / "data" / "mau_so_sanh.wav"
    if not kho.exists():
        print("Dựng câu mẫu ...")
        t = F5TTSService(); t.load()
        kho.write_bytes(await t.synthesize(CAU, use_cache=False))
    goc, sr = pcs._wav_to_pcm(kho.read_bytes())

    # Loa NGOÀI: loa áp tai quá nhỏ, micro không nghe lại nổi qua nền phòng.
    sh(f"media volume --stream 3 --set {a.am_luong}")
    ok, msg = await adb_service.start_bridge(SERIAL, port=8123, src=1)
    if not ok:
        print(msg); return 1
    # start_bridge không truyền usage, gửi lại intent với usage=2 (MEDIA).
    sh("am start-foreground-service -n com.tuktech.voicebridge/.BridgeService "
       f"--ei src 1 --ei port 8123 --ei usage 2 "
       f"--ei rate_xuong {settings.phone_rate_xuong} "
       f"--ei rate_len {settings.phone_rate_len}")
    await asyncio.sleep(1.0)

    bridge = PhoneCallBridge(None, CallSession(customer_name="K"), port=8123)
    bridge.tam_dung_nghe = True
    thu: list[bytes] = []
    bridge.theo_doi_khung = thu.append
    await bridge.start()

    try:
        print(f"[1] Phát ra loa ngoài (âm lượng {a.am_luong}/15) và thu lại ...")
        thu.clear()
        await bridge.play(kho.read_bytes())
        giay = len(goc) / sr
        await asyncio.sleep(giay + 2.0)

        x = np.frombuffer(b"".join(thu), dtype=np.int16).astype(np.float32) / 32768.0
        p = ghi(RA / "thu_tu_loa.wav", x, settings.phone_rate_len)
        dinh = float(np.abs(x).max())
        print(f"    thu được {x.size / settings.phone_rate_len:.1f}s, đỉnh {dinh:.3f}")
        if dinh >= 0.99:
            print("    CẢNH BÁO: micro thu bị vỡ - hạ --am-luong rồi chạy lại,")
            print("    không thì méo do vỡ chứ không phải do đường tiếng.")
        print(f"    {p}")
    finally:
        await bridge.stop()
        await adb_service.stop_bridge(SERIAL, port=8123)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--am-luong", type=int, default=6,
                    help="âm lượng loa 0-15; to quá thì micro thu vỡ")
    return asyncio.run(chay(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
