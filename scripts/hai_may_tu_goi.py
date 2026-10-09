"""Hai máy phone farm TỰ GỌI NHAU: máy AI gọi sang máy "khách", máy khách tự bắt
máy rồi phát các câu hỏi đã dựng sẵn vào đường lên. Không cần người nghe máy.

    máy AI   (mặc định trong hệ thống)  --GSM-->  máy khách
    backend lo trọn phía AI (đường sản phẩm thật: POST /contacts/{id}/call)
    script này lo phía khách: bắt máy, cầu tiếng src=4, tiêm câu hỏi, thu lại.

Kết quả: in từng lượt (khách hỏi gì - AI nghe ra gì - AI đáp gì - đi đường nào -
bao lâu), và lưu bản thu PHÍA KHÁCH (cả hai chiều) vào data/tu_goi/<giờ>.wav -
đây là thứ tai khách thật sẽ nghe, khác bản ghi của backend.

    .venv\\python.exe scripts\\hai_may_tu_goi.py 0833816298 --may-khach 228b1b68920b7ece

Chạy từ thư mục gốc dự án (settings đọc .env theo thư mục làm việc).
"""
import argparse
import asyncio
import base64
import io
import json
import socket
import sys
import threading
import time
import urllib.parse
import urllib.request
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from backend.services import adb_service as ad  # noqa: E402

API = "http://127.0.0.1:8100"
RATE = 8000
KHUNG = 320  # 20ms @8k, 16-bit mono
CAU_HOI = [
    "Lãi suất vay tín chấp bao nhiêu em?",
    "Vay tối đa được bao nhiêu?",
    "Hồ sơ vay cần những gì?",
    "Bao lâu thì giải ngân em?",
    "Trả trước hạn có mất phí không?",
    "Anh làm nghề tự do thì có vay được không?",
    "Để anh suy nghĩ thêm đã.",
    "Cảm ơn em nhé.",
]


def api(duong, du_lieu=None, form=None, cho=180):
    data, headers = None, {}
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
    elif du_lieu is not None:
        data = json.dumps(du_lieu, ensure_ascii=False).encode()
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(API + duong, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=cho) as r:
        return json.loads(r.read().decode("utf-8"))


def dung_tieng(cau: str, giong: str) -> bytes:
    """Câu hỏi của "khách" bằng TTS giọng khác, hạ về 8 kHz PCM16."""
    from scipy.signal import resample_poly
    ra = api("/api/voices/test-tts", form={"text": cau, "voice_name": giong})
    if ra.get("error"):
        raise RuntimeError(ra["error"])
    b64 = ra.get("audio") or ra.get("audio_base64") or ra.get("wav") or ""
    with wave.open(io.BytesIO(base64.b64decode(b64.split(",")[-1]))) as w:
        sr, pcm = w.getframerate(), np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    x = resample_poly(pcm.astype(np.float32), RATE, sr)
    x = x / (np.max(np.abs(x)) + 1e-6) * 9000  # mức vừa phải, không chạm trần
    return x.astype(np.int16).tobytes()


class CauKhach:
    """Một kết nối TCP tới app cầu nối trên máy khách: gửi đều 20ms, thu về."""

    def __init__(self, port: int):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.sock.settimeout(1.0)
        self.thu = bytearray()
        self.cho_gui = bytearray()
        self.khoa = threading.Lock()
        self.chay = True
        self.dang_noi = False
        threading.Thread(target=self._nhan, daemon=True).start()
        threading.Thread(target=self._gui, daemon=True).start()

    def _nhan(self):
        while self.chay:
            try:
                d = self.sock.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if not d:
                break
            self.thu += d

    def _gui(self):
        im = b"\0" * KHUNG
        moc = time.perf_counter()
        while self.chay:
            with self.khoa:
                if len(self.cho_gui) >= KHUNG:
                    khung, self.dang_noi = bytes(self.cho_gui[:KHUNG]), True
                    del self.cho_gui[:KHUNG]
                else:
                    khung, self.dang_noi = im, False
            try:
                self.sock.sendall(khung)
            except OSError:
                break
            moc += 0.02
            time.sleep(max(0.0, moc - time.perf_counter()))

    def noi(self, pcm: bytes):
        with self.khoa:
            self.cho_gui += pcm + b"\0" * (KHUNG - len(pcm) % KHUNG)

    def muc(self, giay: float = 0.3) -> float:
        n = int(RATE * giay) * 2
        x = np.frombuffer(bytes(self.thu[-n:]), dtype=np.int16).astype(np.float32)
        return float(np.sqrt(np.mean(x * x))) if len(x) else 0.0

    def dong(self):
        self.chay = False
        try:
            self.sock.close()
        except OSError:
            pass


def cho_ben_kia_noi_xong(cau: CauKhach, nen: float, toi_da: float, im_can: float = 1.6) -> str:
    """Chờ AI nói rồi IM `im_can` giây. Trả 'xong' | 'khong_noi' | 'het_gio'."""
    # Ngưỡng CỐ ĐỊNH theo trần: mức nền đo lúc vào cuộc có khi dính đúng lời
    # chào (nền 1522 -> ngưỡng 5300, không bao giờ thấy AI nói, script hỏi dồn
    # lên câu trả lời). Tiếng AI ở bản thu này 1000-3000, lúc im dưới 50.
    nguong = min(max(250.0, nen * 3.5), 600.0)
    t0, da_noi, im_tu = time.time(), False, None
    while time.time() - t0 < toi_da:
        time.sleep(0.1)
        if cau.dang_noi:
            continue
        if cau.muc() > nguong:
            da_noi, im_tu = True, None
        elif da_noi:
            im_tu = im_tu or time.time()
            if time.time() - im_tu >= im_can:
                return "xong"
        elif time.time() - t0 > 9:
            return "khong_noi"
    return "het_gio"


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("so", help="số của SIM trong máy khách")
    ap.add_argument("--may-khach", required=True)
    ap.add_argument("--may-ai", default="21f10e44220c7ece", help="serial máy AI, để cúp khi dọn")
    ap.add_argument("--giong-khach", default="giong_nam")
    ap.add_argument("--giong-ai", default="default")
    ap.add_argument("--san-pham", default="vay tín chấp")
    ap.add_argument("--port", type=int, default=8124)
    a = ap.parse_args()
    s2 = a.may_khach
    # Chốt chặn cứng: dù script kẹt ở đâu, sau 4 phút cả hai máy bị cúp.
    def _chot():
        import subprocess
        for s in (a.may_ai, s2):
            subprocess.run(["adb", "-s", s, "shell", "input", "keyevent", "6"], capture_output=True)
        print("   CHỐT CHẶN 4 PHÚT: đã cúp cả hai máy", flush=True)
        import os
        os._exit(4)
    chot = threading.Timer(240, _chot)
    chot.daemon = True      # không giữ tiến trình sống sau khi chạy xong
    chot.start()

    print("1. Dựng tiếng câu hỏi của khách ...")
    tieng = [dung_tieng(c, a.giong_khach) for c in CAU_HOI]
    print(f"   {len(tieng)} câu, dài {sum(len(t) for t in tieng) / 2 / RATE:.1f}s")

    ds = api("/api/phones/contacts?limit=500").get("contacts", [])
    lh = next((c for c in ds if c["phone"].strip() == a.so), None)
    if lh is None:
        ra = api("/api/phones/contacts", {"name": "Máy khách phone farm", "phone": a.so,
                                          "product": a.san_pham})
        lh = ra.get("contact") or ra
    cid = lh["contact_id"]

    print("2. Máy AI quay số qua đường sản phẩm ...")
    ra = api(f"/api/phones/contacts/{cid}/call", {"voice_name": a.giong_ai})
    if ra.get("error"):
        print("   LỖI:", ra["error"])
        return 1
    sid = ra.get("session_id") or (ra.get("session") or {}).get("session_id", "")
    print(f"   quay {ra.get('dialed')} | tiếng: {ra.get('tieng')} {ra.get('canh_bao') or ''} | phiên {sid}")

    cau = None
    try:
        print("3. Chờ máy khách đổ chuông ...")
        t0 = time.time()
        while time.time() - t0 < 45:
            tt, _ = await ad.call_state(s2)
            if tt == "ringing":
                break
            await asyncio.sleep(1)
        else:
            print("   Máy khách KHÔNG đổ chuông sau 45s: sai số, hết tiền, hoặc mất sóng.")
            return 2
        print(f"   đổ chuông sau {time.time() - t0:.0f}s")
        # Bấm bắt máy có lúc không ăn (màn hình cuộc gọi đến chưa kịp hiện):
        # bấm lại tới khi máy thật sự sang "đang nói chuyện".
        await asyncio.sleep(1.5)
        for lan in range(6):
            await ad.answer(s2)
            await asyncio.sleep(1.0)
            if (await ad.precise_call_state(s2))[0] == 1:
                break
        else:
            print("   Máy khách KHÔNG bắt được máy sau 6 lần bấm.")
            return 3
        print(f"   bắt máy sau {lan + 1} lần bấm")
        print("   cầu tiếng:", await ad.start_bridge(s2, port=a.port))
        print("   tiêm đường lên:", (await ad.set_uplink_injection(s2, True))[1])
        cau = CauKhach(a.port)
        await asyncio.sleep(1.0)
        nen = cau.muc(0.5)
        print(f"4. Vào cuộc. Mức nền phía khách {nen:.0f}. Chờ AI chào ...")
        print("   lời chào:", cho_ben_kia_noi_xong(cau, nen, 25))
        moc = []
        for cau_hoi, pcm in zip(CAU_HOI, tieng):
            if (await ad.call_state(s2))[0] == "idle":
                print("   cuộc gọi đã kết thúc sớm.")
                break
            t_hoi = time.time()
            cau.noi(pcm)
            # CÓ HẠN CHỜ: cầu tiếng máy khách đứt thì luồng gửi chết, cờ
            # `dang_noi` kẹt mãi và vòng này không bao giờ thoát - cuộc gọi treo
            # 9 phút (08-10-2026), tốn cước ngoại mạng. Quá hạn là bỏ cuộc.
            han = time.time() + len(pcm) / 2 / RATE + 8
            while cau.dang_noi or len(cau.cho_gui) >= KHUNG:
                if time.time() > han:
                    raise RuntimeError("cầu tiếng máy khách đứng - dừng cuộc gọi")
                await asyncio.sleep(0.05)
            t_dut = time.time()
            kq = await asyncio.to_thread(cho_ben_kia_noi_xong, cau, nen, 30)
            moc.append((cau_hoi, t_dut - t_hoi, time.time() - t_dut, kq))
            print(f"   KHÁCH: {cau_hoi}  -> AI {kq} sau {time.time() - t_dut:.1f}s")
            await asyncio.sleep(0.8)
    except Exception as e:
        print("   DỪNG SỚM:", e)
    finally:
        print("5. Dọn: cúp máy, trả micro, tắt cầu ...")
        try:
            # Cúp CẢ HAI đầu: chỉ cúp máy khách thì máy AI có khi vẫn giữ cuộc.
            await ad.hangup(a.may_ai) if getattr(a, "may_ai", "") else None
            await ad.hangup(s2)
            await ad.set_uplink_injection(s2, False)
            await ad.stop_bridge(s2, port=a.port)
        except Exception as e:
            print("   lỗi khi dọn:", e)
        try:
            api(f"/api/phones/contacts/{cid}/result", {"status": "done"})
        except Exception as e:
            print("   không đóng được phiên phía AI:", e)

    if cau is not None:
        cau.dong()
        out = Path("data/tu_goi")
        out.mkdir(parents=True, exist_ok=True)
        f = out / (time.strftime("%Y%m%d_%H%M%S") + ".wav")
        with wave.open(str(f), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(bytes(cau.thu))
        print(f"   bản thu phía khách: {f} ({len(cau.thu) / 2 / RATE:.0f}s)")

    await asyncio.sleep(3)
    print("\n6. Phía AI đã nghe và đáp:")
    phien = api(f"/api/sessions/{sid}").get("session", {}) if sid else {}
    log = [m for m in phien.get("latency_log", []) if isinstance(m, dict)]
    i = 0
    for m in phien.get("history", []):
        if m.get("role") == "user":
            print(f"   AI NGHE: {m.get('content', '')}")
        else:
            met = log[i] if i < len(log) else {}
            i += 1
            route = met.get("answer_route", {})
            print(f"   AI ĐÁP : {m.get('content', '')[:150]}")
            if met:
                print(f"            [{route.get('mode')}/{route.get('reason')}] im lặng "
                      f"{met.get('im_lang_ms')}ms, ttfa {met.get('ttfa_ms')}ms, stt {met.get('stt_ms')}ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
