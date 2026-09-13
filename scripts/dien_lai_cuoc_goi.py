"""Diễn lại một cuộc gọi THẬT bằng chính tiếng khách trong bản ghi, không cần gọi ai.

Đưa kênh khách của file .opus vào ĐÚNG `PhoneCallBridge._read_loop` + `StreamingPipeline`
thật, theo thời gian thực, nên chạm được cả VAD, đoán trước, câu đệm, STT, RAG, LLM.
Dùng để đối chứng một thay đổi ở tầng nghe mà không phải nhờ người cầm máy.

    .venv\\python.exe scripts\\dien_lai_cuoc_goi.py data\\recordings\\2026-09-07\\08c0d3e0.opus 17.2

Tham số 2 là GIÂY BẮT MÁY trong file. BẮT BUỘC phải có và phải đúng:

  Cuộc thật chỉ mở micro sau khi người kia bấm nghe (`bridge.tam_dung_nghe`), nên
  đưa cả file vào là cho VAD nghe luôn TIẾNG CHUÔNG CHỜ. Chuông to hơn hẳn lời nói
  (đo được đỉnh 16503 so với 1000-3000), VAD mở lượt trên nó, `muc_khach` bị đặt
  theo mức đó, rồi `_nguong_theo_khach` đội ngưỡng mở lượt lên chạm trần 2000 và
  chặn sạch lời khách thật. Bản chạy sai kiểu này ra ÍT lượt hơn cuộc thật, và các
  lượt đầu cách nhau đúng nhịp chuông ~5 giây.

  Tìm mốc bắt máy: so dòng `đã chào` trong `logs/backend.log` với cụm tiếng đầu
  tiên của kênh AI (kênh PHẢI) trong bản ghi.

Cách kiểm bản diễn lại có ĐÚNG không: chạy với tham số CŨ trước, số lượt phải khớp
số lượt của cuộc thật trong DB. Khớp rồi mới tin nó ở tham số mới.

Cần PhoWhisper (:8178) và Ollama đang chạy. Nên DỪNG backend (:8100) trước để khỏi
tranh VRAM với F5 - script này tự nạp F5 của nó.
"""
import asyncio
import os
import sys
import time

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backend.services.phone_call_service as pcs  # noqa: E402
from backend.pipeline.session_manager import CallSession  # noqa: E402
from backend.pipeline.streaming_pipeline import StreamingPipeline  # noqa: E402
from backend.services.phone_call_service import FRAME_BYTES_LEN, PhoneCallBridge  # noqa: E402


class ReaderBanGhi:
    """Phát khung theo THỜI GIAN THỰC. Nhanh hơn thực là hỏng phép đo: câu đệm,
    đoán trước và TTFA đều tính theo đồng hồ tường."""

    def __init__(self, khung, bridge):
        self.khung, self.i, self.bridge = khung, 0, bridge
        self.t0 = None

    async def readexactly(self, n):
        if self.t0 is None:
            self.t0 = time.perf_counter()
        if self.i >= len(self.khung):
            self.bridge.running = False
            raise asyncio.IncompleteReadError(b"", n)
        den_han = self.t0 + self.i * 0.02
        cho = den_han - time.perf_counter()
        if cho > 0:
            await asyncio.sleep(cho)
        f = self.khung[self.i]
        self.i += 1
        return f

    @property
    def giay(self):
        return self.i * 0.02


async def chay(duong_dan, t_bat_may, voice, product, scenario_id):
    from backend.services.llm_service import LLMService
    from backend.services.rag_service import RAGService
    from backend.services.stt_service import STTService
    from backend.services.tts_service import F5TTSService

    from backend.config import settings
    from backend.models.db import init_db
    from backend.services.filler_situation import chuan_hoa
    from backend.services.filler_store import MA_NHOM_CHUNG, lay_kho

    print("Đang nạp dịch vụ...", flush=True)
    # Ba việc dưới đây là của `core/startup`. Thiếu bất kỳ việc nào thì lượt vẫn
    # MỞ được nhưng chết ở `_send_filler`, và bản diễn lại chỉ còn đo được tầng
    # nghe - đúng lỗi đã mắc lần chạy đầu:
    #   init_db      thiếu -> `lay_kho()` ném LoiKho, MỌI lượt lỗi, không câu nào ra
    #   kho_vector   thiếu -> "tình huống: bỏ - kho_vector=KHÔNG", câu đệm rơi rổ chung
    #   dung_fillers thiếu -> không có clip nào để phát
    await init_db(settings.db_file)
    stt, llm, rag, tts = STTService(), LLMService(), RAGService(), F5TTSService()
    rag.load()
    # NẠP LẠI tri thức: `rag.load()` chỉ mở kho vector đã có, không đọc
    # lại thư mục. Sửa file trong `knowledge/` mà bỏ bước này thì bản diễn
    # lại vẫn chạy trên mảnh CŨ và mọi kết luận về sửa tri thức đều sai.
    rag.ingest_directory("./knowledge")
    tts.load()
    # Backend thật hâm các hình dạng tensor lúc khởi động và hâm cả hai nhánh
    # LLM trong lúc điện thoại còn đổ chuông. Bản diễn lại bắt đầu thẳng từ lúc
    # bắt máy; thiếu hai bước này làm lượt 1 trả giá nguội 2-4 giây mà cuộc gọi
    # thật không phải trả, khiến phép so trước/sau sai ngay từ đầu.
    await tts.ham_nong_hinh_dang()
    async for _ in llm.stream_response(
            [{"role": "user", "content": "xin chào"}], "Trả lời đúng một từ."):
        break
    from backend.pipeline.cong_cu_llm import ham_luot_quyet_dinh
    await ham_luot_quyet_dinh(llm)
    await tts.dung_fillers(lay_kho())

    from backend.main import app_state
    kho = lay_kho()
    app_state.kho_vector = {
        t.id: chuan_hoa(rag.embed(list(t.vi_du)))
        for t in kho.tinh_huong if t.vi_du and t.id != MA_NHOM_CHUNG
    }
    print(f"Đã nhúng {len(app_state.kho_vector)} tình huống", flush=True)
    # Bảng hỏi-đáp: `core/startup` nạp nó cho backend thật. Thiếu ở đây thì bản
    # diễn lại KHÔNG BAO GIỜ trúng dòng nào - lần diễn lại 11-09 bảng có 4 dòng
    # mà "thủ tục cần những gì" vẫn do mô hình tự nói, và mọi kết luận về bảng
    # (kể cả dòng chê đi theo tình huống) sẽ sai.
    from backend.models import db as _db
    from backend.services.bang_hoi_dap import doc_dong
    dong = doc_dong(_db.connection())
    app_state.hoi_dap = {d["id"]: d for d in dong}
    app_state.hoi_dap_vector = {d["id"]: chuan_hoa(rag.embed(list(d["cau_hoi"])))
                                for d in dong if d["cau_hoi"]}
    print(f"Đã nhúng {len(app_state.hoi_dap_vector)} dòng hỏi-đáp", flush=True)

    pipeline = StreamingPipeline(stt=stt, llm=llm, tts=tts, rag=rag)

    x, sr = sf.read(duong_dan, always_2d=True)
    kh = x[int(t_bat_may * sr):, 0]          # kênh TRÁI = khách
    import scipy.signal as ss
    kh = ss.resample_poly(kh, pcs.RATE_LEN, sr)
    n16 = (np.clip(kh, -1, 1) * 32767).astype(np.int16)
    mau = FRAME_BYTES_LEN // 2
    khung = [n16[i:i + mau].tobytes() for i in range(0, len(n16) - mau, mau)]
    print(f"{len(khung)} khung = {len(khung) * 0.02:.0f}s tiếng khách, "
          f"t=0 là lúc bắt máy\n", flush=True)

    session = CallSession(customer_name="Anh/Chị")
    session.product, session.voice_name = product, voice
    session.scenario_id = scenario_id
    bridge = PhoneCallBridge(pipeline, session, port=0, serial="dienlai")
    reader = ReaderBanGhi(khung, bridge)
    bridge.reader, bridge.running = reader, True
    bridge.tam_dung_nghe = False

    khung_ai: list[tuple[float, bytes]] = []   # (giây phát, khung)

    async def don_hang_doi():
        """Đóng vai `_write_loop`: rút hàng đợi ĐÚNG NHỊP 20ms/khung và ghi lại
        MỐC THỜI GIAN của từng khung.

        Phải phát theo nhịp chứ không rút sạch: TTS đẻ nhanh hơn phát ~3,5 lần
        nên khung vào hàng đợi thành từng cụm giật cục. Rút sạch rồi nối lại là
        được một file tiếng AI liền tù tì, nhanh hơn thực, KHÔNG có quãng chờ -
        nghe không ra được gì và rất dễ tưởng máy đang nhanh. (Đã mắc: bản đầu
        ghi kiểu đó, người dùng mở lên chỉ thấy giọng AI nói liên tục.)

        Mốc thời gian để dựng lại file HAI KÊNH đúng nhịp cuộc gọi - xem cuối hàm.
        """
        t_phat: float | None = None
        while bridge.running:
            try:
                f = await asyncio.wait_for(bridge._out.get(), timeout=0.5)
            except (asyncio.TimeoutError, Exception):
                continue
            if not f:
                continue
            now = time.perf_counter() - (reader.t0 or time.perf_counter())
            # Nghỉ quá 0,5s coi như lượt mới: bắt nhịp lại từ lúc khung tới,
            # đúng cách `_write_loop` xử lý (RESET_GAP).
            if t_phat is None or now > t_phat + 0.5:
                t_phat = now
            khung_ai.append((t_phat, f))
            t_phat += 0.02
            cho = (reader.t0 + t_phat) - time.perf_counter()
            if cho > 0:
                await asyncio.sleep(cho)

    don = asyncio.create_task(don_hang_doi())
    try:
        await bridge._read_loop()
    finally:
        don.cancel()

    if khung_ai:
        # File HAI KÊNH đúng nhịp cuộc gọi: trái = khách (chính tiếng đã đưa
        # vào), phải = AI (đặt theo mốc phát). Giống hệt bố cục bản ghi thật nên
        # nghe lại là so được trực tiếp.
        import wave
        SR = pcs.RATE_XUONG
        import scipy.signal as _ss
        kh8 = _ss.resample_poly(kh, SR, pcs.RATE_LEN)
        n = max(len(kh8), int((khung_ai[-1][0] + 0.02) * SR) + 1)
        trai = np.zeros(n, dtype=np.float32)
        trai[:len(kh8)] = np.clip(kh8, -1, 1) * 32767
        phai = np.zeros(n, dtype=np.float32)
        for t, f in khung_ai:
            a = np.frombuffer(f, dtype=np.int16).astype(np.float32)
            i = int(t * SR)
            phai[i:i + len(a)] = a[:max(0, n - i)]
        # Cân mức hai kênh cho dễ nghe; KHÔNG dùng file này để đo mức.
        for k in (trai, phai):
            d = np.abs(k).max()
            if d > 0:
                k *= 9000.0 / d
        ra = os.path.join("logs", "dien_lai_2_kenh.wav")
        with wave.open(ra, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(np.clip(np.stack([trai, phai], axis=1), -32768, 32767)
                          .astype(np.int16).tobytes())
        print(f"\nHai kênh (trái=khách, phải=AI): {ra} ({n / SR:.1f}s)")

    print("\n===== HỘI THOẠI DIỄN LẠI =====")
    for t in session.history:
        vai = "KHÁCH" if t["role"] == "user" else "AI   "
        print(f"  {vai}: {t['content']}")
    print(f"\n{bridge.turns} lượt mở. Độ trễ từng lượt:")
    for m in session.latency_log:
        print(f"  TTFA {m.get('ttfa_ms', 0):5.0f}ms  tổng {m.get('total_ms', 0):5.0f}ms  "
              f"tình huống={m.get('tinh_huong_id') or '-'}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    asyncio.run(chay(
        sys.argv[1], float(sys.argv[2]),
        voice=sys.argv[3] if len(sys.argv) > 3 else "heu_a6_35",
        product=sys.argv[4] if len(sys.argv) > 4 else "",
        scenario_id=sys.argv[5] if len(sys.argv) > 5 else "sc_nganhang",
    ))
