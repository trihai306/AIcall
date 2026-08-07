"""Kiểm cắt lời + ghép câu trên ĐƯỜNG ĐIỆN THOẠI, không cần SIM hay máy thật.

Dựng một "điện thoại giả": mở cổng TCP 8123 đúng như app Voice Bridge, nói PCM
8kHz vào đó và nghe tiếng AI đi ra. PhoneCallBridge nối vào như nối máy thật nên
toàn bộ đường đi được kiểm - VAD tự cắt lượt, huỷ lượt khi bị chen ngang, ghép
câu, vuốt tiếng. Chỉ khâu ALSA/VSS trên máy Android là không có ở đây.

Kịch bản y như gọi điện:
  1. Khách nói "Cho em hỏi"        -> AI bắt đầu trả lời
  2. Khách NÓI ĐÈ LÊN "lãi suất vay tín chấp bao nhiêu"
  3. AI phải im ngay, bỏ câu trả lời dở, ghép hai vế rồi trả lời một lần

    python scripts/phone_cat_loi.py
"""

import asyncio
import io
import sys
import time
import wave
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

# Lấy thẳng từ dịch vụ thật, đừng chép lại số: hai chiều có tần số riêng và
# script này đóng vai điện thoại nên phải khớp cả hai, lệch là sai tốc độ tiếng.
from backend.services.phone_call_service import (          # noqa: E402
    FRAME_BYTES_LEN, FRAME_BYTES_XUONG, RATE_LEN,
)

FRAME_MS = 20
SILENCE_END_MS = 700   # phải khớp với hằng số trong phone_call_service


def wav_len(b: bytes) -> bytes:
    """WAV 24kHz của TTS -> PCM thô ở RATE_LEN, đúng thứ điện thoại gửi lên."""
    import numpy as np

    with wave.open(io.BytesIO(b)) as w:
        sr = w.getframerate()
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    n = int(len(pcm) / sr * RATE_LEN)
    return np.interp(np.linspace(0, len(pcm) - 1, n),
                     np.arange(len(pcm)), pcm).astype(np.int16).tobytes()


class DienThoaiGia:
    """Đóng vai app Voice Bridge: mở cổng, nhận tiếng AI, phát tiếng khách."""

    def __init__(self, port=8123):
        self.port = port
        self.server = None
        self.reader = self.writer = None
        self.da_noi = asyncio.Event()
        self.khung_nhan = []          # (thời điểm ms, khung) tiếng AI nhận được
        self.t0 = None
        self._im = b"\x00" * FRAME_BYTES_LEN

    async def start(self):
        self.server = await asyncio.start_server(self._on_conn, "127.0.0.1", self.port)
        self.t0 = time.perf_counter()

    async def _on_conn(self, r, w):
        self.reader, self.writer = r, w
        self.da_noi.set()
        try:
            while True:
                f = await r.readexactly(FRAME_BYTES_XUONG)
                self.khung_nhan.append((round((time.perf_counter() - self.t0) * 1000), f))
        except Exception:
            pass

    async def noi(self, pcm: bytes, thoi_gian_that=True):
        """Phát tiếng khách lên, theo nhịp thời gian thực như micro thật."""
        for i in range(0, len(pcm) - FRAME_BYTES_LEN + 1, FRAME_BYTES_LEN):
            self.writer.write(pcm[i:i + FRAME_BYTES_LEN])
            await self.writer.drain()
            if thoi_gian_that:
                await asyncio.sleep(FRAME_MS / 1000)

    async def im_lang(self, ms: int):
        """Gửi khung im - VAD cần nghe khoảng lặng mới chốt là khách nói xong."""
        for _ in range(ms // FRAME_MS):
            self.writer.write(self._im)
            await self.writer.drain()
            await asyncio.sleep(FRAME_MS / 1000)

    def muc_tieng_AI(self, tu_ms: int) -> int:
        """Số khung tiếng AI (không phải khung im) nhận được sau mốc tu_ms."""
        import numpy as np
        n = 0
        for t, f in self.khung_nhan:
            if t < tu_ms:
                continue
            a = np.frombuffer(f, dtype=np.int16).astype(np.float32)
            if np.sqrt((a * a).mean()) > 100:
                n += 1
        return n

    async def stop(self):
        if self.writer:
            self.writer.close()
        if self.server:
            self.server.close()
            await self.server.wait_closed()


async def main() -> int:
    from backend.config import settings
    from backend.pipeline.session_manager import CallSession
    from backend.services.llm_service import LLMService
    from backend.services.phone_call_service import PhoneCallBridge
    from backend.services.rag_service import RAGService
    from backend.services.stt_service import STTService
    from backend.services.tts_service import F5TTSService
    from backend.pipeline.streaming_pipeline import StreamingPipeline

    from backend.services.filler_store import lay_kho

    print("Nạp model ...")
    stt, llm, tts, rag = STTService(), LLMService(), F5TTSService(), RAGService()
    tts.load()
    # Backend thật làm bước này lúc khởi động. Bỏ qua thì filler rỗng và khách
    # phải nghe cả giây im lặng - lần đầu chạy test tôi tưởng đó là lỗi sản phẩm.
    await tts.dung_fillers(lay_kho().cau)
    rag.load()
    pipeline = StreamingPipeline(stt=stt, llm=llm, tts=tts, rag=rag)

    VE1, VE2 = "Cho em hỏi", "lãi suất vay tín chấp bao nhiêu"
    print(f"Sinh giọng khách: {VE1!r} / {VE2!r}")
    a1 = wav_len(await tts.synthesize(VE1, use_cache=False))
    a2 = wav_len(await tts.synthesize(VE2, use_cache=False))

    dt = DienThoaiGia()
    await dt.start()
    session = CallSession(customer_name="Khách thử")
    bridge = PhoneCallBridge(pipeline, session, port=dt.port)
    await bridge.start()
    await asyncio.wait_for(dt.da_noi.wait(), 5)
    print("Điện thoại giả đã nối vào cầu tiếng\n")

    print(f"[1] Khách nói: {VE1!r}")
    await dt.noi(a1)
    t_dut_loi = round((time.perf_counter() - dt.t0) * 1000)
    await dt.im_lang(900)          # đủ dài để VAD chốt lượt

    print("[2] Chờ AI bắt đầu nói ...")
    for _ in range(120):
        if dt.muc_tieng_AI(0) > 0:
            break
        await dt.im_lang(100)
    t_tieng_dau = next((t for t, _ in dt.khung_nhan), None)
    print(f"    nhận được {dt.muc_tieng_AI(0)} khung tiếng AI")
    if t_tieng_dau is not None:
        # Đường thoại phải chờ VAD chốt im lặng (700ms) rồi mới xử lý, khác
        # trình duyệt (khách tự bấm nút). Con số này gồm cả khoản đó.
        print(f"    khách chờ {t_tieng_dau - t_dut_loi}ms từ lúc dứt lời"
              f" (trong đó {SILENCE_END_MS}ms là VAD đợi xem đã nói xong chưa)")

    moc_cat = round((time.perf_counter() - dt.t0) * 1000)
    print(f"[3] Khách NÓI ĐÈ LÊN: {VE2!r}")
    await dt.noi(a2)
    await dt.im_lang(900)

    print("[4] Chờ câu trả lời cho ý đã ghép ...")
    for _ in range(150):
        await dt.im_lang(100)
        if session.history and session.history[-1]["role"] == "assistant":
            break

    await bridge.stop()
    await dt.stop()

    # --- chấm điểm ---------------------------------------------------------
    print("\n" + "=" * 68)
    dat = True

    def kiem(mo_ta, dk, them=""):
        nonlocal dat
        dat &= bool(dk)
        print(("  ĐẠT  " if dk else "  TRẬT ") + mo_ta + (f"  {them}" if them else ""))

    cau_khach = [h["content"] for h in session.history if h["role"] == "user"]
    tra_loi = [h["content"] for h in session.history if h["role"] == "assistant"]

    def gon(s):
        return " ".join("".join(c for c in s.lower() if c.isalnum() or c.isspace()).split())

    kiem("chỉ còn MỘT lượt của khách trong lịch sử", len(cau_khach) == 1,
         f"({len(cau_khach)} lượt: {cau_khach})")
    mong = f"{VE1} {VE2}"
    thuc = cau_khach[-1] if cau_khach else ""
    kiem("hai vế đã ghép thành một ý", gon(thuc) == gon(mong),
         f"\n         mong đợi: {mong!r}\n         nhận được: {thuc!r}")
    kiem("chỉ trả lời MỘT lần", len(tra_loi) == 1, f"({len(tra_loi)} câu)")
    if tra_loi:
        print(f"\n  AI trả lời: {tra_loi[-1]}")

    print("=" * 68)
    print("=> " + ("TẤT CẢ ĐẠT" if dat else "CÓ MỤC TRẬT"))
    return 0 if dat else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
