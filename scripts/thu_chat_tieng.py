"""So ba cách xử lý tiếng trong MỘT cuộc gọi - nghe rồi chọn.

Người nghe báo "có tiếng rồi nhưng dè". Nghi vấn: nâng `rate_xuong` lên 24000 đã
vô tình tắt cả cụm `toi_uu_cho_thoai`, mà trong cụm đó có hai việc khác hẳn nhau:

  - bù phổ cho LOA THOẠI hẹp băng   -> đích ở đây không phải loa, bật lên là dè
  - giới hạn đỉnh + chuẩn mức       -> LUÔN cần, bộ mã AMR vỡ đỉnh như mọi bộ mã

Tắt cả hai làm tiếng TTS đi thẳng ở mức đầy thang vào bộ trộn của codec. Đã tách
`chuan_muc_thoai` ra riêng; script này để nghe xem tách vậy có đúng không.

Mỗi bản phát trước một số tiếng bíp để đánh dấu:

    1 bíp  ->  chuẩn mức -19 dBFS      (bản mới)
    2 bíp  ->  chuẩn mức -26 dBFS      (nhỏ hơn 7 dB - thử xem có phải vỡ tiếng)
    3 bíp  ->  chuẩn mức + bù hẹp băng
    4 bíp  ->  không xử lý gì          (bản đang bị dè, để đối chiếu)

Script cũng đọc số lần AudioTrack thiếu tiếng trước và sau khi phát - thiếu
tiếng cũng nghe thành rè, và bản dump trước đó đã thấy 8364 lần.

    python scripts/thu_chat_tieng.py 0396130621
"""

import argparse
import asyncio
import math
import re
import struct
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


def sh(cmd: str, t: int = 90) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def trang_thai() -> int:
    m = re.search(r"mForegroundCallState=(\d+)", sh("dumpsys telephony.registry"))
    return int(m.group(1)) if m else -1


def thieu_tieng() -> int:
    """Tổng số lần AudioTrack thiếu tiếng, đọc từ bảng Tracks của AudioFlinger."""
    d = sh("dumpsys media.audio_flinger")
    tong = 0
    for dong in d.splitlines():
        # Dòng track có dạng: "  0  yes  16841  377 A 0x001 ... <Underruns> ..."
        c = dong.split()
        if len(c) >= 16 and c[2].isdigit() and c[1] in ("yes", "no"):
            try:
                tong += int(c[-4])
            except (ValueError, IndexError):
                pass
    return tong


# Dấu mốc phải là GIỌNG NÓI, không phải tiếng bíp. AMR-NB là vocoder: nó dựng
# lại tiếng theo mô hình thanh quản người, nên sóng sin thuần qua nó méo mó là
# chuyện đương nhiên chứ không phải lỗi đường truyền. Dùng bíp làm mốc thì người
# nghe tưởng cả hệ thống hỏng, còn tôi thì đi sửa nhầm chỗ - đã xảy ra thật.
SO_DEM = ["", "Bản một.", "Bản hai.", "Bản ba.", "Bản bốn."]


def dong_wav(x: np.ndarray, rate: int) -> bytes:
    pcm = np.clip(x, -1.0, 1.0)
    pcm = (pcm * 32767).astype(np.int16)
    buf = BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


async def chay(a) -> int:
    from backend.pipeline.session_manager import CallSession
    from backend.services import adb_service, phone_call_service as pcs
    from backend.services.phone_call_service import PhoneCallBridge
    from backend.services.tts_service import F5TTSService  # noqa: F401

    # Nhớ sẵn ra đĩa. Nạp TTS mất khoảng một phút, mà chuông chỉ reo sau đó -
    # người bên kia chờ mỏi rồi bỏ, đã hụt ba cuộc vì lý do này. Lần chạy sau
    # đọc lại từ đĩa nên chuông reo gần như ngay.
    _tts = []

    async def doc_hoac_dung(ten_file: str, cau: str) -> bytes:
        f = PROJECT / "data" / ten_file
        if f.exists() and not a.dung_lai:
            return f.read_bytes()
        if not _tts:
            print("    nạp TTS ...")
            t = F5TTSService()
            t.load()
            _tts.append(t)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(await _tts[0].synthesize(cau, use_cache=False))
        return f.read_bytes()

    print("[1] Chuẩn bị câu mẫu và dấu mốc ...")
    wav = await doc_hoac_dung("mau_so_sanh.wav", CAU)
    goc, sr = pcs._wav_to_pcm(wav)

    moc = {}
    for i in range(1, len(SO_DEM)):
        m, msr = pcs._wav_to_pcm(await doc_hoac_dung(f"moc_{i}.wav", SO_DEM[i]))
        moc[i] = dong_wav(pcs.chuan_muc_thoai(m), msr)

    # Bản 2 hạ thêm 7 dB để kiểm giả thuyết vỡ tiếng. Không kiểm được bằng máy:
    # nguồn MIC của Android không đọc thẳng AIF1TX1 nên vòng lặp trên máy đo ra
    # tín hiệu không đổi theo mức phát - vô giá trị. Chỉ còn cách nghe.
    chuan = pcs.chuan_muc_thoai(goc)
    ban = [
        ("chuẩn mức -19 dBFS", dong_wav(chuan, sr)),
        ("chuẩn mức -26 dBFS (thử vỡ tiếng)", dong_wav(chuan * 0.45, sr)),
        ("chuẩn mức + bù hẹp băng", dong_wav(pcs.toi_uu_cho_thoai(goc, sr), sr)),
        ("không xử lý gì", wav),
    ]

    ok, msg = await adb_service.start_bridge(SERIAL, port=8123, src=3)
    print(f"[2] {msg}")
    if not ok:
        return 1
    bridge = PhoneCallBridge(None, CallSession(customer_name="Khách"), port=8123)
    bridge.tam_dung_nghe = True
    await bridge.start()

    try:
        print(f"\n[3] Gọi {a.so} ... HÃY BẮT MÁY")
        # Mở khoá TRƯỚC khi gọi. Màn khoá thì giao diện gọi không lên được và
        # cuộc gọi đứng im ở "rảnh" - trông hệt như không ai bắt máy, đã mất
        # nhiều lượt vì tưởng nhầm là nhà mạng chặn.
        sh("input keyevent KEYCODE_WAKEUP")
        sh("wm dismiss-keyguard")
        await asyncio.sleep(0.6)
        # Chỉ định thẳng khe SIM: máy hai khe bật hộp chọn SIM cho số chưa gọi
        # bao giờ, mà hộp đó chờ người bấm. Khe 1 trống, Viettel ở khe 2 -> slot 1.
        sh(f"am start -a android.intent.action.CALL -d tel:{a.so} "
           f"--ei com.android.phone.extra.slot 1")
        # In từng lần đổi trạng thái. Không in thì "không ai bắt máy" che mất
        # trường hợp máy còn chẳng quay được số - đã mất mấy lượt vì lẫn hai cái.
        TEN = {0: "rảnh", 1: "ĐÃ NỐI MÁY", 3: "đang quay số",
               4: "đang đổ chuông bên kia", 7: "đã ngắt"}
        truoc = None
        for i in range(45):
            await asyncio.sleep(1)
            t = trang_thai()
            if t != truoc:
                print(f"    {i}s: {TEN.get(t, t)}")
                truoc = t
            if t == 1:
                break
        else:
            print("    hết giờ chờ" + ("" if truoc else " - máy không quay số"))
            return 1
        await asyncio.sleep(1.5)
        ok_inj, msg_inj = await adb_service.set_uplink_injection(SERIAL, True)
        print(f"    {msg_inj}")
        if not ok_inj:
            return 1

        # Đọc lại để CHẮC micro đã tắt. Đặt xong mà không đọc lại thì không biết
        # HAL có giật lại không.
        doc = await adb_service.doc_duong_tiem(SERIAL)
        for k in sorted(doc):
            canh = "  <-- tiếng AI" if doc[k] == "AIF1RX1" else (
                "  <-- CÒN NỐI, tiếng phòng sẽ lọt vào" if doc[k] != "None" else "")
            print(f"        {k} = {doc[k]}{canh}")

        # HAL dựng lại chuỗi micro mỗi lần đổi tuyến, nên phải giữ đường tiêm.
        # Thiếu cái này thì micro bật lại giữa chừng mà không ai biết.
        async def giu():
            while True:
                await asyncio.sleep(4)
                try:
                    await adb_service.set_uplink_injection(SERIAL, True)
                except Exception:
                    pass
        canh_task = asyncio.create_task(giu())

        # Nghỉ một nhịp sau khi nối máy: người bên kia vừa bấm nghe còn đang đưa
        # máy lên tai, phát ngay thì bản đầu tiên nghe hụt - đã xảy ra thật.
        await asyncio.sleep(2.5)

        for so, (ten, du_lieu) in enumerate(ban, start=1):
            if a.ban and so not in a.ban:
                continue
            if trang_thai() != 1:
                print("    cuộc gọi kết thúc giữa chừng")
                break
            print(f"\n    --- bản {so}: {ten}")
            for lan in range(max(1, a.lap)):
                await bridge.play(moc[so], xu_ly=False)
                await asyncio.sleep(2.2)
                # Bốn bản đã xử lý sẵn ở trên nên gửi thô, không xử lý lần nữa.
                await bridge.play(du_lieu, xu_ly=False)
                await asyncio.sleep(10)

        print("\n    BẢN NÀO NGHE SẠCH NHẤT? (một / hai / ba / bốn)")
        for _ in range(max(0, a.giay // 5)):
            if trang_thai() != 1:
                break
            await asyncio.sleep(5)
    finally:
        print("\n[5] Dọn dẹp ...")
        try:
            canh_task.cancel()
        except NameError:
            pass
        await adb_service.set_uplink_injection(SERIAL, False)
        sh("input keyevent KEYCODE_ENDCALL")
        await bridge.stop()
        await adb_service.stop_bridge(SERIAL, port=8123)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("so")
    ap.add_argument("--giay", type=int, default=10)
    ap.add_argument("--ban", type=int, nargs="*",
                    help="chỉ phát những bản này (vd --ban 1), mặc định phát hết")
    ap.add_argument("--lap", type=int, default=1,
                    help="phát mỗi bản mấy lần")
    ap.add_argument("--dung-lai", action="store_true",
                    help="dựng lại câu mẫu thay vì đọc bản đã lưu")
    return asyncio.run(chay(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
