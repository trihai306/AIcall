import asyncio
import base64
import logging
import random
import time

from fastapi import WebSocket

from backend.config import settings
from backend.models.db import save_session
from backend.pipeline.session_manager import CallSession
from backend.pipeline import cong_cu_llm
from backend.pipeline.luot_thuong_gap import tra_loi_san
from backend.pipeline.tra_loi_ho_so import tra_loi as tra_loi_ho_so
from backend.pipeline.text_chunker import nhip_nghi_sau, should_flush
from backend.pipeline.text_normalizer import (BotLichSu, bo_cau_lui_thua,
                                              chan_so_sai, chan_tien_sai,
                                              sua_xung_ho)
from backend.services.audio_utils import chen_lang_dau_wav
from backend.services.stt_service import STTService
from backend.services.llm_service import LLMService
from backend.services.tts_service import F5TTSService
from backend.services.rag_service import RAGService
from backend.services.filler_store import lay_kho
from backend.core.logging_config import Timer

logger = logging.getLogger(__name__)

# Strong refs to in-flight background writes: asyncio only holds a weak
# reference to a task, so an unreferenced one can be collected mid-write.
_bg_writes: set[asyncio.Task] = set()


async def _persist_turn(session: CallSession):
    try:
        await save_session(session)
    except Exception as e:
        # A failed write must never break a live call.
        logger.warning(f"DB write failed (non-fatal): {e}")


def _ghep_ngu_canh(session, rag_context: str) -> str:
    """Ghép hồ sơ khách tra được (nếu có) vào ngữ cảnh tham khảo.

    Đặt TRƯỚC phần RAG chung: đây là số liệu của đúng khách đang nghe máy, nên
    khi có mâu thuẫn thì nó phải là thứ mô hình đọc trước. Xem
    services/data_source_service.py, chế độ "lookup".
    """
    rieng = getattr(session, "ngu_canh_khach", "")
    if not rieng:
        return rag_context
    return f"{rieng}\n\n{rag_context}" if rag_context else rieng


def _ghep_uu_tien(du_lieu_cong_cu: str, ngu_canh: str) -> str:
    """Xếp dữ liệu vừa tra lên TRƯỚC và nói rõ thứ tự ưu tiên.

    Xếp trước thôi là KHÔNG ĐỦ - đã đo: khách hỏi "anh còn nợ bao nhiêu", hồ sơ
    ghi dư nợ 142.500.000 mà mô hình trả lời "vay tối đa 500 triệu" (hạn mức
    trong tài liệu sản phẩm). Cùng loại lỗi hai-con-số-cạnh-tranh đã phải chữa
    ở `_loc_theo_san_pham`: hai số cùng đơn vị tiền trong ngữ cảnh là mô hình
    chọn bừa.

    Dùng CHUNG cho cả đường chính lẫn đường nghĩ-sẵn. Hai chỗ dựng ngữ cảnh khác
    nhau thì bản nghĩ sẵn và bản sinh thật nói hai kiểu, mà `_answer_hit` chỉ so
    câu HỎI nên không phát hiện được.
    """
    if not du_lieu_cong_cu:
        return ngu_canh
    ra = ("DỮ LIỆU VỪA TRA CHO ĐÚNG CÂU HỎI NÀY (ưu tiên TUYỆT ĐỐI, "
          "dùng số ở đây trước mọi nguồn khác):\n" + du_lieu_cong_cu)
    if ngu_canh:
        ra += f"\n\nTHÔNG TIN CHUNG (chỉ dùng khi phần trên không có):\n{ngu_canh}"
    return ra


def _schedule_persist(session: CallSession):
    """Fire-and-forget the DB write so it stays off the latency path."""
    task = asyncio.create_task(_persist_turn(session))
    _bg_writes.add(task)
    task.add_done_callback(_bg_writes.discard)


class StreamingPipeline:
    """Orchestrates the full voice AI pipeline with graceful degradation."""

    def __init__(self, stt: STTService, llm: LLMService, tts: F5TTSService, rag: RAGService):
        self.stt = stt
        self.llm = llm
        self.tts = tts
        self.rag = rag
        self._da_bao_tts_chet = False

    @property
    def _tts_available(self) -> bool:
        return self.tts._is_loaded

    @staticmethod
    def _toc_cho_phien(tts, session, voice: str | None) -> float | None:
        """Tốc đọc cho phiên này: tốc của giọng, nhân hệ số nếu là cuộc gọi.

        Phân biệt bằng `session.audio_rate` - 8000 là đường thoại, 16000 là
        trình duyệt. Đó là mốc sẵn có và luôn đúng, không phải cờ tự đặt thêm.
        """
        try:
            goc = tts.toc_do_cua(voice)
            if getattr(session, "audio_rate", 16000) <= 8000:
                return goc * tts.he_so_thoai()
            return goc
        except Exception:
            return None

    async def _try_synthesize(self, text: str, fast: bool = False, voice: str | None = None,
                              session=None) -> bytes | None:
        if not self._tts_available:
            # Trả None lặng lẽ ở đây từng làm mất hàng chục phút truy lỗi: TTS nạp
            # hỏng lúc khởi động thì mọi lượt sau đều câm, log không một dòng, giao
            # diện chỉ hiện "không có tiếng" mà không nói vì sao. Kêu MỘT lần cho
            # mỗi lần model chết, không kêu mỗi mảnh - một lượt có 3-5 mảnh.
            if not self._da_bao_tts_chet:
                self._da_bao_tts_chet = True
                logger.error(
                    "TTS CHƯA NẠP ĐƯỢC - toàn bộ lượt sau sẽ KHÔNG CÓ TIẾNG. "
                    "Xem dòng '[6/6] Loading F5-TTS' trong log khởi động để biết lý do."
                )
            return None
        self._da_bao_tts_chet = False
        try:
            toc = self._toc_cho_phien(self.tts, session, voice) if session is not None else None
            return await self.tts.synthesize(text, fast=fast, voice=voice, speed=toc)
        except Exception as e:
            logger.warning(f"TTS failed: {e}")
            return None

    # --- Đoán trước trong lúc khách còn đang nói ------------------------------
    # Đặt theo THỜI GIAN, không theo số byte. Đệm của phiên mang tần số riêng
    # (`CallSession.audio_rate`): trình duyệt 16kHz, đường thoại 8kHz. Chốt cứng
    # theo byte của 16kHz thì đường thoại chạy đúng NỬA nhịp mà không báo lỗi gì
    # - đã mắc đúng lỗi này khi bỏ khâu đổi tần: mốc bắt đầu thành 2.5s và nhịp
    # đoán thành 0.8s, tức lặng lẽ quay về đúng cấu hình đã cố ý bỏ.
    # Hạ 1250 -> 600 (07-08). Đo trên cuộc gọi thật: khách nói 2380ms và
    # **1020ms**. Lượt 1020ms NGẮN HƠN CẢ NGƯỠNG KHỞI ĐỘNG nên không được đoán
    # lần nào, trả đủ tiền STT+RAG+LLM trên đường găng. Câu thoại bán hàng thật
    # ngắn hơn hẳn giả định cũ, nên ngưỡng phải xuống theo.
    _SPEC_MIN_MS = 600       # ngắn hơn thì phiên âm chưa ra gì
    # Đoán lại sau mỗi ~0.4s tiếng mới (trước là 0.8s). Nhịp thưa làm bản đoán
    # lỗi thời đúng lúc cần nhất: khách dứt lời khi bản đoán đã cũ 0.7s thì nó
    # thiếu mấy từ cuối, `_answer_hit` trượt, và phải sinh lại từ đầu.
    # Tốn thêm GPU nhưng đúng lúc khách đang nói - lúc đó TTS không chạy.
    _SPEC_STEP_MS = 400

    @staticmethod
    def _byte_cho_ms(session: CallSession, ms: int) -> int:
        """Số byte PCM 16-bit mono ứng với `ms` mili giây tiếng trong đệm phiên."""
        return session.audio_rate * 2 * ms // 1000

    @staticmethod
    def _truy_van_rag(text: str, session: CallSession) -> str:
        """Ghép sản phẩm đang tư vấn vào câu truy vấn RAG.

        Vì sao cần: truy vấn chỉ bằng lời khách thì câu méo hoặc câu cụt kéo về
        nhầm sản phẩm. Đo trên cuộc gọi thật: khách hỏi "cho anh thông tin căn
        cước" trong lúc đang tư vấn VAY TÍN CHẤP, RAG lại lấy về "Miễn phí thường
        niên cho tất cả loại thẻ" - tài liệu THẺ TÍN DỤNG. Trả lời theo đó là tư
        vấn sai sản phẩm.

        Kênh thoại 8kHz cho phiên âm sai nhiều, nên chỗ dựa duy nhất còn chắc
        chắn là sản phẩm của phiên - ghép nó vào để neo truy vấn.
        """
        sp = (getattr(session, "product", "") or "").strip()
        return f"{sp} {text}".strip() if sp else text

    async def speculate(self, session: CallSession, ngay: bool = False):
        """Phiên âm tạm + nạp sẵn ngữ cảnh RAG khi khách còn đang nói.

        Chỉ làm phần AN TOÀN: kết quả chỉ được dùng lại nếu phiên âm cuối cùng
        thật sự bắt đầu bằng phiên âm tạm. Đoán trượt thì bỏ, chạy lại như thường
        - không bao giờ trả lời khách bằng nội dung đoán chưa xác nhận.
        Lúc này TTS đang rảnh nên GPU trống, đoán trước gần như miễn phí.

        `ngay=True`: khách VỪA NGỪNG TIẾNG, bỏ qua mọi ngưỡng nhịp và huỷ bản
        đang chạy dở để đoán lại trên TOÀN BỘ câu. Đây là lần đoán giá trị nhất
        của cả lượt - audio đã đủ cả câu nên `_answer_hit` gần như chắc trúng,
        khác hẳn những lần giữa chừng vốn chỉ có câu cụt. Xem `_read_loop`.
        """
        n = session.audio_len()
        if session.spec_running:
            if not ngay:
                return
            # Bản giữa chừng đang chạy đã lỗi thời (nó chỉ thấy câu cụt). Huỷ để
            # nhường chỗ. KHÔNG await ở đây - vòng thu tiếng không được nghẽn;
            # bản bị huỷ chưa kịp ghi gì vào phiên vì nó chỉ ghi ở bước cuối.
            if session.spec_task is not None and not session.spec_task.done():
                session.spec_task.cancel()
            session.spec_running = False
        elif n < self._byte_cho_ms(session, self._SPEC_MIN_MS):
            return
        if not ngay and n - session.spec_bytes < self._byte_cho_ms(
                session, self._SPEC_STEP_MS):
            return

        # Khách nói tiếp thì bản nghĩ cũ đã lỗi thời -> huỷ, nghĩ lại từ nội dung mới.
        if session.spec_task is not None and not session.spec_task.done():
            session.spec_task.cancel()

        session.spec_running = True
        session.spec_bytes = n
        audio = session.peek_audio()
        history = list(session.history)          # chụp lại, tránh đọc lúc đang đổi

        async def _run():
            try:
                text = (await self.stt.transcribe(
                    audio, sample_rate=session.audio_rate)).strip()
                # Cất NGAY sau STT, trước mọi bước sau. Hai lý do: (1) đây là
                # khoản đắt nhất còn cắt được khỏi đường găng (212-502ms mỗi
                # lượt), (2) nếu RAG hay LLM bên dưới hỏng/bị huỷ thì phần phiên
                # âm vẫn dùng được - cất ở cuối là mất trắng.
                session.spec_stt = (n, text)
                if len(text) < 4:
                    return
                rag = ""
                try:
                    rag = await self.rag.retrieve(self._truy_van_rag(text, session), top_k=2,
                                                  san_pham=session.product)
                except Exception as e:
                    logger.debug(f"RAG đoán trước lỗi (bỏ qua): {e}")

                # LLM SOẠN SẴN CÂU TRẢ LỜI - chỉ ra chữ, TUYỆT ĐỐI KHÔNG gọi TTS.
                # Chưa có tiếng nào tồn tại nên không thể lỡ phát nhầm; nếu khách
                # nói tiếp thì bản nghĩ này bị huỷ và soạn lại, không mất gì ngoài
                # ít GPU đang rảnh (lúc khách nói thì TTS không chạy).
                # Tra dữ liệu NGAY TẠI ĐÂY, không đợi khách nói xong.
                #
                # Thiếu bước này thì bản nghĩ sẵn được soạn mà KHÔNG có dư nợ /
                # ngày đến hạn - rồi `_answer_hit` (chỉ so câu HỎI, không soi nội
                # dung) cho qua, và khách nghe đúng câu thiếu số. Tức tính năng
                # tra dữ liệu bị vô hiệu đúng ở những lượt chạy nhanh nhất.
                #
                # Đặt ở đây gần như MIỄN PHÍ: lưới từ khoá tốn ~1ms, mà kể cả
                # rơi xuống đường LLM ~419ms thì lúc này khách vẫn đang nói và
                # GPU đang rảnh - không chạm vào đường găng.
                du_lieu = ""
                try:
                    du_lieu = await self._tra_bang_cong_cu(text, session, {})
                except Exception as e:
                    logger.debug(f"Tra dữ liệu khi nghĩ sẵn lỗi (bỏ qua): {e}")

                sys_prompt = self.llm.build_system_prompt(
                    customer_name=session.customer_name,
                    product=session.product,
                    rag_context=_ghep_uu_tien(du_lieu, _ghep_ngu_canh(session, rag)),
                    scenario=getattr(session, "scenario", None),
                    gioi_tinh=getattr(session, "gender", ""),
                    gioi_tinh_do_tin=getattr(session, "gender_do_tin", None),
                )
                msgs = history + [{"role": "user", "content": text}]
                answer = ""
                async for tok in self.llm.stream_response(msgs, sys_prompt):
                    answer += tok

                session.spec_transcript = text
                session.spec_rag = rag
                session.spec_answer = answer.strip()
                logger.info(
                    "Đã nghĩ sẵn [%.1fs] hỏi='%s' -> trả lời %d chữ",
                    n / (session.audio_rate * 2), text[:44], len(session.spec_answer),
                )
            except asyncio.CancelledError:
                logger.debug("Bản nghĩ bị huỷ vì khách nói tiếp")
                raise
            except Exception as e:
                logger.debug(f"Đoán trước lỗi (bỏ qua): {e}")
            finally:
                # CHỈ bản đoán hiện hành mới được hạ cờ. Với `ngay=True` ta huỷ
                # bản cũ rồi dựng bản mới ngay; `finally` của bản cũ chạy SAU đó
                # nên hạ vô điều kiện là xoá nhầm cờ của bản mới, và lần
                # `speculate` kế tiếp tưởng đang rảnh nên huỷ luôn bản mới.
                if session.spec_task is asyncio.current_task():
                    session.spec_running = False

        session.spec_task = asyncio.create_task(_run())

    # --- Nạp sẵn trong lúc khách còn đang GÕ ----------------------------------

    _PREFETCH_MIN_CHARS = 8

    async def prefetch_text(self, text: str, session: CallSession):
        """Chạy trước phần RAG cho câu đang gõ, để lúc bấm gửi khỏi phải chờ.

        RAG nằm nối tiếp NGAY TRƯỚC LLM và ăn 120-171ms mỗi lượt (đo thật trên
        đường chat). Kéo nó ra khỏi đường tới hạn là phần rút ngắn duy nhất ở đây
        không đánh đổi thứ gì.

        CHỈ RAG, KHÔNG gọi LLM. RAG chạy trên CPU (embedding_device="cpu") nên
        không tranh GPU với TTS. Ngược lại, sinh sẵn câu trả lời ở đây là phản
        tác dụng: huỷ đọc stream KHÔNG ngăn được Ollama tính tiếp, GPU bị chiếm
        đẩy TTS mảnh đầu từ ~510ms lên 1258-1434ms - chậm hơn cả không đoán gì.

        Trả về ngay; việc nặng chạy trong task nền. Kết quả chỉ được dùng lại khi
        _spec_hit() xác nhận câu gửi đi đúng là nối tiếp câu đã nạp.
        """
        text = text.strip()
        if len(text) < self._PREFETCH_MIN_CHARS:
            return
        # Khách đang nói thì speculate() mới là chủ của các ô spec_*, đừng giẫm lên.
        if session.spec_running or session.audio_len() > 0:
            return
        if session.spec_transcript == text:
            return                      # đã nạp đúng chuỗi này rồi
        if session.spec_task is not None and not session.spec_task.done():
            session.spec_task.cancel()  # khách gõ thêm -> bản cũ lỗi thời

        session.spec_running = True

        async def _run():
            try:
                rag = await self.rag.retrieve(self._truy_van_rag(text, session),
                                              top_k=2, san_pham=session.product)
                session.spec_transcript = text
                session.spec_rag = rag
                logger.debug("Nạp sẵn RAG lúc khách gõ: '%s'", text[:44])
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.debug(f"Nạp sẵn RAG lỗi (bỏ qua): {e}")
            finally:
                session.spec_running = False

        session.spec_task = asyncio.create_task(_run())

    # Từ đệm cuối câu tiếng Việt: khách nói thêm mấy chữ này thì câu hỏi KHÔNG
    # đổi nghĩa, nên bản đã nghĩ vẫn dùng được. Cố tình để hẹp - "không", "chưa",
    # "gì" đều đổi nghĩa câu hỏi nên KHÔNG có trong danh sách.
    # CHỈ nhận từ đệm cuối câu KHÔNG ĐỔI NGHĨA. Mỗi từ thêm vào đây là một lần
    # nới điều kiện đọc thẳng câu đã soạn cho khách nghe, nên phải xét từng từ.
    #
    # ĐÃ CÂN NHẮC RỒI LOẠI, đừng thêm lại:
    #   "rồi"     - đổi thì: "em vay rồi" (đã vay) khác hẳn "em vay" (muốn vay)
    #   "hả/hở"   - biến câu kể thành câu hỏi
    #   "không"   - phủ định hoặc thành câu hỏi, đổi nghĩa hoàn toàn
    #   "luôn"    - thêm sắc thái tức thì; ranh giới, chưa đủ an toàn
    _TU_DEM_CUOI = {
        "ạ", "à", "á", "nhé", "nha", "nhỉ", "ấy", "đó", "đấy", "thế", "vậy",
        "ừ", "ờ", "ha", "hen", "ạk", "ak",
        # thêm 2026-08-04: từ đáp nhận và tiểu từ diễn ngôn, không mang nội dung
        "vâng", "dạ", "ok", "oke", "okay", "cơ", "mà", "thôi",
    }

    @classmethod
    def _answer_hit(cls, spec: str, final: str) -> bool:
        """Bản trả lời đã soạn sẵn có còn dùng được cho câu hỏi cuối cùng không.

        CHẶT HƠN _spec_hit rất nhiều. _spec_hit chỉ quyết định có dùng lại ngữ
        cảnh RAG hay không - đoán sai thì cùng lắm lấy nhầm tài liệu tham khảo,
        câu hỏi trong prompt vẫn là bản cuối. Còn ở đây là ĐỌC THẲNG cho khách
        nghe, sai là tư vấn sai sản phẩm.

        Điều kiện: phần đã nghĩ phải khớp gần như tuyệt đối với đầu câu cuối, và
        phần khách nói thêm chỉ được là từ đệm cuối câu.
        """
        if not spec or not final:
            return False
        a = spec.lower().split()
        b = final.lower().split()
        if len(a) < 4 or len(b) < len(a):
            return False
        import difflib
        if difflib.SequenceMatcher(None, a, b[: len(a)]).ratio() < 0.85:
            return False
        duoi = b[len(a):]
        if len(duoi) > 3:
            return False
        return all(w.strip(".,!?") in cls._TU_DEM_CUOI for w in duoi)

    @staticmethod
    def _spec_hit(spec: str, final: str) -> bool:
        """Phiên âm cuối có thật sự nối tiếp phiên âm tạm không.

        KHÔNG so khớp tuyệt đối: PhoWhisper giải mã lại toàn bộ audio mỗi lần nên
        chữ đầu có thể đổi giữa hai lần chạy trên CÙNG một đoạn tiếng (đo được:
        "cho tôi hỏi..." -> "trò tôi hỏi..."). So tuyệt đối thì gần như luôn trượt.

        Nới thành so mềm theo từ là AN TOÀN Ở ĐÂY vì thứ được dùng lại chỉ là ngữ
        cảnh RAG - câu hỏi đưa vào prompt vẫn là phiên âm CUỐI. Nếu sau này đoán
        trước cả câu trả lời (mức 3) thì PHẢI quay lại so khớp chặt.
        """
        if not spec or not final:
            return False
        a = spec.lower().split()
        b = final.lower().split()
        if len(a) < 3 or len(b) < len(a):
            return False
        import difflib
        # chỉ so với phần ĐẦU của câu cuối, đúng bằng độ dài phần đã đoán
        ratio = difflib.SequenceMatcher(None, a, b[:len(a)]).ratio()
        return ratio >= 0.75

    # --- Câu đệm mở đầu ------------------------------------------------------
    # Dùng khi chưa có số đo nào của phiên. Đường thoại lớn hơn vì TTFA của nó
    # còn cộng thêm STT.
    # Lượt ĐẦU của mỗi cuộc gọi chưa có số đo nào nên phải dùng con số này. Nâng
    # 1100 -> 1800 (07-08): đo trên 6 lượt thoại thật sau khi tối ưu, TTFA là
    # 1067/1173/1737/1741/1817/2084ms — trung vị ~1740, tức 1100 thấp hơn thực tế
    # rất nhiều. Hậu quả đo được: lượt 1 của một cuộc chọn filler 1300ms cho quãng
    # chờ 2084ms, khách nghe hụt 780ms im lặng ngay câu đầu tiên.
    #
    # Đặt cao chỉ ảnh hưởng LƯỢT ĐẦU; từ lượt 2 `_filler_min_ms` đã có số thật của
    # chính cuộc gọi đó để dùng. Và đặt cao thì cùng lắm chọn câu đệm dài hơn cần
    # thiết — câu trả lời thật vẫn phát ngay sau đó, không mất gì.
    _FILLER_MIN_THOAI_MS = 1800.0
    _FILLER_MIN_CHAT_MS = 900.0

    # Dưới mức trễ này thì ĐỪNG phát câu đệm - khoảng lặng ngắn nghe tự nhiên
    # hơn hẳn một câu "Dạ vâng ạ" chèn vào.
    #
    # Vì sao phải thêm: câu đệm sinh ra để che TTFA ~1100ms. Sau khi bật
    # torch.compile và rút đoạn mẫu, TTS xuống 331ms; cộng cơ chế nghĩ sẵn thì
    # nhiều lượt có câu trả lời gần như tức thì. Lúc đó câu đệm không che gì cả,
    # chỉ thành lời thừa - người nghe báo "dạ vâng ạ lặp lại quá nhiều".
    _FILLER_BO_QUA_MS = 700.0

    def _filler_min_ms(self, session: CallSession, la_thoai: bool, mac_dinh: float) -> float:
        """Filler phải dài ít nhất bằng TTFA gần đây của CHÍNH đường này.

        Ngắn hơn thì khách nghe hụt một khoảng lặng đúng bằng phần thiếu; dài
        quá thì câu trả lời thật bị đẩy ra sau một cách vô ích. Tách thoại/chat
        theo stt_ms vì hai đường chênh nhau đúng phần STT.
        """
        qua = [
            m["ttfa_ms"] for m in session.latency_log[-6:]
            if m.get("ttfa_ms") and bool(m.get("stt_ms")) == la_thoai
        ]
        return max(qua[-3:]) if qua else mac_dinh

    async def _send_filler(self, ws: WebSocket, session: CallSession, t_start: float,
                           metrics: dict, la_thoai: bool):
        """Phát câu đệm đã dựng sẵn NGAY - đây mới là lúc AI bắt đầu nói theo tai khách.

        Phải là await ĐẦU TIÊN của lượt: audio đã nằm sẵn trong cache từ lúc khởi
        động (dung_fillers) nên không tốn GPU, chỉ tốn thời gian gửi.

        ttfa_ms bên dưới đo tới mảnh THẬT đầu tiên và bỏ qua hoàn toàn filler,
        nên nhìn một mình ttfa_ms sẽ tưởng khách phải chờ im lặng lâu hơn thực tế.
        """
        can_che = self._filler_min_ms(
            session, la_thoai,
            self._FILLER_MIN_THOAI_MS if la_thoai else self._FILLER_MIN_CHAT_MS,
        )

        # 1. Đã nghĩ sẵn câu trả lời -> BỎ được khâu sinh chữ (~220ms), NHƯNG
        #    vẫn còn STT bản cuối + TTS mảnh đầu, và đó mới là phần lớn.
        #
        #    Giả định cũ "câu thật tới gần như tức thì" SAI - đo trên ba cuộc gọi
        #    thật: đúng những lượt dùng bản nghĩ sẵn lại là lượt khách phải nghe
        #    im lặng LÂU NHẤT (947ms, 1295ms, 1739ms), vì chỉ chúng bị bỏ câu đệm.
        #    Tức tối ưu này đang làm hỏng chính thứ nó tối ưu.
        #
        #    Vẫn bỏ câu đệm, nhưng chỉ khi đường này thật sự nhanh - để điều kiện
        #    2 bên dưới quyết, đừng quyết thay nó.
        if session.spec_answer and can_che < self._FILLER_BO_QUA_MS:
            metrics["filler_bo_qua"] = f"đã nghĩ sẵn + nhanh sẵn ({can_che:.0f}ms)"
            return
        # 2. Đường này gần đây vốn đã nhanh -> khoảng lặng ngắn tự nhiên hơn.
        if can_che < self._FILLER_BO_QUA_MS:
            metrics["filler_bo_qua"] = f"nhanh sẵn ({can_che:.0f}ms)"
            return

        # Khách vừa HỎI thì "em nắm được rồi" nghe như gạt đi - lọc bỏ những
        # câu gắn cờ không hợp câu hỏi. Chưa có phiên âm ở mốc này nên vẫn suy
        # từ lượt trước: đang tư vấn thì đa số lượt là câu hỏi. (Mốc 2 sẽ đọc
        # session.spec_stt để biết chắc thay vì đoán.)
        kho = lay_kho().cau
        if session.turn_count > 0:
            kho = [c for c in kho if c.hop_cau_hoi]

        dem = getattr(session, "dem_filler", None)
        if dem is None:
            dem = session.dem_filler = {}

        filler_audio, cau = self.tts.pick_filler(
            kho, session.voice_name, min_ms=can_che, dem=dem,
        )
        if not filler_audio:
            return
        dem[cau.id] = dem.get(cau.id, 0) + 1
        await self._send_audio(ws, filler_audio, is_filler=True, turn_id=session.turn_id)
        metrics["filler_ms"] = round((time.perf_counter() - t_start) * 1000)
        metrics["filler_text"] = cau.text
        metrics["filler_id"] = cau.id

    async def process_turn(self, audio_bytes: bytes, session: CallSession, ws: WebSocket):
        """Full pipeline: Audio -> STT -> RAG -> LLM -> TTS -> Audio."""
        t_start = time.perf_counter()
        metrics = {}

        await self._send_filler(ws, session, t_start, metrics, la_thoai=True)

        # STT - dùng lại bản đã phiên âm lúc đoán trước, NHƯNG chỉ khi nó phủ
        # đúng chừng này byte. Bằng nhau nghĩa là bản đoán đã nghe trọn câu,
        # không thiếu chữ cuối nào; lệch một byte cũng phải phiên âm lại.
        #
        # So ĐỘ DÀI chứ không so nội dung: nội dung thì chưa có gì để so (đây
        # chính là thứ ta đang định tính), còn độ dài audio là bằng chứng chắc
        # chắn rằng hai bên nhìn cùng một đoạn tiếng.
        cache = session.spec_stt
        dung_lai = bool(cache and cache[0] == len(audio_bytes) and cache[1])
        metrics["stt_doan_truoc"] = dung_lai
        try:
            if dung_lai:
                transcript = cache[1]
                metrics["stt_ms"] = 0
                logger.info("STT: dùng lại bản đoán trước, bỏ được một lượt phiên âm")
            else:
                with Timer("STT") as t_stt:
                    transcript = await self.stt.transcribe(
                        audio_bytes, sample_rate=session.audio_rate)
                metrics["stt_ms"] = round(t_stt.elapsed_ms)
        except Exception as e:
            logger.error(f"STT error: {e}")
            await self._send_event(ws, "error", {
                "message": "STT server không khả dụng. Dùng text input thay thế."
            })
            await self._send_event(ws, "turn_complete", {"full_response": "", "metrics": {"error": "stt_unavailable"}})
            return

        if not transcript.strip():
            await self._send_event(ws, "error", {"message": "Không nhận dạng được giọng nói"})
            await self._send_event(ws, "turn_complete", {"full_response": "", "metrics": {}})
            return

        # Lượt trước bị khách cắt lời: nối câu nói dở vào câu này thành một ý.
        if session.cau_bi_cat:
            truoc = session.cau_bi_cat
            transcript = session.ghep_cau_bi_cat(transcript)
            logger.info("Ghép câu bị cắt: '%s' + câu mới -> '%s'", truoc, transcript)
            metrics["ghep_cau_bi_cat"] = truoc

        await self._send_event(ws, "transcript", {"text": transcript, "latency_ms": metrics["stt_ms"]})
        session.add_turn("user", transcript)

        # Điểm an toàn thứ nhất. Khách cắt lời trong lúc STT còn chạy thì tới đây
        # mới xử lý được - lúc này câu của họ ĐÃ nằm trong lịch sử nên giữ lại và
        # ghép được. Cắt cứng task ngay lúc STT chạy thì mất trắng câu đó.
        if await self._dung_neu_bi_cat(session, ws):
            return

        await self._generate_response(transcript, session, ws, t_start, metrics)

    async def _tra_bang_cong_cu(self, user_text: str, session: CallSession,
                                metrics: dict) -> str:
        """Hỏi mô hình xem lượt này có cần tra dữ liệu không, rồi tra.

        Chạy như một lượt RIÊNG với prompt tối giản (`PROMPT_QUYET_DINH`), KHÔNG
        dùng prompt tư vấn đầy đủ - lý do đo được ghi ở `cong_cu_llm`: prompt đầy
        đủ ra lệnh "TRẢ LỜI" nên mô hình bỏ qua công cụ, 0/3 lần gọi.

        Chạy NỐI TIẾP sau RAG, không song song. Đường lùi bằng LLM vì thế ăn
        trọn ~419ms trên đường găng - đó là lý do phải có đường nhanh bằng lưới
        từ khoá bên dưới (đo được 9/9 đúng trong ~1ms). Chỉ khi lưới không chắc
        mới trả giá đó, và lúc đó đúng còn quan trọng hơn nhanh.

        Trả về văn bản để ghép vào THÔNG TIN THAM KHẢO. Rỗng nghĩa là không cần
        tra gì - đường đi y như trước khi có tính năng này.
        """
        if not user_text.strip():
            return ""
        t0 = time.perf_counter()

        # ĐƯỜNG NHANH: so khớp chữ trước, chỉ hỏi mô hình khi không chắc.
        # Đo được lưới từ khoá đúng 9/9 trong 0ms, còn lượt LLM đúng 6/7 nhưng
        # ăn 419ms ngay trên đường găng - và hạ xuống model nhỏ hơn không cứu
        # được (qwen3 0.6B và 1.7B đều chỉ 2/9). Chi tiết ở `cong_cu_llm`.
        nhanh = cong_cu_llm.loc_nhanh(user_text)
        if nhanh:
            van = await cong_cu_llm.chay(nhanh, {}, session, rag=self.rag)
            metrics["cong_cu"] = nhanh
            metrics["cong_cu_ms"] = round((time.perf_counter() - t0) * 1000)
            metrics["cong_cu_nhanh"] = True
            logger.info("Công cụ %s (lưới từ khoá, %dms) -> %s", nhanh,
                        metrics["cong_cu_ms"], van[:80].replace("\n", " "))
            return van

        xin_goi: list[dict] = []
        try:
            async for _ in self.llm.stream_response(
                [{"role": "user", "content": user_text}],
                cong_cu_llm.PROMPT_QUYET_DINH,
                tools=cong_cu_llm.DINH_NGHIA,
                on_tool_calls=xin_goi.extend,
            ):
                # Mô hình quyết định KHÔNG cần tra thì nó sinh chữ - bỏ hết, câu
                # trả lời thật do lượt sau sinh bằng prompt đầy đủ.
                pass
        except Exception as e:
            logger.warning("Lượt quyết định công cụ lỗi (bỏ qua): %s", e)
            return ""

        if not xin_goi:
            metrics["cong_cu_ms"] = round((time.perf_counter() - t0) * 1000)
            return ""

        ten_da_goi, phan = [], []
        # Tối đa 2 hàm: mô hình thỉnh thoảng xin cả chùm, mà mỗi hàm là một lần
        # đọc file/CSDL nằm ngay trên đường găng độ trễ.
        for g in xin_goi[:2]:
            van = await cong_cu_llm.chay(g["name"], g.get("arguments") or {},
                                         session, rag=self.rag)
            ten_da_goi.append(g["name"])
            phan.append(van)
            logger.info("Công cụ %s -> %s", g["name"], van[:90].replace("\n", " "))

        metrics["cong_cu"] = ",".join(ten_da_goi)
        metrics["cong_cu_ms"] = round((time.perf_counter() - t0) * 1000)
        return "\n\n".join(p for p in phan if p)

    async def _dung_neu_bi_cat(self, session: CallSession, ws) -> bool:
        """Khách vừa cắt lời? Nếu có thì dọn dẹp, báo xong lượt, trả về True."""
        if not session.yeu_cau_huy:
            return False
        session.yeu_cau_huy = False
        session.danh_dau_bi_cat()
        logger.info("Lượt dừng vì khách cắt lời. Giữ câu để ghép: %r",
                    session.cau_bi_cat[:60])
        await self._send_event(ws, "turn_complete",
                               {"full_response": "", "metrics": {"bi_cat_loi": True}})
        return True

    async def process_text_turn(self, text: str, session: CallSession, ws: WebSocket):
        """Text-only turn (skip STT)."""
        t_start = time.perf_counter()
        metrics = {"stt_ms": 0}

        # Đường chat trước đây KHÔNG có filler: khách gõ xong bấm gửi rồi ngồi im
        # 1.2-1.4 giây (đo thật) mới nghe tiếng, trong khi gọi điện thì nghe ngay.
        # Cùng một pipeline, chỉ thiếu đúng dòng này.
        await self._send_filler(ws, session, t_start, metrics, la_thoai=False)

        if session.cau_bi_cat:
            truoc = session.cau_bi_cat
            text = session.ghep_cau_bi_cat(text)
            logger.info("Ghép câu bị cắt: '%s' + câu mới -> '%s'", truoc, text)
            metrics["ghep_cau_bi_cat"] = truoc

        session.add_turn("user", text)
        await self._send_event(ws, "transcript", {"text": text, "latency_ms": 0})

        await self._generate_response(text, session, ws, t_start, metrics)

    async def _generate_response(self, user_text: str, session: CallSession, ws: WebSocket, t_start: float, metrics: dict):
        """Shared logic: RAG -> LLM streaming -> optional TTS."""
        # Chụp lại bản đoán RỒI dọn ngay: dọn muộn thì đoạn LLM bên dưới đọc phải
        # ô đã bị xoá, còn dọn thiếu thì lượt sau dùng nhầm bản nghĩ của lượt này.
        spec_transcript = session.spec_transcript
        spec_rag = session.spec_rag
        spec_answer = session.spec_answer
        session.clear_speculation()

        # Lượt thường gặp (chào máy, "ai đấy", "đang bận", từ chối...) trả lời
        # bằng bảng có sẵn, KHÔNG qua mô hình - đo được mô hình đóng khuôn
        # 5/10 lượt loại này. Xem `luot_thuong_gap` cho số liệu và lý do.
        dap_san = tra_loi_san(
            user_text, bank=settings.bank_name, agent=settings.agent_name,
            product=session.product, luot_thu=session.turn_count)
        if dap_san:
            metrics["luot_thuong_gap"] = dap_san[0]
            logger.info("Lượt thường gặp '%s' -> trả lời sẵn, bỏ qua RAG+LLM",
                        dap_san[0])

        # Câu hỏi về HỒ SƠ RIÊNG của khách (dư nợ, ngày đến hạn, phải trả bao
        # nhiêu...) trả lời THẲNG TỪ DỮ LIỆU, không qua mô hình. Đây là việc có
        # quy tắc xác định, mà mô hình 3B thì không đáng tin ở đúng chỗ này -
        # xem chú thích đầu `tra_loi_ho_so.py` và `data_source_service.dung_ngu_canh`.
        #
        # Đặt SAU `tra_loi_san`: lượt chào/từ chối phải được xử lý trước, không
        # thì "anh bận lắm" có thể lọt vào mẫu hỏi số.
        if not dap_san:
            from backend.services.gender_detect import xung_ho as _xh
            ho_so = getattr(session, "ho_so_khach", None) or {}
            got = tra_loi_ho_so(
                user_text, ho_so,
                _xh(getattr(session, "gender", ""), getattr(session, "gender_do_tin", None)))
            if got:
                dap_san = got
                metrics["tra_tu_ho_so"] = got[0]
                logger.info("Hỏi hồ sơ '%s' -> trả lời thẳng từ dữ liệu, bỏ qua RAG+LLM",
                            got[0])

        # KHỞI ĐỘNG tra dữ liệu NGAY, chạy song song với RAG bên dưới. Hai việc
        # độc lập: `_tra_bang_cong_cu` chỉ cần `user_text`, không đụng tới kết
        # quả RAG. Nối tiếp chúng là tự cộng dồn thời gian - đo được đường lùi
        # bằng LLM của nó tốn ~419ms và trước đây nằm trọn trên đường găng.
        cong_cu_task = None
        if not dap_san:
            cong_cu_task = asyncio.create_task(
                self._tra_bang_cong_cu(user_text, session, metrics))

        # RAG - dùng lại kết quả đã đoán trước nếu phiên âm cuối nối tiếp đúng
        # phiên âm tạm. Bỏ được ~120ms mã hoá bge-m3 mà không đổi nội dung.
        if dap_san:
            # Câu trả lời sẵn không có con số nào phải tra, khỏi tốn bge-m3.
            rag_context = ""
            metrics["rag_ms"] = 0
            metrics["rag_doan_truoc"] = False
        elif self._spec_hit(spec_transcript, user_text) and spec_rag:
            rag_context = spec_rag
            metrics["rag_ms"] = 0
            metrics["rag_doan_truoc"] = True
            logger.info("RAG: dùng lại bản đoán trước (tiết kiệm ~120ms)")
        else:
            if spec_transcript:
                logger.info(
                    "RAG: đoán trượt, chạy lại | đã đoán '%s' nhưng khách nói '%s'",
                    spec_transcript[:40], user_text[:40],
                )
            try:
                with Timer("RAG") as t_rag:
                    rag_context = await self.rag.retrieve(
                        self._truy_van_rag(user_text, session), top_k=2,
                        san_pham=session.product)
                metrics["rag_ms"] = round(t_rag.elapsed_ms)
            except Exception as e:
                logger.warning(f"RAG error: {e}")
                rag_context = ""
                metrics["rag_ms"] = 0
            metrics["rag_doan_truoc"] = False

        # Cho mô hình TỰ TRA thứ RAG không có: hồ sơ riêng của khách (dư nợ, kỳ
        # hạn còn lại), hoặc số liệu sản phẩm mà mảnh RAG lấy được chưa chạm tới.
        #
        # Chạy sau RAG. Rẻ vì `_tra_bang_cong_cu` đi đường lưới từ khoá (~1ms)
        # cho câu hỏi thường gặp; chỉ cách nói lạ mới rơi xuống đường LLM ~419ms.
        # Đo sau khi có đường nhanh: TTFA 963-999ms, so với 1399-1645ms lúc còn
        # hỏi mô hình mọi lượt.
        # Lượt đã có câu trả lời sẵn (chào, "ai đấy", "đang bận") thì không tra
        # gì cả - vừa phí một lượt LLM vừa không dùng tới, nên `cong_cu_task`
        # không được tạo ở trên.
        du_lieu_cong_cu = ""
        if cong_cu_task is not None:
            try:
                du_lieu_cong_cu = await cong_cu_task
            except Exception as e:
                logger.debug(f"Tra dữ liệu lỗi (bỏ qua): {e}")

        # Dựng ngữ cảnh bằng ĐÚNG hàm mà đường nghĩ-sẵn dùng, xem `_ghep_uu_tien`.
        ngu_canh = _ghep_uu_tien(du_lieu_cong_cu, _ghep_ngu_canh(session, rag_context))

        system_prompt = self.llm.build_system_prompt(
            customer_name=session.customer_name,
            product=session.product,
            rag_context=ngu_canh,
            scenario=getattr(session, "scenario", None),
                    gioi_tinh=getattr(session, "gender", ""),
                    gioi_tinh_do_tin=getattr(session, "gender_do_tin", None),
        )

        # LLM streaming -> TTS consumer (runs CONCURRENTLY with LLM streaming).
        # The LLM loop only enqueues text chunks; the consumer synthesizes and
        # sends them in order. While TTS renders chunk N, the LLM keeps
        # streaming chunk N+1 - so its text is ready the moment TTS frees up,
        # eliminating the gap between sentences.
        text_buffer = ""
        full_response = ""
        # Bản ĐÃ LỌC, ghép từ đúng những mảnh đưa xuống TTS.
        #
        # `full_response` là chuỗi token THÔ từ LLM, chưa qua `_don_loi` - khách
        # nghe "bên em" nhưng lịch sử lại lưu "chúng tôi". Ba chỗ dùng nó đều sai
        # theo: lịch sử nhồi ngược vào prompt lượt sau (nên model cứ được củng cố
        # thói xưng "tôi" mà prompt đang cấm), báo cáo hiện câu khách chưa từng
        # nghe, và bộ dò "bot đang bí" soi nhầm văn bản.
        cau_da_loc = ""
        chunks_enqueued = 0
        tts_queue: asyncio.Queue[str | None] = asyncio.Queue()

        # Ollama và F5-TTS dùng chung một GPU, và đây là nút thắt lớn nhất:
        # đo đối chứng cho thấy TTS mất 510-515ms khi GPU rảnh nhưng 1258-1434ms
        # khi Ollama đang sinh token.
        #
        # Đã thử tạm dừng vòng đọc stream để "nhường GPU" - VÔ TÁC DỤNG, vì ngừng
        # đọc không ngăn được Ollama tiếp tục tính phía server. Cách thật sự hiệu
        # quả là giảm khối lượng Ollama phải sinh (llm_max_tokens).
        first_audio_done = asyncio.Event()

        async def tts_consumer():
            idx = 0
            first_audio_sent = False
            nghi_ms = 0.0        # nhịp nghỉ nợ từ mảnh TRƯỚC, trả vào đầu mảnh này
            while True:
                goi = await tts_queue.get()
                if goi is None:
                    break
                # Quãng nghỉ đi KÈM mảnh: chỗ ngắt câu có thể nằm ở chữ "ạ"
                # đầu mảnh mà `BotLichSu` vừa bỏ, lúc đó mảnh trước không còn
                # dấu câu nào để `nhip_nghi_sau` nhìn ra.
                chunk_text, nghi_them = goi
                nghi_ms += nghi_them

                # Mảnh không có chữ nào (thường là đúng một dấu chấm, sinh ra khi
                # luật "ạ/nhé" cắt trước rồi dấu câu mới tới) - đừng gọi TTS cho
                # nó: tốn một lượt sinh để ra gần như im lặng. Nhưng vẫn phải lấy
                # nhịp nghỉ của nó, không thì mảnh sau mất chỗ ngắt.
                if not chunk_text or not any(c.isalnum() for c in chunk_text):
                    nghi_ms = max(nghi_ms, nhip_nghi_sau(chunk_text))
                    continue

                # First chunk: fewer diffusion steps -> lower TTFA
                t_synth = time.perf_counter()
                audio_chunk = await self._try_synthesize(
                    chunk_text, fast=(idx == 0), voice=session.voice_name,
                    session=session,
                )
                synth_ms = round((time.perf_counter() - t_synth) * 1000)

                # Trả lại nhịp nghỉ mà trim_silence đã cắt mất ở ranh giới mảnh.
                # Chèn vào ĐẦU mảnh này chứ không nối vào cuối mảnh trước: mảnh
                # đầu tiên vì thế không bao giờ bị chèn (TTFA không đổi), và mảnh
                # cuối cùng không bị thêm đuôi lặng thừa.
                if audio_chunk and nghi_ms > 0:
                    audio_chunk = chen_lang_dau_wav(audio_chunk, nghi_ms)
                nghi_ms = nhip_nghi_sau(chunk_text)

                if audio_chunk and not first_audio_sent:
                    metrics["ttfa_ms"] = round((time.perf_counter() - t_start) * 1000)
                    # Bóc tách TTFA: nếu không đo riêng thì đoạn giữa RAG và audio
                    # đầu tiên là hộp đen, không biết LLM hay TTS mới là chỗ chậm.
                    metrics["tts_first_ms"] = synth_ms
                    metrics["tts_first_chars"] = len(chunk_text)
                    first_audio_sent = True
                    first_audio_done.set()   # trả GPU lại cho LLM

                if audio_chunk:
                    await self._send_audio(ws, audio_chunk, chunk_id=idx,
                                           turn_id=session.turn_id)

                await self._send_event(ws, "response_chunk", {
                    "text": chunk_text,
                    "chunk_id": idx,
                })
                idx += 1

        consumer_task = asyncio.create_task(tts_consumer())

        # Phát lại theo TỪ, không theo ký tự: should_flush() cắt câu dựa trên
        # nội dung nên chia thế nào cũng ra cùng kết quả, nhưng đếm theo ký tự
        # làm n_tokens sai lệch hẳn (log từng báo "139 token" cho câu 40 token).
        def _phat_lai(cau: str):
            async def _g():
                for i, tu in enumerate(cau.split(" ")):
                    yield (" " + tu) if i else tu
            return _g()

        # Nếu đã nghĩ sẵn câu trả lời trong lúc khách nói và câu hỏi cuối cùng
        # vẫn khớp thì khỏi gọi LLM nữa - phát lại chữ đã soạn qua ĐÚNG logic cắt
        # câu bên dưới, để phần TTS không phải biết gì về chuyện này.
        dung_ban_nghi = bool(spec_answer) and self._answer_hit(spec_transcript, user_text)
        metrics["llm_nghi_san"] = dung_ban_nghi
        if dap_san:
            # Lượt thường gặp (chào, "ai đấy", "đang bận"...) - xem
            # `luot_thuong_gap` để biết vì sao KHÔNG giao cho mô hình.
            nguon_token = _phat_lai(dap_san[1])
        elif dung_ban_nghi:
            logger.info("LLM: dùng bản đã nghĩ sẵn, bỏ qua sinh mới (tiết kiệm ~220ms)")
            nguon_token = _phat_lai(spec_answer)
        else:
            if spec_answer:
                logger.info(
                    "LLM: bản đã nghĩ KHÔNG dùng được, sinh lại | nghĩ theo '%s' "
                    "nhưng khách nói '%s'",
                    spec_transcript[:40], user_text[:40],
                )
            nguon_token = self.llm.stream_response(session.history, system_prompt)

        def _chan_so(doan: str) -> str:
            """Chặn số sai TRƯỚC khi đưa sang TTS - đây là tầng cuối còn sửa được.

            Mô hình đọc sai số một cách hệ thống (xem chú thích ở `chan_so_sai`),
            và prompt lẫn temperature đều không chữa được. Với tư vấn tài chính
            thì phải chặn, không thể tin.
            """
            # Đối chiếu với `ngu_canh` chứ KHÔNG phải `rag_context`: dữ liệu
            # vừa tra bằng công cụ nằm trong `ngu_canh`. Dùng `rag_context` thì
            # lưới coi dư nợ thật (142.500.000) là số bịa và thay bằng số lớn
            # nhất trong tài liệu sản phẩm (500 triệu) - tự tay tạo ra đúng cái
            # lỗi nó sinh ra để chặn.
            ra, sua = chan_so_sai(doan, ngu_canh)
            if sua:
                logger.warning("CHẶN SỐ SAI: %s | %r -> %r", sua, doan[:50], ra[:50])
                metrics["chan_so_sai"] = sua
            # Hàng rào thứ hai: SỐ TIỀN. Truyền cả câu khách vừa nói để không
            # "sửa" con số do chính khách nêu ra - AI nhắc lại số của khách là
            # đúng, chặn nó mới là sai.
            ra, sua_tien = chan_tien_sai(ra, ngu_canh, khach_noi=user_text)
            if sua_tien:
                logger.warning("CHẶN TIỀN SAI: %s | %r", sua_tien, ra[:50])
                metrics["chan_tien_sai"] = sua_tien
            return ra

        # Bớt "ạ"/"Dạ" thừa. Bỏ "Dạ" mở đầu khi: (a) vừa phát filler - gần hết
        # filler đã mở bằng "Dạ" rồi, để nguyên thì khách nghe "Dạ vâng ạ. Dạ
        # hiện bên em..." hai lần liền; hoặc (b) lượt chẵn - mở đầu lượt nào cũng
        # "Dạ" thì nghe như máy, mà bỏ sạch lại cộc, xen kẽ là vừa.
        bot_lich_su = BotLichSu(
            bo_da=bool(metrics.get("filler_text")) or session.turn_count % 2 == 0)

        def _noi_manh(da_co: str, them: str) -> str:
            """Ghép mảnh lại thành câu đọc được.

            Không chèn dấu cách trước mảnh mở đầu bằng dấu câu: bộ cắt đôi khi
            đẩy dấu chấm sang mảnh riêng, ghép thẳng sẽ ra "… một năm ạ ." trong
            bản ghi và báo cáo.
            """
            if not da_co:
                return them
            if them[:1] in ".,!?:;…":
                return da_co + them
            return da_co + " " + them

        def _don_loi(doan: str) -> str:
            # `sua_xung_ho` chạy TRƯỚC: nó bỏ số thứ tự đầu câu, mà các bước sau
            # xét chữ đầu ("Dạ", con số) nên phải sạch trước khi tới đó.
            #
            # `bo_cau_lui_thua` đứng SAU `sua_xung_ho` để câu lùi đã về đúng dạng
            # "anh/chị" trước khi đem so, và TRƯỚC `_chan_so` để phần bị cắt bỏ
            # không mang theo con số nào làm lệch bộ chặn số.
            return bot_lich_su(_chan_so(bo_cau_lui_thua(sua_xung_ho(doan))))

        t_llm = time.perf_counter()
        n_tokens = 0
        try:
            async for token in nguon_token:
                # Điểm an toàn thứ hai: khách cắt lời giữa lúc AI đang trả lời.
                # Dừng ở đây thì câu khách vẫn nguyên trong lịch sử để ghép, và
                # không phí thêm token nào cho câu trả lời không ai nghe.
                if session.yeu_cau_huy:
                    tts_queue.put_nowait(None)
                    await consumer_task
                    await self._dung_neu_bi_cat(session, ws)
                    return

                n_tokens += 1
                if n_tokens == 1:
                    # Ollama nghĩ xong, token đầu ra: đây là TTFT thật của LLM.
                    metrics["llm_ttft_ms"] = round((time.perf_counter() - t_llm) * 1000)
                text_buffer += token
                full_response += token
                await self._send_event(ws, "token", {"text": token})

                if should_flush(text_buffer, first_chunk=(chunks_enqueued == 0)):
                    chunk_text = text_buffer.strip()
                    text_buffer = ""
                    if chunk_text:
                        if chunks_enqueued == 0:
                            # LLM phải sinh đủ chữ cho câu đầu thì TTS mới có việc.
                            # Tách riêng khỏi TTFT: chờ token đầu và gom đủ câu là
                            # hai nguyên nhân chậm khác nhau, cách xử lý cũng khác.
                            metrics["llm_chunk1_ms"] = round((time.perf_counter() - t_llm) * 1000)
                        chunk_text = _don_loi(chunk_text)
                        tts_queue.put_nowait((chunk_text, bot_lich_su.nghi_truoc_ms))
                        cau_da_loc = _noi_manh(cau_da_loc, chunk_text)
                        chunks_enqueued += 1
        except Exception as e:
            logger.error(f"LLM error: {e}")
            await self._send_event(ws, "error", {"message": f"LLM error: {e}"})

        # Flush remaining text, then wait for the consumer to drain the queue
        if text_buffer.strip():
            du = _don_loi(text_buffer.strip())
            tts_queue.put_nowait((du, bot_lich_su.nghi_truoc_ms))
            cau_da_loc = _noi_manh(cau_da_loc, du)
        tts_queue.put_nowait(None)
        try:
            await consumer_task
        except Exception as e:
            logger.error(f"TTS consumer error: {e}")

        metrics["total_ms"] = round((time.perf_counter() - t_start) * 1000)
        # Từ đây dùng bản đã lọc. Chỉ lùi về bản thô khi không có mảnh nào xuống
        # TTS (lỗi giữa chừng) - thà lưu câu thô còn hơn lưu chuỗi rỗng.
        cau_bot_that = cau_da_loc.strip() or full_response
        session.add_turn("assistant", cau_bot_that)
        session.log_latency(metrics)
        _schedule_persist(session)  # after the audio is out - zero TTFA cost

        # Đếm các dấu hiệu "bot đang bí" để quyết định có nối máy cho chuyên
        # viên không. Chỉ CẬP NHẬT ĐẾM ở đây; việc nối máy do lớp gọi điện làm,
        # vì chỉ nó mới cầm được thiết bị. Xem services/transfer_service.py.
        try:
            from backend.services import transfer_service
            transfer_service.cap_nhat_dem(
                session,
                cau_khach=user_text,
                cau_bot=cau_bot_that,
                rag_rong=not rag_context,
            )
        except Exception as e:
            logger.debug(f"Cập nhật đếm chuyển tiếp bỏ qua: {e}")

        await self._send_event(ws, "turn_complete", {
            "full_response": cau_bot_that,
            "metrics": metrics,
        })

        metrics["llm_tokens"] = n_tokens
        metrics["tts_chunks"] = chunks_enqueued

        # Bảng bóc tách TTFA - chỉ ra ĐÂU chậm thay vì chỉ nói "chậm".
        # TTFA = RAG + (chờ token đầu) + (gom đủ câu đầu) + (TTS mảnh đầu)
        ttfa = metrics.get("ttfa_ms")
        rag = metrics.get("rag_ms", 0)
        ttft = metrics.get("llm_ttft_ms")
        chunk1 = metrics.get("llm_chunk1_ms")
        tts1 = metrics.get("tts_first_ms")
        if ttfa is not None and ttft is not None and chunk1 is not None and tts1 is not None:
            stt = metrics.get("stt_ms", 0) or 0      # đường thoại mới có
            gom_cau = chunk1 - ttft                  # thời gian sinh nốt câu đầu
            con_lai = ttfa - stt - rag - chunk1 - tts1   # hàng đợi + gửi WS + sai số
            logger.info(
                "TTFA=%dms = STT %dms + RAG %dms%s + LLM_chờ_token_đầu %dms "
                "+ LLM_gom_câu_đầu %dms + TTS_mảnh_đầu %dms (%d ký tự) + khác %dms"
                "  |  TARGET 1000ms %s",
                ttfa, stt, rag,
                " (đoán trước)" if metrics.get("rag_doan_truoc") else "",
                ttft, gom_cau, tts1, metrics.get("tts_first_chars", 0),
                con_lai, "ĐẠT" if ttfa < 1000 else "KHÔNG ĐẠT",
            )
        # AI bắt đầu nói = filler nếu có (đường thoại), không thì là mảnh thật.
        bat_dau_noi = metrics.get("filler_ms")
        if bat_dau_noi is not None:
            logger.info(
                "AI bắt đầu nói sau %dms (filler '%s'), câu trả lời thật sau %sms "
                "-> khách KHÔNG nghe khoảng lặng nếu filler dài hơn %sms",
                bat_dau_noi, metrics.get("filler_text", ""),
                metrics.get("ttfa_ms", "-"), metrics.get("ttfa_ms", "-"),
            )
        else:
            # Cả hai đường đều gửi filler, nên tới đây nghĩa là cache filler rỗng
            # cho giọng đang dùng - khách phải chờ im lặng hết TTFA.
            logger.warning(
                "KHÔNG có filler cho giọng '%s' -> khách chờ im lặng đủ %sms",
                session.voice_name, metrics.get("ttfa_ms", "-"),
            )
        logger.info(
            "Turn complete: TTFA=%sms Total=%dms | %d token, %d mảnh TTS",
            metrics.get("ttfa_ms", "-"), metrics["total_ms"], n_tokens, chunks_enqueued,
        )

    async def _send_audio(self, ws: WebSocket, wav_bytes: bytes, chunk_id: int = 0,
                          is_filler: bool = False, turn_id: int = 0):
        # turn_id: client so với lượt nó đang chờ, lệch thì bỏ. Huỷ lượt cũ ở
        # phía server đã chặn gần hết, nhưng mảnh đã nằm trong đệm socket thì
        # vẫn tới nơi - đây là chốt chặn cuối.
        data = base64.b64encode(wav_bytes).decode()
        await ws.send_json({
            "type": "audio", "data": data, "chunk_id": chunk_id,
            "is_filler": is_filler, "turn_id": turn_id,
        })

    async def _send_event(self, ws: WebSocket, event_type: str, payload: dict):
        await ws.send_json({"type": event_type, **payload})
