"""So ba tuyến tiêm trong MỘT cuộc gọi - nghe rồi chọn.

Đã loại được: bộ mã AMR (bản mô phỏng ngoại tuyến nghe sạch), giọng F5 (cùng lý
do), micro lọt vào (đã tắt cả 4 đầu vào và đọc lại xác nhận), đói dữ liệu
AudioTrack (0 lần/giây sau khi sửa nhịp gửi và nới đệm), âm lượng mixer (cả 4
đầu vào đều 32/48 = 0 dB).

Còn lại chính chỗ tôi tự ý đổi: `SIFS1`. Ban đầu tiếng AI đi qua `SIFS0` như mọi
tiếng phát khác, tôi chuyển sang `SIFS1` để tách khỏi đường thu (không thì AI
nghe lại chính nó). Nhưng chưa hề kiểm `SIFS1` có chạy đúng tần số không.

Mẫu hình sau nhiều vòng thử:

    PC -> AudioTrack -> LOA (qua UAIF1)   ->  SẠCH (thu lại nghe kỹ)
    mô phỏng AMR ngoại tuyến              ->  SẠCH
    mọi cách tiêm qua UAIF0 -> codec      ->  DÈ, cả ba cách như nhau

Thứ có mặt trong MỌI trường hợp dè và vắng trong mọi trường hợp sạch là
`ABOX UAIF0 SPK` - tức việc bật chiều PHÁT của UAIF0. Lúc đang gọi HAL chỉ dùng
UAIF0 cho chiều THU (micro), nên bật thêm chiều phát là dùng một giao diện được
cấu hình cho việc khác.

Vòng này thử bỏ hẳn codec: đường lên của modem lấy từ `ABOX NSRC1`, mà control đó
chọn thẳng được SIFS1.

Tìm được trong mixer_paths.xml của máy: Samsung có sẵn tuyến lấy tiếng ĐƯỜNG LÊN
từ THIẾT BỊ NGOÀI (micro của tai nghe USB), tên `incall-usb-headset-mic`:

    ABOX SPUS OUT6 = SIFS2      RDMA6 -> SIFS2
    ABOX SIFS2     = SPUS OUT6
    ABOX NSRC1     = SIFS2      đường lên lấy từ SIFS2
    ABOX SIFM1     = WDMA
    ABOX ERAP info USB On = 1   BÁO cho khối xử lý biết nguồn là thiết bị ngoài

Cờ cuối là thứ chưa bao giờ đặt. Không có nó, khối xử lý tiếng vẫn áp nguyên bộ
lọc dành cho micro cầm tay lên tín hiệu của ta - khớp với tiếng dè, và giải thích
vì sao đổi định tuyến kiểu gì cũng như nhau.

    tuyến một  ->  cách hiện tại (SIFS1 + tiêm ở codec), để đối chiếu
    tuyến hai  ->  tuyến USB chính thức, KHÔNG bật cờ ERAP
    tuyến ba   ->  tuyến USB chính thức, CÓ bật cờ ERAP USB On

    python scripts/so_tuyen_usb.py 0396130621
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
MIXCTL = "/data/local/tmp/mixctl"
CAU = ("Dạ em chào anh chị ạ. Em là nhân viên tư vấn của ngân hàng. "
       "Anh chị có cần em hỗ trợ thông tin gì không ạ?")
MOC = {1: "Tuyến một.", 2: "Tuyến hai.", 3: "Tuyến ba."}


def sh(cmd: str, t: int = 90) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def dat(*cap: tuple[str, str]) -> None:
    lenh = "; ".join(f'{MIXCTL} set "{t}" {v}' for t, v in cap)
    sh(f"su -c '{lenh}'")


def doc(ten: str) -> str:
    m = re.search(r"= \d+ \((.*)\)|= (\d+)$",
                  sh(f"""su -c '{MIXCTL} get "{ten}"'""").strip().splitlines()[-1]
                  if sh(f"""su -c '{MIXCTL} get "{ten}"'""") else "")
    return (m.group(1) or m.group(2)) if m else "?"


def trang_thai() -> int:
    m = re.search(r"mForegroundCallState=(\d+)", sh("dumpsys telephony.registry"))
    return int(m.group(1)) if m else -1


def tuyen(so: int) -> list[tuple[str, str]]:
    """Bộ control cho từng tuyến ở khâu codec.

    Chung cho cả ba: tiếng AI vào SIFS1 rồi ra codec qua UAIF0. Khác nhau ở chỗ
    LẤY nó vào đường lên thế nào.
    """
    # Dọn sạch mọi đường tiêm cũ trước, không thì các tuyến chồng lên nhau.
    cap = [(f"AIF1TX{tx} Input {i}", "None") for tx in (1, 2) for i in (1, 2, 3, 4)]

    if so == 1:
        # Cách hiện tại, giữ để đối chiếu.
        cap += [(f"ABOX SPUS OUT{i}", "SIFS1") for i in range(6)]
        cap += [("ABOX UAIF0 SPK", "SIFS1"), ("ABOX NSRC1", "UAIF0"),
                ("ABOX ERAP info USB On", "0"),
                ("AIF1TX1 Input 2", "AIF1RX1"), ("AIF1TX2 Input 2", "AIF1RX1")]
    else:
        # Tuyến USB chính thức. Luồng phát của ta đi vào SIFS2 rồi thẳng lên
        # modem, không qua codec, không qua UAIF0.
        cap += [(f"ABOX SPUS OUT{i}", "SIFS2") for i in range(6)]
        cap += [("ABOX SIFS2", "SPUS OUT0"),
                ("ABOX NSRC1", "SIFS2"),
                ("ABOX SIFM1", "WDMA"),
                ("ABOX UAIF0 SPK", "RESERVED"),
                ("ABOX ERAP info USB On", "1" if so == 3 else "0")]
    return cap


def dong_wav(x: np.ndarray, rate: int) -> bytes:
    buf = BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


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
    goc, sr = pcs._wav_to_pcm(await lay("mau_so_sanh.wav", CAU))
    cau_wav = dong_wav(pcs.chuan_muc_thoai(goc), sr)
    moc = {}
    for i, t in MOC.items():
        m, msr = pcs._wav_to_pcm(await lay(f"tuyen_{i}.wav", t))
        moc[i] = dong_wav(pcs.chuan_muc_thoai(m), msr)

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
        await asyncio.sleep(2.5)

        hien = {"so": 1}

        async def giu():
            # HAL dựng lại tuyến khi đổi định tuyến; giữ lại đúng tuyến đang thử.
            while True:
                await asyncio.sleep(4)
                try:
                    dat(*tuyen(hien["so"]))
                except Exception:
                    pass

        for so in (a.tuyen or [1, 2, 3]):
            if trang_thai() != 1:
                print("    cuộc gọi kết thúc giữa chừng")
                break
            hien["so"] = so
            dat(*tuyen(so))
            if canh is None:
                canh = asyncio.create_task(giu())
            await asyncio.sleep(0.6)
            ten = {1: "cách hiện tại (SIFS1 + codec)",
                   2: "tuyến USB, KHÔNG cờ ERAP",
                   3: "tuyến USB, CÓ cờ ERAP USB On"}[so]
            print(f"\n    --- tuyến {so}: {ten}")
            for lan in range(a.lap):
                await bridge.play(moc[so], xu_ly=False)
                await asyncio.sleep(2.2)
                await bridge.play(cau_wav, xu_ly=False)
                await asyncio.sleep(10)

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
        # Trả chuỗi micro về như HAL đặt, không thì cuộc gọi thường mất tiếng.
        # Trả đường lên về micro, không thì cuộc gọi thường mất tiếng.
        dat(("ABOX NSRC1", "UAIF0"), ("ABOX UAIF0 SPK", "RESERVED"),
            ("ABOX ERAP info USB On", "0"),
            *[(f"ABOX SPUS OUT{i}", "SIFS0") for i in range(6)])
        sh("input keyevent KEYCODE_ENDCALL")
        await bridge.stop()
        await adb_service.stop_bridge(SERIAL, port=8123)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("so")
    ap.add_argument("--tuyen", type=int, nargs="*")
    ap.add_argument("--lap", type=int, default=1)
    ap.add_argument("--giay", type=int, default=10)
    return asyncio.run(chay(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
