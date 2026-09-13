import asyncio
import base64
import logging
import random
import re
import time

from fastapi import WebSocket

from backend.config import settings
from backend.models import scenarios_db
from backend.models.db import save_session
from backend.pipeline.session_manager import CallSession
from backend.pipeline.chan_tuan_thu import chan_gan_thu_nhap, chan_tu_cam
from backend.pipeline.thuoc_tinh import (chan_thuoc_tinh_sai,
                                         sua_theo_tai_lieu)
from backend.pipeline.ngu_canh_tai_lieu import toan_van as _toan_van_tai_lieu
from backend.pipeline.text_normalizer import noi_tiep_ve_dang_do
from backend.pipeline import cong_cu_llm
from backend.pipeline.cau_chan_lap import cau_chan, dem_chan_lien_tiep
from backend.pipeline.hoi_lai import chon_cau_hoi_lai, nen_hoi_lai
from backend.pipeline.luot_thuong_gap import tra_loi_san
from backend.pipeline.danh_muc_san_pham import tra_loi as tra_loi_danh_muc
from backend.pipeline.tra_loi_ho_so import tra_loi as tra_loi_ho_so
from backend.pipeline.text_chunker import (TOI_THIEU_TU_MANH_CUOI, co_manh,
                                            cho_gom_ms, nhip_nghi_sau, noi_lo,
                                            sap_cum_gop, tach_manh, ty_le_gop,
                                            uoc_sinh_ms)
from backend.pipeline.text_normalizer import (CAU_KIEM_TRA_LAI, BoHuaSuong,
                                              BotLichSu, bo_cau_lui_thua,
                                              bo_chu_de_da_neu,
                                              chan_chu_ngoai, chan_lai_suat_bia,
                                              chan_so_sai, sua_chu_mo_hinh,
                                              chan_tien_sai, sua_xung_ho)
from backend.services.audio_utils import chen_lang_dau_wav, dai_wav_ms
from backend.services.stt_service import STTService
from backend.services.llm_service import LLMService
from backend.services.tts_service import GOP_LO, LO_TOI_DA, F5TTSService
from backend.services.rag_service import RAGService
from backend.services.filler_store import lay_kho
from backend.services.filler_pick import (NGUONG_BO_DEM_MS, can_che_ms,
                                          cho_den_khi, du_doan_cho_ms,
                                          loc_cau_dem_llm,
                                          tu_vung_tu_kho,
                                          nen_bo_cau_dem, tinh_huong_dung)
from backend.services.tieng_san import kho_tieng_san
from backend.services.bang_hoi_dap import (bo_qua_chi_theo_tinh_huong,
                                           bo_qua_khac_san_pham, doc_nguyen_van,
                                           dong_theo_tinh_huong)
from backend.services.filler_situation import (
    DIEU_KIEN_NGU_CANH, NGUONG_CAU_DEM, chon_tinh_huong, chuan_hoa,
    loc_theo_ngu_canh,
)
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
    ở `_mat_na_loc`: hai số cùng đơn vị tiền trong ngữ cảnh là mô hình
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


def _ghi_im_lang(session: CallSession, t_start: float, metrics: dict):
    """`im_lang_ms` = khách dứt lời -> AI bật ra tiếng. Quãng khách NGỒI IM.

    Khác `ttfa_ms` ở CẢ HAI ĐẦU, và cả hai chỗ khác đều làm số nhỏ đi so với
    thứ tai khách thật sự chịu:

    - Đầu trước: `ttfa_ms` đếm từ lúc pipeline chạy, mà lúc đó VAD đã nghe im
      `SILENCE_END_MS` (750ms) để dám chắc khách nói xong, có khi còn chờ lượt
      cũ dừng hẳn. Khách ngồi im trọn khoảng đó mà không số đo nào đếm.
    - Đầu sau: `ttfa_ms` đo tới mảnh NỘI DUNG đầu tiên, bỏ qua câu đệm - nhưng
      câu đệm mới là lúc tai khách nghe thấy tiếng. Có câu đệm thì `filler_ms`
      mới là mốc đúng, và nó nhỏ hơn `ttfa_ms` rất nhiều.

    Chỉ có ở đường thoại: `t_dut_loi` do vòng thu của `PhoneCallBridge` đặt.
    Đường chat gõ chữ không có ai dứt lời nên bỏ qua - thiếu khoá thì báo cáo tự
    lùi về cách hiển thị cũ, không có gì để nhầm.

    XOÁ mốc sau khi dùng. Để lại thì lượt kế tiếp nào KHÔNG đi qua VAD (câu treo,
    đọc nốt phần dở) sẽ trừ vào mốc của lượt trước rồi ghi ra một con số vài chục
    giây - nhìn thì biết sai, nhưng nó đã lọt vào trung bình trước khi ai kịp nhìn.
    """
    moc = session.t_dut_loi
    session.t_dut_loi = None
    if moc is None:
        return
    cho_truoc = round((t_start - moc) * 1000)
    metrics["cho_truoc_ms"] = cho_truoc
    # Câu đệm trước, vì nó phát TRƯỚC. Không có thì khách chờ trọn tới mảnh thật.
    tieng_dau = metrics.get("filler_ms")
    if tieng_dau is None:
        tieng_dau = metrics.get("ttfa_ms")
    if tieng_dau is not None:
        metrics["im_lang_ms"] = cho_truoc + tieng_dau


def _nap_bang_thuoc_tinh() -> dict:
    """Bảng thuộc tính cho lưới kiểm chứng. GIEO trước rồi mới đọc.

    VÌ SAO PHẢI GIEO Ở ĐÂY. Bản đầu chỉ gọi `doc_bang_sync`, mà hàm gieo chỉ nằm
    trong vỏ async `luat_kiem_db.doc_bang()` - vỏ đó chỉ chạy khi có người mở
    trang quản lý luật kiểm. Không ai mở thì bảng `thuoc_tinh_kiem` rỗng 0 dòng,
    `doc_bang_sync` trả `{}`, và `chan_thuoc_tinh_sai` thoát ngay ở `if not kho`.

    Đo trên máy chạy thật 09-09-2026: bảng đúng 0 dòng, và lưới thuộc tính CHƯA
    TỪNG chạy một lần nào - không một dòng "THUỘC TÍNH LỆCH" trong log, trong khi
    gọi thẳng `chan_thuoc_tinh_sai` trên chính câu AI vừa nói thì nó chặn đúng.
    Bảng rỗng không phải ngoại lệ nên nhánh `except` bên dưới không cứu được.

    Ba đường ra, cả ba đều có chủ ý:
      - DB chưa mở / đọc hỏng -> bảng gốc trong code. Mất lưới lặng lẽ nguy hiểm
        hơn nhiều so với dùng bảng cũ.
      - Bảng có dòng nhưng KHÔNG dòng nào bật -> trả rỗng, tôn trọng quyết định
        của người vận hành. Phân biệt được với ca "chưa gieo" nhờ ĐẾM SỐ DÒNG.
      - Bình thường -> bảng trong DB.
    """
    from backend.pipeline.thuoc_tinh import THUOC_TINH_MAC_DINH
    try:
        from backend.models import db as _db
        from backend.models.luat_kiem_db import doc_bang_sync, gieo_mac_dinh_sync
        _c = _db.connection()
        if _c is None:
            raise RuntimeError("DB chưa mở")
        gieo_mac_dinh_sync(_c)          # chạy lại được: chỉ thêm dòng còn thiếu
        bang = doc_bang_sync(_c)
        if not bang:
            n = _c.execute("SELECT COUNT(*) FROM thuoc_tinh_kiem").fetchone()[0]
            logger.warning(
                "Lưới thuộc tính TẮT: %d dòng trong bảng, không dòng nào bật", n)
        return bang
    except Exception as e:
        logger.warning("Không đọc được bảng thuộc tính (%s) - dùng mặc định", e)
        return THUOC_TINH_MAC_DINH


class StreamingPipeline:
    """Orchestrates the full voice AI pipeline with graceful degradation."""

    def __init__(self, stt: STTService, llm: LLMService, tts: F5TTSService, rag: RAGService):
        self.stt = stt
        self.llm = llm
        self.tts = tts
        self.rag = rag
        self._da_bao_tts_chet = False
        # Đọc MỘT LẦN lúc dựng pipeline: đường sinh không được đụng SQLite.
        self._bang_thuoc_tinh = _nap_bang_thuoc_tinh()

    @property
    def _tts_available(self) -> bool:
        return self.tts._is_loaded

    @staticmethod
    def _toc_cho_phien(tts, session, voice: str | None) -> float | None:
        """Tốc đọc cho phiên. Ưu tiên ô ĐÃ CHỐT của lượt.

        VÌ SAO PHẢI CÓ Ô CHỐT (lỗi có sẵn, tìm ra 06-09-2026): hàm này đọc
        `session.tinh_huong`, nhưng `_generate_response` gọi `clear_speculation()`
        ngay dòng đầu và hàm đó đặt `tinh_huong = None`. Nên tại MỌI lệnh gọi TTS
        thật, `tinh_huong` luôn rỗng - tốc riêng theo tình huống chưa bao giờ
        chạy trên đường thoại.

        Hệ quả thứ hai, nặng hơn: `speed` nằm trong khoá cache TTS. Dựng sẵn
        tiếng lúc `tinh_huong` còn sống rồi phát lúc nó đã bị xoá là hai khoá
        khác nhau -> cache trượt 100%.

        Xem `tests/test_toc_doc_chot_theo_luot.py`.

        Phân biệt thoại/chat bằng `session.audio_rate` - 8000 là đường thoại.
        Đó là mốc sẵn có và luôn đúng, không phải cờ tự đặt thêm.

        GIÁ PHẢI TRẢ, ghi lại cho rõ: tốc riêng theo tình huống làm khoá cache
        câu bị CHIA theo tình huống, nên tỉ lệ trúng cache giảm.
        """
        da_chot = getattr(session, "toc_doc_luot", None)
        if da_chot is not None:
            return da_chot
        return StreamingPipeline._tinh_toc_doc(tts, session, voice)

    @staticmethod
    def _chot_toc_doc(tts, session, voice: str | None) -> float | None:
        """Chốt tốc đọc cho lượt này. Gọi MỘT LẦN, trước `clear_speculation()`.

        Ghi đè vô điều kiện: mỗi lượt tình huống một khác nên phải tính lại.
        """
        session.toc_doc_luot = StreamingPipeline._tinh_toc_doc(tts, session, voice)
        return session.toc_doc_luot

    # Tốc đọc có đi theo TÌNH HUỐNG không. Đang TẮT, và đây là quyết định có đo:
    #
    # Nhánh đó chưa bao giờ chạy - `clear_speculation()` xoá `tinh_huong` trước
    # mọi lệnh gọi TTS (xem `_toc_cho_phien`). Nên "bật lại" không phải khôi phục
    # hành vi cũ mà là đổi hành vi sang thứ chưa ai nghe thử.
    #
    # Đo trên DB đang chạy 06-09-2026: 34 tình huống đang bật, ĐÚNG MỘT cái đặt
    # tốc riêng - `khach_noi_khong_ro` đặt 1.0. Mà dự án đã đo tốc đọc quyết định
    # độ nghe rõ thế nào: 0,90 cho 28/30 câu nghe đúng, 1,00 chỉ 23/30. Bật lên
    # nghĩa là đọc NHANH HƠN đúng vào lúc khách vừa báo nghe không rõ - ngược
    # hẳn thứ cần làm.
    #
    # Thêm nữa nó chia nhỏ khoá cache TTS theo tình huống, chống lại chính việc
    # dựng sẵn tiếng đang làm.
    #
    # Muốn bật thì đặt True và đo lại hai thứ: độ nghe rõ, và tỉ lệ trúng cache.
    TOC_DOC_THEO_TINH_HUONG = False

    @staticmethod
    def _tinh_toc_doc(tts, session, voice: str | None) -> float | None:
        """Phép tính thuần: (tình huống nếu bật) -> giọng -> hệ số thoại."""
        try:
            goc = None
            if StreamingPipeline.TOC_DOC_THEO_TINH_HUONG and session.tinh_huong:
                # Import trong thân hàm: filler_store không kéo torch nhưng
                # streaming_pipeline thì có - import ở tầng module làm mọi lượt
                # gọi chịu chi phí, và tạo vòng phụ thuộc khi khởi động.
                from backend.services.filler_store import lay_kho
                th = session.tinh_huong[1]   # (số_byte, id, điểm) → lấy id
                for t in lay_kho().tinh_huong:
                    if t.id == th and t.speed is not None:
                        goc = t.speed
                        break
            if goc is None:
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

    async def _try_synthesize_lo(self, texts: list[str], voice: str | None = None,
                                 session=None) -> list[bytes | None]:
        """Sinh cả lô trong một lần gọi model. Hỏng thì lùi về sinh từng mảnh.

        Có đường lùi vì bản gộp lô dựa vào nội bộ F5 (`CFM.sample`) - nếu thư
        viện đổi thì cuộc gọi vẫn phải ra tiếng, chỉ chậm hơn.
        """
        if not self._tts_available:
            return [None] * len(texts)
        try:
            toc = self._toc_cho_phien(self.tts, session, voice) if session is not None else None
            return await self.tts.synthesize_nhieu(texts, voice=voice, speed=toc)
        except Exception as e:
            logger.warning("TTS gộp lô hỏng (%s) - lùi về sinh từng mảnh", e)
            return [await self._try_synthesize(t, voice=voice, session=session)
                    for t in texts]

    # --- Hâm nóng cache TTS trong quãng im cuối lượt --------------------------

    # Tiểu từ mở đầu mà `_don_loi` có thể bỏ (tuỳ lượt chẵn/lẻ, tuỳ có câu đệm).
    # Không đoán nổi lúc dựng sẵn nên thấy là bỏ qua - thà MISS còn hơn sinh một
    # mảnh chắc chắn sai khoá cache.
    _TIEU_TU_MO_DAU = re.compile(r"^(dạ|vâng)\b", re.IGNORECASE)

    @staticmethod
    def _manh_dau_ham_cache(spec_answer: str,
                            mo_dau: tuple[str, ...] = ()) -> str | None:
        """Mảnh đầu đáng hâm cache, hoặc None nếu không chắc khớp lượt thật.

        Dùng `chia_ca_luot` - NGUỒN DUY NHẤT của luật cắt cả lượt. Tuyệt đối
        không viết lại luật cắt ở đây: dự án đã hỏng đúng kiểu đó một lần, khi
        `api/voices.py` giữ một bản chép riêng và trang nghe thử cắt khác cuộc
        gọi thật mà không có gì báo lỗi.
        """
        if not (spec_answer or "").strip():
            return None
        from backend.pipeline.text_chunker import chia_ca_luot
        manh = chia_ca_luot(spec_answer)
        if not manh:
            return None
        dau = manh[0].strip()
        if not dau or StreamingPipeline._TIEU_TU_MO_DAU.match(dau):
            return None
        # Câu đệm nêu chủ đề thì `BotLichSu` cắt cụm đó khỏi mảnh đầu (xem
        # `bo_chu_de_da_neu`), mà cache khoá theo NGUYÊN VĂN chữ - hâm chữ cũ là
        # hâm thứ sẽ không bao giờ phát, lượt đó chờ thêm trọn một mảnh F5.
        # Lúc này chưa biết mẩu mở đầu nào được chọn, nên hâm bản mà NHIỀU mẩu
        # của tình huống đoán được cho ra nhất; hoà thì giữ bản chưa cắt như cũ.
        bien = [bo_chu_de_da_neu(m, dau) for m in mo_dau]
        bien = [b[:1].upper() + b[1:] for b in bien if b.strip()]
        if not bien:
            return dau
        return max(dict.fromkeys(bien), key=lambda b: (bien.count(b), b == dau))

    @staticmethod
    def _mo_dau_du_doan(session: CallSession, n: int) -> tuple[str, ...]:
        """Các mẩu mở đầu của tình huống vừa đoán cho ĐÚNG đoạn tiếng `n`.

        Tình huống của đoạn cũ hơn thì bỏ: nó thuộc phiên âm cụt đã bị thay.
        """
        th = getattr(session, "tinh_huong", None)
        if not th or th[0] != n:
            return ()
        try:
            from backend.services.filler_store import lay_kho
            t = next((x for x in lay_kho().tinh_huong if x.id == th[1]), None)
        except Exception:
            return ()
        return tuple(t.mo_dau) if t else ()

    # Lời nhắc sinh câu đệm. NGẮN và tách hẳn khỏi prompt tư vấn - dự án đã có
    # bài học: nhét prompt tư vấn vào một lượt có mục đích khác thì mô hình bỏ
    # việc được giao và quay về tư vấn (xem lượt định tuyến gọi hàm).
    #
    # Cấm số ngay trong lời nhắc DÙ ĐÃ có lưới `loc_cau_dem_llm`: nhắc trước thì
    # phần lớn lượt không sinh số, lưới chỉ còn phải chặn số ít - mà mỗi lần lưới
    # chặn là một lượt khách nghe im lặng.
    _NHAC_CAU_DEM = (
        "Khách vừa hỏi: {hoi}\n\n"
        "Viết MỘT câu dẫn ngắn để nhân viên nữ ngân hàng nói ngay trước khi trả "
        "lời, thể hiện đã nghe rõ chủ đề. Luật:\n"
        "- Tối đa 10 từ, kết bằng dấu phẩy\n"
        "- Nhắc lại CHỦ ĐỀ khách hỏi, KHÔNG trả lời\n"
        "- TUYỆT ĐỐI không có chữ số, không hứa hẹn con số nào\n"
        "- Xưng em, gọi anh chị\n"
        "- KHÔNG kết thúc bằng chữ 'thì'\n"
        "Ví dụ: 'Dạ về thời gian giải ngân,'\n\n"
        "Chỉ trả về đúng câu đó, không giải thích."
    )

    # Dưới bấy nhiêu ký tự thì câu còn quá cụt để dẫn chủ đề. Đo trên lượt
    # thật: "a lô ai đấy ạ" (13) và "ừ em nói đi" (11) bị chặn - đúng ý, hai
    # lượt đó không có chủ đề nào để dẫn, dẫn bừa còn tệ hơn im lặng.
    _TOI_THIEU_KY_TU_CAU_DEM = 20

    def _xep_nghi_cau_dem(self, session: CallSession) -> None:
        """Xếp một task nền nghĩ câu đệm, nếu lượt này đang cần và chưa có.

        KHÔNG await: hàm gọi nó (`speculate`) chạy trong vòng thu tiếng, nghẽn
        ở đây là nghẽn cả đường nhận audio.

        Ba chốt chặn cái giá:
          `tinh_huong is None`  kho khớp rồi thì đã có clip dựng sẵn, khỏi tốn
          `not spec_cau_dem`    mỗi lượt sinh ĐÚNG MỘT lần
          chữ đủ dài            xem `_TOI_THIEU_KY_TU_CAU_DEM`

        Giữ tham chiếu mạnh trong `_bg_writes` theo đúng khuôn `_ham_cache_tts`:
        task rơi khỏi tầm tham chiếu thì bị thu gom giữa chừng.
        """
        if session.tinh_huong is not None or session.spec_cau_dem:
            return
        if getattr(session, "_cau_dem_dang_nghi", False):
            return
        chu = (session.spec_stt or (0, ""))[1]
        if len(chu) < self._TOI_THIEU_KY_TU_CAU_DEM:
            return

        session._cau_dem_dang_nghi = True

        async def _chay():
            try:
                await self._nghi_cau_dem(chu, session)
            finally:
                session._cau_dem_dang_nghi = False

        task = asyncio.create_task(_chay())
        _bg_writes.add(task)
        task.add_done_callback(_bg_writes.discard)

    async def _nghi_cau_dem(self, hoi: str, session: CallSession) -> None:
        """Nhờ mô hình nghĩ câu đệm cho lượt mà kho tình huống không khớp.

        Chạy trong lúc khách còn đang nói nên GPU rảnh và không chạm đường găng.
        Sinh xong thì dựng tiếng luôn qua `_ham_cache_tts` - đường phát tra cache
        bằng nguyên văn chữ nên lúc lượt mở gần như 0ms.

        MỌI lỗi đều nuốt: đây là đường phụ, hỏng thì rơi về im lặng đúng như
        trước khi có nó. Không được để nó làm chết bản đoán câu trả lời chạy
        ngay sau.

        Lưới lọc nằm ở `filler_pick.loc_cau_dem_llm` (thuần logic, test được
        không cần GPU). Chuỗi ghi vào `session.spec_cau_dem` là chuỗi SẴN SÀNG
        ĐỌC - nơi dùng không lọc lại.
        """
        try:
            tho = await self.llm.generate_simple(self._NHAC_CAU_DEM.format(hoi=hoi))
        except Exception as e:
            logger.debug("nghĩ câu đệm bỏ qua: %s", e)
            return
        # Truyền VỐN TỪ nghiệp vụ: câu đệm không được đọc lại chữ mà máy nghe
        # sai. Xem luật 5 trong `loc_cau_dem_llm` cho ca thật đã đo.
        cau = loc_cau_dem_llm(tho, tu_vung=self._von_tu_nghiep_vu())
        if not cau:
            logger.info("câu đệm LLM bị lưới chặn: %r", (tho or "")[:60])
            return
        session.spec_cau_dem = cau
        logger.info("câu đệm LLM: %r", cau)
        await self._ham_cache_tts(cau, session)

    async def _ham_cache_tts(self, manh: str, session: CallSession) -> None:
        """Sinh trước `manh` CHỈ để nạp cache. Không cất, không phát, vứt kết quả.

        VÌ SAO AN TOÀN: cache của `synthesize` khoá theo nguyên văn chữ, và
        đường phát chỉ tra bằng đúng chữ nó sắp phát. Nên đoán sai chỉ thành
        MISS, không thể thành SAI TIẾNG. Không có bytes nào chạm tới `session` -
        `tests/test_ham_cache_tts.py` canh đúng bất biến đó.

        Bỏ qua khi worker F5 đang bận: executor chỉ có MỘT worker, chen vào là
        đẩy lùi mảnh kế của lượt đang phát và tạo quãng im giữa câu.

        Chạy nền và giữ tham chiếu mạnh theo khuôn `_bg_writes`: dòng ghi cache
        nằm SAU `run_in_executor`, nên task bị huỷ giữa chừng thì thread F5 vẫn
        chạy hết mà cache không được ghi - vừa mất GPU vừa giữ worker.
        """
        if getattr(self.tts, "dang_ban", 1) != 0:
            logger.info("hâm cache TTS: BỎ - worker F5 đang bận")
            return
        logger.info("hâm cache TTS: dựng trước mảnh đầu %r", manh[:40])

        async def _chay():
            try:
                await self._try_synthesize(
                    manh, fast=True, voice=session.voice_name, session=session)
            except Exception as e:
                logger.debug("hâm cache TTS bỏ qua: %s", e)

        task = asyncio.create_task(_chay())
        _bg_writes.add(task)
        task.add_done_callback(_bg_writes.discard)

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

    def _tra_bang_hoi_dap(self, text: str, session: CallSession,
                          tinh_huong_id: str | None = None) -> dict | None:
        """Dòng bảng hỏi-đáp khớp với lời khách, hoặc None.

        Tra TRƯỚC khi hỏi tri thức. Trúng thì nội dung là câu đã soạn sẵn - đúng
        nguyên văn, không phụ thuộc việc mô hình có đọc đúng con số hay không.
        Trượt thì trả None và đường cũ chạy nguyên vẹn.

        Dùng lại `chon_tinh_huong`: việc "chọn id khớp nhất từ kho ví dụ đã
        nhúng" y hệt bài toán chọn tình huống, viết lại là có hai bộ luật ngưỡng
        rồi lệch nhau lúc nào không biết.

        Nhóm tình huống CHÊ thì ngược lại: dòng của nó chỉ đi theo `tinh_huong_id`
        mà bộ phân loại (có cổng ngữ cảnh) đã chọn cho câu đệm, không bao giờ theo
        cosine - xem `bang_hoi_dap.dong_theo_tinh_huong`.
        """
        try:
            from backend.main import app_state
            bang = getattr(app_state, "hoi_dap", None) or {}
            dieu_kien = {ma: d.get("san_pham", "") for ma, d in bang.items()}
            bo = bo_qua_khac_san_pham(dieu_kien, session.product)
            ma = dong_theo_tinh_huong(tinh_huong_id, bang, DIEU_KIEN_NGU_CANH)
            if ma and ma not in bo:
                dong = dict(bang[ma])
                dong["theo_tinh_huong"], dong["diem"] = True, 0.0
                return dong
            kho = getattr(app_state, "hoi_dap_vector", None)
            if not kho or len(text) < 4:
                return None
            q = chuan_hoa(self.rag.embed([text]))[0]
            ma, diem = chon_tinh_huong(
                q, kho, bo_qua=bo | bo_qua_chi_theo_tinh_huong(bang, DIEU_KIEN_NGU_CANH))
            if not ma:
                return None
            dong = dict(app_state.hoi_dap[ma])
            dong["diem"] = diem
            return dong
        except Exception as e:
            logger.debug("tra bảng hỏi-đáp trượt (bỏ qua): %s", e)
            return None

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
        # Câu đệm sinh trong task RIÊNG, đặt TRƯỚC mọi lưới return của hàm này.
        #
        # Hai bản trước đặt nó bên trong `_run()` và cả hai đều CHƯA BAO GIỜ
        # chạy. Lý do là lưới ngay dưới: bản đoán giữa chừng mất 1-2 giây (STT +
        # RAG + LLM), nên `spec_running` gần như luôn True và mọi lần gọi
        # `speculate(ngay=False)` sau đó thoát ngay tại dòng đầu. Log 06-09-2026
        # ghi thẳng: "HUỶ bản giữa chừng (đang ở bước 'LLM')" - tức lúc khách
        # dứt lời nó vẫn đang chạy dở.
        #
        # Tách ra task riêng thì câu đệm không còn phụ thuộc vòng đời bản đoán:
        # nó chỉ cần `spec_stt` (ghi ngay sau STT, sớm nhất có chữ) chứ không
        # cần RAG hay LLM của bản đoán.
        self._xep_nghi_cau_dem(session)

        n = session.audio_len()
        if session.spec_running:
            if not ngay:
                return
            # Bản giữa chừng đang chạy đã lỗi thời (nó chỉ thấy câu cụt). Huỷ để
            # nhường chỗ. KHÔNG await ở đây - vòng thu tiếng không được nghẽn;
            # bản bị huỷ chưa kịp ghi gì vào phiên vì nó chỉ ghi ở bước cuối.
            if session.spec_task is not None and not session.spec_task.done():
                logger.info("đoán trước: HUỶ bản giữa chừng (đang ở bước %r) "
                            "để đoán lại trên trọn câu",
                            getattr(session, "spec_buoc", "?"))
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
                session.spec_buoc = "STT"
                text = (await self.stt.transcribe(
                    audio, sample_rate=session.audio_rate)).strip()
                # Cất NGAY sau STT, trước mọi bước sau. Hai lý do: (1) đây là
                # khoản đắt nhất còn cắt được khỏi đường găng (212-502ms mỗi
                # lượt), (2) nếu RAG hay LLM bên dưới hỏng/bị huỷ thì phần phiên
                # âm vẫn dùng được - cất ở cuối là mất trắng.
                session.spec_stt = (n, text)
                # Phân loại tình huống ngay tại đây, cùng chỗ và cùng lý do với
                # `spec_stt`: đây là điểm sớm nhất đã có chữ. Không await gì ở
                # đường găng - `_send_filler` đọc được thì dùng, không thì rơi
                # về rổ chung. Cùng triết lý với chính hàm này: đoán trượt thì bỏ.
                try:
                    from backend.main import app_state
                    kho_vec = getattr(app_state, "kho_vector", None)
                    if kho_vec and len(text) >= 4:
                        q = chuan_hoa(self.rag.embed([text]))[0]
                        # Nhóm chê chỉ vào cuộc sau khi bot đã tư vấn chủ đề đó.
                        # Xem `loc_theo_ngu_canh` - điểm cosine giữa hỏi và chê
                        # chỉ cách nhau 0.026 trên câu cụt, chữ không tự cứu được.
                        id_th, diem = chon_tinh_huong(
                            q, kho_vec, nguong=NGUONG_CAU_DEM,
                            bo_qua=loc_theo_ngu_canh(DIEU_KIEN_NGU_CANH,
                                                     session.da_tu_van))
                        if id_th:
                            session.tinh_huong = (n, id_th, diem)
                except Exception as e:
                    logger.debug("phan loai tinh huong truot (bo qua): %s", e)

                # Kho tình huống KHÔNG khớp -> nhờ mô hình nghĩ một câu dẫn.
                #
                # Đây là chỗ duy nhất còn im lặng: đo 06-09-2026 trên cuộc gọi
                # thử, 3/9 lượt không câu nào đạt ngưỡng 0,90 nên không có clip
                # nào để phát, khách nghe im 0,8-2,2 giây.
                #
                # Sinh TRƯỚC câu trả lời (khối LLM bên dưới) vì nó ngắn và cần
                # gấp hơn: câu đệm phải kịp lúc lượt mở, còn câu trả lời thì
                # dù sao cũng có câu đệm che.
                #

                # HÂM CACHE, đường thứ nhất: dùng bản trả lời đã soạn từ lần
                # đoán GIỮA CHỪNG, nếu nó còn khớp phiên âm trọn câu.
                #
                # Cần cả hai đường vì chúng bù nhau: đường này ăn khi khách nói
                # đủ dài để lần đoán giữa chừng kịp soạn xong (`_answer_hit` đòi
                # tối thiểu 4 từ); đường kia - đặt sau khi `spec_answer` của
                # chính lần này có - ăn khi LLM kịp xong trong cửa sổ im lặng.
                # Đo trên cuộc gọi f37bc210: 0/5 lượt LLM kịp xong, nên chỉ có
                # đường kia thôi là không lần nào chạy.
                if ngay and session.spec_answer and self._answer_hit(
                        session.spec_transcript, text):
                    manh_cu = self._manh_dau_ham_cache(
                        session.spec_answer, mo_dau=self._mo_dau_du_doan(session, n))
                    if manh_cu:
                        await self._ham_cache_tts(manh_cu, session)

                if len(text) < 4:
                    return
                rag = ""
                session.spec_buoc = "RAG"
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
                session.spec_buoc = "LLM"
                msgs = history + [{"role": "user", "content": text}]
                answer = ""
                da_ham = False
                async for tok in self.llm.stream_response(msgs, sys_prompt):
                    answer += tok
                    # Dựng tiếng NGAY khi đủ mảnh đầu, đừng đợi trọn câu.
                    #
                    # Đo 06-09-2026 bằng máy đo vòng đời bản đoán: bản nghe được
                    # TRỌN câu luôn bị lượt mở giết khi đang ở bước LLM, vì sinh
                    # trọn câu mất 600-2000ms mà cửa sổ im lặng chỉ 700ms. Nhưng
                    # riêng MẢNH ĐẦU thì kịp: TTFT 265-500ms + gom câu ~150ms.
                    #
                    # Nên tách hai việc: `spec_answer` vẫn cần trọn câu để lượt
                    # sau dùng lại, còn tiếng thì chỉ cần mảnh đầu - và mảnh đầu
                    # chỉ phụ thuộc mấy từ đầu tiên nên tính được sớm.
                    if ngay and not da_ham and len(answer.split()) >= 12:
                        manh_som = self._manh_dau_ham_cache(
                            answer, mo_dau=self._mo_dau_du_doan(session, n))
                        if manh_som:
                            da_ham = True
                            await self._ham_cache_tts(manh_som, session)

                session.spec_transcript = text
                session.spec_rag = rag
                session.spec_answer = answer.strip()

                # Quãng im cuối lượt (nay 1 giây) đang bỏ không, trong khi mảnh
                # đầu tốn 287-472ms SAU khi lượt mở. Sinh trước mảnh đầu để nạp
                # cache; lượt thật phát lại đúng `spec_answer` này nên tra trúng.
                #
                # PHẢI đặt ở đây, sau khi `spec_answer` đã có. Bản đầu tôi đặt
                # ngay sau STT và dùng `spec_answer` CŨ từ lần đoán giữa chừng -
                # lần đó thường chỉ nghe được vài từ ("lãi suất"), mà
                # `_answer_hit` đòi tối thiểu 4 từ, nên khối đó không chạy lần
                # nào. Đo trên cuộc gọi 25fc015e: 0/5 lượt hâm được cache.
                #
                # Chỉ ở lần đoán cuối câu: bản giữa chừng còn đổi liên tục, sinh
                # theo nó là đốt worker cho chữ sắp bị thay.
                #
                # KHÔNG cất tiếng vào phiên, KHÔNG phát. Xem `_ham_cache_tts`.
                if ngay:
                    manh_dau = self._manh_dau_ham_cache(session.spec_answer)
                    if manh_dau:
                        await self._ham_cache_tts(manh_dau, session)
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
                logger.info("đoán trước: BỊ HUỶ ở bước %r - mất trắng công đã làm",
                            getattr(session, "spec_buoc", "?"))
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
    # 900 -> 2000 (08-10). Đo trên 3 lần chạy hội thoại 10 lượt: TTFA đường chat
    # là 678-1978ms, trung vị ~1280. Để 900 thì lượt ĐẦU luôn chọn câu đệm quá
    # ngắn - đo được câu đệm 1,20s cho TTFA 1674ms, khách nghe hụt 474ms im lặng
    # ngay câu đầu tiên. Nay `mac_dinh` còn là SÀN cho mọi lượt, không chỉ lượt
    # đầu - xem `filler_pick.can_che_ms`.
    _FILLER_MIN_CHAT_MS = 2000.0

    # Luật và số đo nằm ở `filler_pick.NGUONG_BO_DEM_MS` - cùng chỗ với
    # `du_doan_cho_ms`, thứ nó được đem ra so sánh. Để hai đại lượng đó xa nhau
    # chính là cách bản cũ hỏng: ngưỡng 700 so với `can_che_ms` (sàn 1800) nên
    # không bao giờ kích hoạt, mã chết suốt một tháng mà log vẫn sạch.
    _FILLER_BO_QUA_MS = NGUONG_BO_DEM_MS

    # Chờ tối đa bấy nhiêu để câu đệm LLM thành tiếng. Bình thường nó đã nằm sẵn
    # trong cache (dựng lúc khách còn nói) nên gần như 0ms; trần này chỉ để chặn
    # ca xấu - worker F5 đang bận nên `_ham_cache_tts` đã bỏ qua, và đây phải
    # sinh thật. Thà im như trước còn hơn đẩy lùi chính câu trả lời.
    _CHO_CAU_DEM_LLM_MS = 400.0

    # Chờ tối đa bấy nhiêu để task nghĩ câu đệm SINH XONG CHỮ (khác
    # `_CHO_CAU_DEM_LLM_MS` ở trên - cái đó chờ chữ thành TIẾNG).
    #
    # Cái giá: 3 lượt hiện im lặng sẽ đẩy câu trả lời thật lùi tối đa 300ms.
    # Đáng, vì chính 3 lượt đó đang để khách nghe im 1,7-3,2 giây.
    #
    # Chỉ chờ khi task đang chạy thật (`_cau_dem_dang_nghi`), nếu không thì mọi
    # lượt không có câu đệm đều mất trắng 300ms.
    _CHO_SINH_CAU_DEM_MS = 300.0

    # Chờ tối đa bao nhiêu ms để speculate._run() hoàn thành STT và phân loại
    # tình huống. Đặt 0 để tắt hoàn toàn.
    # NGOẠI LỆ có chủ đích: ràng buộc "không thêm await vào _send_filler" tồn tại
    # để bảo vệ TTFA; một lần chờ CÓ TRẦN CỨNG là đánh đổi đã đo, khác hẳn chờ vô hạn.
    #
    # 150 -> 650 (06-09-2026). Số cũ chốt ngày 11-08 khi chỉ nhìn "câu đệm che
    # ~1800ms nên mất 150ms vẫn còn 1650ms" - đúng về phía TTFA nhưng KHÔNG hề
    # so với thứ nó đang đợi. Ngân sách thật cho STT là:
    #
    #     (SILENCE_END_MS - SPEC_CUOI_MS) + _CHO_TINH_HUONG_MS
    #      = quãng bản đoán cuối câu được chạy trước khi lượt bắt đầu, cộng chờ
    #
    # Máy đang chạy để PHONE_SILENCE_END_MS=500 và SPEC_CUOI_MS=300, tức chỉ
    # 200 + 150 = 350ms. Chín lần phiên âm đoán trước trên cuộc gọi thật sáng
    # 06-09 mất 178/230/306/375/426/449/520/621/829ms - SÁU lần vượt 350ms, và
    # mỗi lần vượt là một lượt ghi "chưa có spec_stt" rồi rơi về rổ chung.
    # 650 phủ hết dải đo được (200 + 650 = 850 >= 829).
    #
    # Đây là TRẦN, không phải quãng chờ cố định: `asyncio.wait` về ngay khi bản
    # đoán xong, nên lượt STT nhanh vẫn phát câu đệm sớm như cũ. Giá chỉ trả ở
    # đúng những lượt trước đây mất trắng tình huống.
    #
    # 650 -> 200 (07-09-2026). LÝ DO CŨ VẪN ĐÚNG Ở THỜI ĐIỂM ĐÓ: lúc chốt 650,
    # `PHONE_SILENCE_END_MS` đang là 500 nên đà chạy trước chỉ 200ms, phải chờ
    # thêm 629ms mới phủ nổi STT 829ms. Cùng ngày hôm ấy `PHONE_SILENCE_END_MS`
    # nâng 500 -> 750 -> 1000 vì lý do khác hẳn (câu khách bị chẻ đôi), và điều
    # đó lặng lẽ làm 650 thành thừa - chính công thức ngay trên đây:
    #
    #     nay:  (1000 - 300) + 200 = 900ms  >= 829ms   còn dư 71ms
    #     cũ:   (1000 - 300) + 650 = 1350ms >= 829ms   dư 521ms
    #
    # Vì sao 521ms đó ĐẮT chứ không chỉ là thừa: `_send_filler` là await ĐẦU TIÊN
    # của `process_turn`, nên chờ ở đây chặn CẢ CÂU TRẢ LỜI THẬT chứ không riêng
    # câu đệm. Đo trên cuộc gọi 08c0d3e0 (07-09): 3/10 lượt câu đệm ra muộn
    # 555/796/867ms, cộng cửa sổ im 1000ms là khách nghe 1,5-1,9 GIÂY im lặng
    # hoàn toàn trước khi có tiếng nào. Đó cũng là ô "khác" phình to trong bảng
    # bóc tách TTFA (111-1293ms, trung vị ~530ms).
    #
    # STT nay còn nhanh hơn dải cũ: 77 lần đo trong logs/backend.log cho trung vị
    # 313ms, p90 482ms, max 557ms - nằm gọn trong đà 700ms, chưa cần tới ô chờ.
    # Vẫn giữ 200 chứ không hạ về 0: dải 829ms cũ đo trên máy thật và không có gì
    # bảo đảm nó không lặp lại khi GPU bận.
    #
    # 200 -> 250 (07-09-2026, cùng ngày, ít giờ sau). KHÔNG phải đảo ngược quyết
    # định trên: `PHONE_SILENCE_END_MS` hạ 1000 -> 900 để đạt mốc "khách nói xong
    # AI trả lời trong 1s", nên đà chạy trước tụt từ 700 còn 600ms và công thức
    # đòi bù lại 29ms. Lấy 250 cho tròn:
    #
    #     (900 - 300) + 250 = 850ms >= 829ms   dư 21ms
    #
    # Chính lưới canh chéo bắt được chuyện này ngay khi đổi `.env` - đó là việc
    # nó sinh ra để làm.
    #
    # 250 -> 430 (08-09-2026). Lại KHÔNG phải đảo ngược: `PHONE_SILENCE_END_MS`
    # hạ 900 -> 750 -> 700 theo yêu cầu bên A, đà chạy trước tụt từ 600 còn 400ms
    # nên công thức đòi bù 180ms. Lưới canh bắt được ngay khi đổi `.env` - lần
    # thứ hai nó làm đúng việc nó sinh ra để làm.
    #
    #     (700 - 300) + 430 = 830ms >= 829ms   dư 1ms
    #
    # Vì sao nâng trần chứ không hạ `SPEC_CUOI_MS`: đây là TRẦN chứ không phải
    # quãng chờ cố định, lượt STT nhanh thoát ngay và không trả giá gì. Hạ
    # `SPEC_CUOI_MS` thì ngược lại - bản đoán bị bắn khi khách mới im 100ms, tức
    # phiên âm chạy trên đoạn tiếng CỤT ĐUÔI ở MỌI lượt, kể cả lượt đang nhanh.
    #
    # Số 829ms vẫn giữ dù STT đo lại 08-09 trên 44 lượt chỉ cho trung vị 244ms,
    # p95 434ms, max 527ms: dòng "STT ...ms" trong log đo đường phiên âm chính,
    # còn 829ms đo đúng phiên âm ĐOÁN TRƯỚC - hai đại lượng khác nhau, chưa có
    # cơ sở đem cái này thay cái kia.
    #
    # Ràng buộc chéo ba hằng số này có test canh (CẢ HAI CHIỀU - thiếu và thừa):
    # tests/test_ngan_sach_cho_tinh_huong.py
    _CHO_TINH_HUONG_MS: int = 430

    def _filler_min_ms(self, session: CallSession, la_thoai: bool, mac_dinh: float) -> float:
        """Xem `filler_pick.can_che_ms` - luật nằm ở đó để test được không cần GPU."""
        return can_che_ms(session.latency_log, la_thoai, mac_dinh)

    def _phan_loai_dong_bo(self, session: CallSession):
        """Phân loại tình huống ĐỒNG BỘ từ spec_stt đã có, không await (~10ms).

        Gọi trước _send_filler khi audio_end vừa kích hoạt speculate(ngay=True)
        nhưng task đó chưa hoàn thành STT (200-500ms) trước khi _send_filler đọc
        session.tinh_huong. Dùng spec_stt từ lần đoán trung gian cuối cùng đã
        hoàn thành.

        Không ghi đè nếu tinh_huong đã có: tôn trọng kết quả của speculate nền.
        Không ném ngoại lệ: lỗi bất kỳ → rơi về rổ chung (đúng hành vi xuống cấp).
        """
        if session.tinh_huong:
            return
        if not session.spec_stt:
            # Đây là một trong hai đường làm `tinh_huong` rỗng suốt - ghi ra để
            # lần sau khỏi phải đoán. Đo 06-09-2026: `tinh_huong_id` RỖNG ở
            # 11/11 lượt trên hai cuộc gọi thật, nên câu đệm luôn rơi về rổ
            # chung ("em tra lại thông tin rồi báo lại") kể cả khi khách hỏi
            # thẳng lãi suất.
            logger.info("tình huống: KHÔNG phân loại được - chưa có spec_stt")
            return
        try:
            from backend.main import app_state
            kho_vec = getattr(app_state, "kho_vector", None)
            n_stt, text_stt = session.spec_stt
            if not (kho_vec and text_stt and len(text_stt) >= 4):
                logger.info("tình huống: bỏ - kho_vector=%s, chữ đoán trước=%r",
                            "có" if kho_vec else "KHÔNG", (text_stt or "")[:40])
                return
            q = chuan_hoa(self.rag.embed([text_stt]))[0]
            id_th, diem = chon_tinh_huong(
                q, kho_vec, nguong=NGUONG_CAU_DEM,
                bo_qua=loc_theo_ngu_canh(DIEU_KIEN_NGU_CANH, session.da_tu_van))
            if id_th:
                session.tinh_huong = (n_stt, id_th, diem)
                logger.info("tình huống: %r (điểm %.3f) từ %r",
                            id_th, diem or 0.0, (text_stt or "")[:40])
            else:
                logger.info("tình huống: KHÔNG câu nào đạt ngưỡng %.2f - chữ %r",
                            NGUONG_CAU_DEM, (text_stt or "")[:40])
        except Exception as e:
            logger.debug("phan loai tinh huong dong bo (bo qua): %s", e)

    # Dấu kết câu. Mảnh KHÔNG kết bằng một trong số này thì câu còn dang dở,
    # và mảnh kế phải nối tiếp chứ không được mở câu mới.
    _DAU_KET = (".", "?", "!", "…")

    @staticmethod
    def _con_dang_do(manh: str) -> bool:
        """Mảnh vừa phát có bỏ lửng câu không?"""
        t = (manh or "").strip()
        return bool(t) and not t.endswith(StreamingPipeline._DAU_KET)

    @staticmethod
    def _cau_thay_the(cau: str, dang_do: bool) -> str:
        """Câu lưới chặn vừa chèn, đã chỉnh cho ghép được với mảnh trước."""
        return noi_tiep_ve_dang_do(cau) if dang_do else cau

    # Vốn từ nghiệp vụ, dựng MỘT LẦN rồi giữ. Dựng mỗi lượt là quét lại toàn bộ
    # kho tri thức ngay trên đường găng độ trễ.
    _von_tu: frozenset[str] | None = None

    def _von_tu_nghiep_vu(self) -> frozenset[str]:
        """Mọi chữ có thật trong tài liệu + ví dụ tình huống.

        Hỏng thì trả rỗng chứ không ném: `loc_cau_dem_llm` coi vốn từ rỗng là
        "chưa biết" và giữ nguyên hành vi cũ - thà phát câu đệm như trước còn
        hơn im lặng vì một chỗ phụ trợ lỗi.
        """
        if StreamingPipeline._von_tu is not None:
            return StreamingPipeline._von_tu
        doan: list[str] = []
        try:
            doan += list(self.rag._collection.get().get("documents") or [])
        except Exception as e:
            logger.warning("không đọc được tri thức để dựng vốn từ: %s", e)
        try:
            for t in lay_kho().tinh_huong:
                doan += list(t.vi_du or ())
                doan += list(t.mo_dau or ())
        except Exception as e:
            logger.warning("không đọc được kho tình huống để dựng vốn từ: %s", e)
        StreamingPipeline._von_tu = tu_vung_tu_kho(doan)
        logger.info("Vốn từ nghiệp vụ cho câu đệm: %d chữ",
                    len(StreamingPipeline._von_tu))
        return StreamingPipeline._von_tu

    @staticmethod
    def _nghi_noi_cau_dem(metrics: dict) -> float:
        """Nhịp nghỉ phải chèn ở chỗ nối CÂU ĐỆM -> nội dung, tính bằng ms.

        Câu đệm luôn kết bằng dấu phẩy, mà dự án đã đo ra F5 LỜ dấu phẩy nên mọi
        ranh giới phẩy đều được `nhip_nghi_sau` chèn quãng nghỉ. Riêng ranh giới
        này sót, vì vòng phát khởi tạo `nghi_ms = 0.0` và cố ý không chèn vào
        mảnh ĐẦU để giữ TTFA - mà câu đệm thì đứng ngay trước mảnh đầu.

        Hậu quả đo trên cuộc 08c0d3e0: 7/9 chỗ nối có ĐÚNG 0ms lặng, mức 300ms
        hai bên nhảy +3,0 đến +5,0 dB. Người dùng nghe ra: "đè lên từ phía trước,
        tiếng to hơn nghe rất giả".

        CHỈ chèn khi câu đệm CÒN ĐANG PHÁT. Cùng bản ghi có 2/9 lượt `ĐÓI KHUNG`
        (216ms, 287ms) - câu đệm hết trước khi nội dung tới, khách đang nghe
        khoảng lặng thật. Chèn thêm ở đó là kéo dài đúng chỗ đang hỏng, nên mốc
        `filler_xong_luc` là điều kiện bắt buộc chứ không phải để cho chặt.

        Dùng lại `nhip_nghi_sau` chứ không đẻ hằng số mới: cùng một luật với mọi
        ranh giới khác, nên câu đệm đổi sang kết bằng dấu chấm là tự nghỉ dài hơn.
        """
        xong = metrics.get("filler_xong_luc")
        chu = metrics.get("filler_text") or ""
        if not xong or not chu:
            return 0.0
        if time.perf_counter() >= xong:
            return 0.0
        return nhip_nghi_sau(chu)

    async def _send_filler(self, ws: WebSocket, session: CallSession, t_start: float,
                           metrics: dict, la_thoai: bool, n_audio: int = 0):
        """Phát câu đệm đã dựng sẵn NGAY - đây mới là lúc AI bắt đầu nói theo tai khách.

        Phải là await ĐẦU TIÊN của lượt: audio đã nằm sẵn trong cache từ lúc khởi
        động (dung_fillers) nên không tốn GPU, chỉ tốn thời gian gửi.

        `n_audio` = tổng byte audio của lượt, dùng để tính độ phủ bản phân loại.
        Truyền từ `process_turn` (len(audio_bytes)); mặc định 0 → đường chat gõ
        chữ, không có audio → bỏ qua phân loại tình huống.

        ttfa_ms bên dưới đo tới mảnh THẬT đầu tiên và bỏ qua hoàn toàn filler,
        nên nhìn một mình ttfa_ms sẽ tưởng khách phải chờ im lặng lâu hơn thực tế.
        """
        # Vừa đọc nốt phần câu cũ khách chưa nghe (đường thoại đặt cờ này
        # trong `PhoneCallBridge._handle_turn`): quãng chờ đã được che rồi, phát
        # thêm câu đệm là hai đoạn dạo đầu liên tiếp.
        if getattr(session, "da_doc_not", False):
            session.da_doc_not = False
            metrics["filler_bo_qua"] = "vua doc not cau do"
            return

        can_che = self._filler_min_ms(
            session, la_thoai,
            self._FILLER_MIN_THOAI_MS if la_thoai else self._FILLER_MIN_CHAT_MS,
        )

        # BỎ câu đệm khi đường này gần đây vốn đã nhanh - khoảng lặng ngắn nghe
        # tự nhiên hơn hẳn một câu "Dạ vâng ạ" chèn vào.
        #
        # `spec_answer` (đã nghĩ sẵn câu trả lời) KHÔNG được tự nó quyết. Giả
        # định cũ "có bản nghĩ sẵn thì câu thật tới gần như tức thì" SAI - đo
        # trên ba cuộc gọi thật: đúng những lượt dùng bản nghĩ sẵn lại là lượt
        # khách nghe im lặng LÂU NHẤT (947ms, 1295ms, 1739ms), vì chỉ chúng bị
        # bỏ câu đệm. Nghĩ sẵn mới bỏ được khâu sinh chữ (~220ms); STT bản cuối
        # và TTS mảnh đầu vẫn còn, và đó mới là phần lớn. Nên nó chỉ đổi CHỮ ghi
        # vào metrics, còn quyết định thì để số đo lo.
        #
        # `du_doan` KHÁC `can_che`: nó không có sàn 1800/2000ms, nên nói được sự
        # thật "đường này đang chạy 300ms". Dùng `can_che` ở đây là lý do hai
        # nhánh dưới chưa từng chạy suốt từ 08-2026 - xem `_FILLER_BO_QUA_MS`.
        #
        # None = lượt ĐẦU, chưa có số đo nào. Không biết thì PHẢI phát: lượt đầu
        # là lượt chậm nhất cuộc gọi (tra hồ sơ nguội, đo được TTFA 8026ms).
        du_doan = du_doan_cho_ms(session.latency_log, la_thoai)
        if du_doan is not None and du_doan < self._FILLER_BO_QUA_MS:
            metrics["filler_bo_qua"] = (
                f"đã nghĩ sẵn + nhanh sẵn ({du_doan:.0f}ms)" if session.spec_answer
                else f"nhanh sẵn ({du_doan:.0f}ms)")
            metrics["du_doan_cho_ms"] = round(du_doan)
            return

        kho = lay_kho()

        # --- VIỆC 1 (task-11d): Chờ phiên âm tạm để có tình huống chính xác -----
        # speculate(ngay=True) chạy trong task nền khi khách vừa ngừng tiếng.
        # STT tốn 200-500ms — thường xong sau khi _send_filler được gọi, nên
        # tinh_huong chưa được ghi. Chờ tối đa _CHO_TINH_HUONG_MS để task đó hoàn
        # thành, sau đó thử _phan_loai_dong_bo lần nữa nếu vẫn thiếu.
        #
        # Dùng asyncio.wait() (KHÔNG phải wait_for()): wait() không huỷ task khi
        # hết hạn, nên speculate._run() tiếp tục chạy để phục vụ RAG/LLM/answer_hit
        # bên dưới. Đây là lý do chọn wait() thay vì shield()+wait_for().
        # Ghi thời gian chờ thật vào metrics để đo cái giá thực tế.
        if self._CHO_TINH_HUONG_MS > 0 and n_audio > 0 and session.tinh_huong is None:
            # CHỜ chỉ khi task đoán trước còn đang chạy...
            if session.spec_task is not None and not session.spec_task.done():
                # Chờ tới khi CÓ TÌNH HUỐNG, không phải tới khi tác vụ xong.
                # Tác vụ còn làm RAG + LLM soạn sẵn sau khi đã chấm xong tình
                # huống; chờ theo tác vụ là đốt trọn ngân sách cho hai việc câu
                # đệm không dùng. Đo trên cuộc gọi thật: ngân sách 650ms thì lần
                # nào cũng chờ 745-754ms, trong khi phiên âm chỉ mất 297-365ms.
                #
                # Ba lối thoát, lối nào tới trước cũng dừng:
                #   - đã có tình huống          -> thứ ta cần, xong
                #   - `spec_stt` đã đổi          -> phiên âm cuối câu về rồi mà
                #     vẫn không ra tình huống, chờ thêm cũng vô ích
                #   - tác vụ xong/biến mất       -> không còn gì để đợi
                _moc_stt = session.spec_stt

                def _xong() -> bool:
                    t = session.spec_task
                    return (session.tinh_huong is not None
                            or session.spec_stt is not _moc_stt
                            or t is None or t.done())

                metrics["tinh_huong_cho_ms"] = round(
                    await cho_den_khi(_xong, self._CHO_TINH_HUONG_MS))
            # ...nhưng LUÔN thử phân loại nếu vẫn chưa có.
            #
            # Bản cũ đặt `_phan_loai_dong_bo` BÊN TRONG điều kiện "task chưa
            # xong", nên hai đường phổ biến nhất đều lọt: task đã xong mà chưa
            # kịp phân loại, và task chưa từng được tạo (khách nói một câu ngắn,
            # `speculate` không kịp chạy). Hậu quả đo được trên hai cuộc gọi
            # thật và một lượt chạy lại bằng tiếng khách thật: `tinh_huong_id`
            # RỖNG ở 11/11 lượt, tức bộ phân loại chưa từng cho ra kết quả nào -
            # câu đệm luôn rơi về rổ chung ("em tra lại thông tin rồi báo lại")
            # kể cả khi khách hỏi thẳng lãi suất hay hạn mức.
            if session.tinh_huong is None:
                self._phan_loai_dong_bo(session)

        # n_audio được truyền vào từ process_turn (len(audio_bytes)). Trước đây
        # đọc session.audio_len() tại đây nhưng take_audio() đã làm sạch đệm
        # trước khi _send_filler chạy, nên luôn trả về 0. Kết quả: do_phu = n_th / 1
        # (một số rất lớn), điều kiện >= ngưỡng LUÔN ĐÚNG, và luật độ phủ trở
        # thành mã chết không chặn được gì. Nay dùng tham số truyền vào.
        # n_audio = 0 trên đường chat (không audio) → bỏ qua phân loại hoàn toàn.
        # Luật nằm ở `filler_pick.tinh_huong_dung` để test được không cần GPU -
        # cùng lý do với `can_che_ms`. Ở đó có bảng số đo vì sao BỎ lưới độ phủ.
        id_th, do_phu = tinh_huong_dung(session.tinh_huong, n_audio)
        if do_phu is not None:
            metrics["tinh_huong_do_phu"] = round(do_phu, 3)
            metrics["tinh_huong_diem"] = round(session.tinh_huong[2], 3)

        # Không nhận ra tình huống -> THÔI, đừng phát rổ chung. Xem
        # `filler_pick.nen_bo_cau_dem` cho cái giá đã đo của quyết định này.
        if nen_bo_cau_dem(id_th, n_audio > 0):
            metrics["filler_bo_qua"] = "khong ro tinh huong"
            return

        # Khách vừa HỎI thì "em nắm được rồi" nghe như gạt đi. Nay đọc CHÍNH
        # phiên âm dở thay vì suy từ `session.turn_count` như trước: spec_stt có
        # chữ thật, không phải suy đoán từ lượt trước.
        duoi = list(kho.duoi)
        chu = (session.spec_stt or (0, ""))[1].lower()
        if "?" in chu or any(t in chu for t in
                             ("bao nhiêu", "thế nào", "gì", "à", "không ạ")):
            duoi = [d for d in duoi if d.hop_cau_hoi] or duoi

        dem = getattr(session, "dem_filler", None)
        if dem is None:
            dem = session.dem_filler = {}

        # `chi_duoi=None` khi kho đuôi RỖNG, không phải set rỗng: set rỗng đi
        # qua `k[3] in chi_duoi` là loại SẠCH ứng viên, kể cả clip "chỉ mẩu mở
        # đầu" (id_duoi="") vừa dựng - câu đệm biến mất hoàn toàn mà log vẫn
        # sạch. Người dùng bỏ hẳn kho đuôi 06-09-2026 nên đây là đường thật.
        filler_audio, id_duoi, th_dung = self.tts.pick_filler(
            kho, session.voice_name, min_ms=can_che, dem=dem,
            id_tinh_huong=id_th, chi_duoi={d.id for d in duoi} or None,
        )
        if not filler_audio:
            # Kho không có gì hợp -> dùng câu đệm mô hình đã nghĩ trong lúc
            # khách nói. Đây là lượt vốn im lặng hoàn toàn (đo 06-09: 3/9 lượt).
            #
            # `synthesize` tra cache theo nguyên văn chữ, mà `_nghi_cau_dem` đã
            # dựng sẵn đúng chuỗi này - nên gần như 0ms. Chưa dựng kịp thì rơi
            # vào sinh thật; bọc trong `wait_for` để nó KHÔNG BAO GIỜ đẩy lùi
            # câu trả lời: thà im như trước còn hơn nói muộn.
            # Chờ task nghĩ câu đệm nếu nó ĐANG chạy. Đo 06-09-2026: câu đệm
            # sinh được và dựng tiếng xong ("Dạ về số lượng anh còn nợu,") nhưng
            # xong SAU lúc lượt mở, nên nhánh này đọc phải chuỗi rỗng rồi bỏ đi.
            #
            # `_cau_dem_dang_nghi` là điều kiện then chốt: không có nó thì mọi
            # lượt không-có-câu-đệm đều đứng chờ trọn 300ms một thứ không bao giờ
            # tới - tức trì hoãn chính câu trả lời ở đúng những lượt đã chậm nhất.
            if not session.spec_cau_dem and getattr(session, "_cau_dem_dang_nghi", False):
                metrics["cau_dem_llm_cho_ms"] = round(await cho_den_khi(
                    lambda: bool(session.spec_cau_dem), self._CHO_SINH_CAU_DEM_MS))
            cau = session.spec_cau_dem
            if not cau:
                return
            try:
                wav = await asyncio.wait_for(
                    self._try_synthesize(cau, fast=True, voice=session.voice_name,
                                         session=session),
                    timeout=self._CHO_CAU_DEM_LLM_MS / 1000)
            except Exception as e:
                # Gồm cả TimeoutError (từ 3.11 nó là subclass của Exception).
                logger.info("câu đệm LLM không kịp thành tiếng (%s), bỏ qua",
                            type(e).__name__)
                return
            if not wav:
                return
            await self._send_audio(ws, wav, is_filler=True, turn_id=session.turn_id)
            metrics["filler_ms"] = round((time.perf_counter() - t_start) * 1000)
            # Lúc câu đệm phát xong, để `_nghi_noi_cau_dem` biết chỗ nối còn
            # được che hay đã thành khoảng lặng thật.
            metrics["filler_xong_luc"] = time.perf_counter() + dai_wav_ms(wav) / 1000.0
            metrics["filler_text"] = cau
            metrics["filler_id"] = "llm"
            metrics["tinh_huong_id"] = None
            return
        await self._send_audio(ws, filler_audio, is_filler=True,
                               turn_id=session.turn_id)
        metrics["filler_ms"] = round((time.perf_counter() - t_start) * 1000)
        metrics["filler_xong_luc"] = (time.perf_counter()
                                      + dai_wav_ms(filler_audio) / 1000.0)
        # NGUYÊN VĂN chữ vừa phát, do `pick_filler` trả kèm clip. Phải là chữ
        # THẬT chứ không phải nhãn: `prefill` nhét chuỗi này vào miệng mô hình để
        # nó viết tiếp, mà bản cũ suy chữ từ `id_duoi` nên khi kho đuôi rỗng nó
        # ghi nhãn "(chỉ mẩu mở đầu)" - prefill thành vô nghĩa và mô hình viết
        # câu mới. Đo 06-09-2026: "Dạ về hạn mức vay thì, Hạn mức vay tín chấp
        # tối đa lên đến 500 triệu đồng ạ" - lặp nguyên chủ đề.
        metrics["filler_text"] = getattr(self.tts, "_filler_text_cuoi", "") or ""
        metrics["filler_id"] = id_duoi
        # th_dung là tình huống ĐÃ DÙNG THẬT (None khi rơi về đuôi trần), khác
        # với id_th (tình huống ĐOÁN ĐƯỢC). Ghi đúng cái đã dùng để đối soát log.
        metrics["tinh_huong_id"] = th_dung

    async def process_turn(self, audio_bytes: bytes, session: CallSession, ws: WebSocket):
        """Full pipeline: Audio -> STT -> RAG -> LLM -> TTS -> Audio."""
        t_start = time.perf_counter()
        # Ghi THẲNG đường nào, đừng để `can_che_ms` phải suy từ stt_ms: lượt
        # dùng lại bản phiên âm đoán trước có stt_ms = 0, suy ra sẽ thành
        # "đường chat" và lịch sử thoại mất đúng những lượt nhanh nhất.
        metrics = {"la_thoai": True}

        # Đường dự phòng phân loại tình huống cho đường chat-audio: speculate(ngay=True)
        # được gọi ngay trước lượt (trong audio_end) nhưng task đó chưa hoàn thành
        # STT khi _send_filler đọc session.tinh_huong. Nếu tinh_huong chưa có nhưng
        # spec_stt đã có phiên âm từ lần đoán trung gian, phân loại ĐỒNG BỘ ~10ms
        # (không await) để _send_filler có dữ liệu đọc. Xem _phan_loai_dong_bo.
        self._phan_loai_dong_bo(session)

        await self._send_filler(ws, session, t_start, metrics, la_thoai=True,
                                n_audio=len(audio_bytes))

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
            # KHÔNG RA CHỮ -> HỎI LẠI, đừng im. Bản cũ chỉ gửi sự kiện lỗi rồi
            # đóng lượt: khách nói mà không được đáp gì, nghe như máy đã chết.
            # Đây là chỗ DUY NHẤT còn được phép chủ động mở lời, sau khi bỏ cơ
            # chế nhắc theo im lặng (xem `pipeline/hoi_lai.py`).
            so_lan = getattr(session, "so_lan_khong_nghe_ro", 0)
            await self._send_event(ws, "error", {"message": "Không nhận dạng được giọng nói"})
            cau = ""
            if nen_hoi_lai(so_lan):
                cau = chon_cau_hoi_lai(so_lan)
                try:
                    wav = await self.tts.synthesize(
                        cau, voice=getattr(session, "voice_name", None) or "default")
                    await self._send_event(ws, "audio", {
                        "data": base64.b64encode(wav).decode()})
                    logger.info("Không ra chữ (lần %d liên tiếp) -> hỏi lại: %r",
                                so_lan + 1, cau)
                except Exception as e:
                    # Hỏi lại hỏng thì cuộc gọi vẫn phải chạy tiếp.
                    logger.warning("Không phát được câu hỏi lại (bỏ qua): %s", e)
                    cau = ""
            else:
                logger.info("Không ra chữ lần %d liên tiếp - thôi không hỏi nữa",
                            so_lan + 1)
            session.so_lan_khong_nghe_ro = so_lan + 1
            await self._send_event(ws, "turn_complete",
                                   {"full_response": cau,
                                    "metrics": {"khong_ra_chu": so_lan + 1}})
            return

        # Nghe được chữ -> bộ đếm "không ra chữ" về 0. Phải đếm LIÊN TIẾP, dồn
        # cả cuộc gọi thì một cuộc dài bình thường cũng chạm trần rồi câm.
        session.so_lan_khong_nghe_ro = 0

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

    async def process_text_turn(self, text: str, session: CallSession, ws: WebSocket,
                                soi: bool = False, la_thoai: bool = False):
        """Text-only turn (skip STT).

        `la_thoai=True`: chữ đã có sẵn nhưng lượt này VẪN thuộc đường ĐIỆN THOẠI
        (câu bị cắt lời còn treo - xem `viec_cho_doan_ngan`). Phải ghi đúng cờ,
        nếu không `can_che_ms` xếp nó vào lịch sử đường CHAT và ước lượng sai độ
        dài câu đệm cho các lượt thoại sau.

        `soi=True` là chế độ SOI của trang Nhắn tin: đi trọn vòng nghiệp vụ như
        thường (lượt thường gặp, tra hồ sơ, RAG, LLM, lưới chặn số) nhưng bỏ câu
        đệm và bỏ sinh tiếng, đồng thời ghi thêm dấu vết chẩn đoán vào `metrics`.
        Mặc định `False` để đường thoại và trang Hội thoại không đổi hành vi.
        """
        t_start = time.perf_counter()
        metrics = {"stt_ms": 0, "la_thoai": la_thoai}

        # Đường chat trước đây KHÔNG có filler: khách gõ xong bấm gửi rồi ngồi im
        # 1.2-1.4 giây (đo thật) mới nghe tiếng, trong khi gọi điện thì nghe ngay.
        # Cùng một pipeline, chỉ thiếu đúng dòng này.
        #
        # Chế độ soi bỏ câu đệm: nó chỉ có nghĩa khi khách đang CHỜ TIẾNG. Soi thì
        # không phát tiếng, câu đệm chỉ tổ chen một dòng lạ vào giữa hội thoại và
        # tốn một lần đọc kho filler.
        if not soi:
            await self._send_filler(ws, session, t_start, metrics, la_thoai=False)

        if session.cau_bi_cat:
            truoc = session.cau_bi_cat
            text = session.ghep_cau_bi_cat(text)
            logger.info("Ghép câu bị cắt: '%s' + câu mới -> '%s'", truoc, text)
            metrics["ghep_cau_bi_cat"] = truoc

        session.add_turn("user", text)
        await self._send_event(ws, "transcript", {"text": text, "latency_ms": 0})

        await self._generate_response(text, session, ws, t_start, metrics, soi=soi)

    async def _generate_response(self, user_text: str, session: CallSession, ws: WebSocket,
                                 t_start: float, metrics: dict, soi: bool = False):
        """Shared logic: RAG -> LLM streaming -> optional TTS.

        `soi=True`: xem `process_text_turn`. Chỉ đường chữ dùng tới.
        """
        # Chụp lại bản đoán RỒI dọn ngay: dọn muộn thì đoạn LLM bên dưới đọc phải
        # ô đã bị xoá, còn dọn thiếu thì lượt sau dùng nhầm bản nghĩ của lượt này.
        spec_transcript = session.spec_transcript
        spec_rag = session.spec_rag
        spec_answer = session.spec_answer
        logger.info("lượt mở: bản nghĩ sẵn %s (bản đoán đang ở bước %r)",
                    "CÓ" if spec_answer else "KHÔNG",
                    getattr(session, "spec_buoc", "?"))
        # Chốt tốc đọc TRƯỚC khi dọn: `clear_speculation()` xoá `tinh_huong`,
        # mà tốc riêng theo tình huống lấy từ đó. Xem `_toc_cho_phien`.
        self._chot_toc_doc(self.tts, session, session.voice_name)
        session.clear_speculation()

        # Lượt thường gặp (chào máy, "ai đấy", "đang bận", từ chối...) trả lời
        # bằng bảng có sẵn, KHÔNG qua mô hình - đo được mô hình đóng khuôn
        # 5/10 lượt loại này. Xem `luot_thuong_gap` cho số liệu và lý do.
        # Tên tổ chức/nhân viên lấy từ KỊCH BẢN của phiên, không phải `.env`.
        # Đường LLM đã đọc từ kịch bản (`llm_service.build_system_prompt`), nên
        # để chỗ này đọc `.env` là hai đường xưng tên KHÁC NHAU trong cùng một
        # cuộc: câu chào sẵn nói một tên, câu do mô hình sinh nói tên khác.
        dap_san = tra_loi_san(
            user_text,
            bank=scenarios_db.ten_to_chuc(session.scenario),
            agent=scenarios_db.ten_nhan_vien(session.scenario),
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
        # TRỌN tài liệu sản phẩm + FAQ, thay cho hai mảnh RAG. Nhiều chữ hơn mà
        # TTFT thấp hơn (100ms -> 28ms) vì tài liệu đứng yên suốt cuộc gọi nên
        # cache tiền tố giữ được, còn mảnh RAG đổi mỗi lượt thì phá cache. Số đo
        # ở `config.ngu_canh_tron_tai_lieu` và `tests/test_ngu_canh_tai_lieu.py`.
        #
        # Đặt SAU nhánh `dap_san` (lượt đó cố ý không cần ngữ cảnh) và TRƯỚC
        # nhánh đoán trước: có tài liệu rồi thì bản đoán chẳng tiết kiệm được gì.
        # Khách vừa nhắc sản phẩm nào thì NHỚ cho cả cuộc gọi. Phải đứng TRƯỚC
        # `_toan_van_tai_lieu` ngay dưới, không thì lượt vừa neo được vẫn dùng
        # tài liệu của neo cũ. Xem `RAGService.neo_moi_tu_cau` cho ca thật.
        try:
            ten_sp = self.rag.neo_moi_tu_cau(
                user_text, self.rag._san_pham_co_tai_lieu())
            if ten_sp and ten_sp != session.product:
                logger.info("Neo sản phẩm theo lời khách: %r -> %r",
                            session.product, ten_sp)
                session.product = ten_sp
                metrics["neo_san_pham"] = ten_sp
        except Exception as e:
            # Đường phụ trợ: hỏng thì giữ nguyên neo cũ, đừng làm chết cả lượt.
            logger.warning("Không neo được sản phẩm (%s)", e)

        # "bên em có những sản phẩm gì / có bảo hiểm không": danh mục là dữ kiện
        # xác định (kho có tài liệu nào thì bán sản phẩm đó), không để mô hình
        # đoán - nhất là sản phẩm KHÔNG có, mô hình dễ nói "có" rồi bịa.
        # Xem `danh_muc_san_pham`.
        if not dap_san:
            try:
                got = tra_loi_danh_muc(
                    user_text, self.rag._san_pham_co_tai_lieu(),
                    hoi_them=not (session.product or "").strip())
            except Exception as e:
                logger.warning("Không tra được danh mục sản phẩm (%s)", e)
                got = None
            if got:
                dap_san = got
                metrics["tra_tu_danh_muc"] = got[0]
                logger.info("Danh mục sản phẩm '%s' -> trả lời xác định, bỏ qua RAG+LLM",
                            got[0])

        tron_tai_lieu = (_toan_van_tai_lieu(session.product)
                         if settings.ngu_canh_tron_tai_lieu else "")
        if dap_san:
            # Câu trả lời sẵn không có con số nào phải tra, khỏi tốn bge-m3.
            rag_context = ""
            metrics["rag_ms"] = 0
            metrics["rag_doan_truoc"] = False
        elif tron_tai_lieu:
            rag_context = tron_tai_lieu
            metrics["rag_ms"] = 0
            metrics["rag_doan_truoc"] = False
            metrics["ngu_canh_tron"] = len(tron_tai_lieu)
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
                truy_van = self._truy_van_rag(user_text, session)
                with Timer("RAG") as t_rag:
                    if soi:
                        # Giữ luôn điểm khớp, nguồn và mảnh bị lọc để trang Nhắn
                        # tin chỉ ra được VÌ SAO câu trả lời ra như vậy. Truy vấn
                        # cũng ghi lại: nó đã được neo theo sản phẩm nên khác câu
                        # khách gõ, mà lệch neo là một nguồn lỗi thật.
                        rag_context, metrics["rag_nguon"] = \
                            await self.rag.retrieve_chi_tiet(
                                truy_van, top_k=2, san_pham=session.product)
                        metrics["rag_truy_van"] = truy_van
                    else:
                        rag_context = await self.rag.retrieve(
                            truy_van, top_k=2, san_pham=session.product)
                metrics["rag_ms"] = round(t_rag.elapsed_ms)
            except Exception as e:
                logger.warning(f"RAG error: {e}")
                rag_context = ""
                metrics["rag_ms"] = 0

        # Bảng hỏi-đáp đứng TRƯỚC tri thức: trúng dòng nào thì nội dung dòng đó
        # lên đầu ngữ cảnh, còn tri thức tra được vẫn giữ nguyên bên dưới. Đặt
        # lên đầu chứ không thay thế: câu khách hỏi có thể chạm hai chuyện, bỏ
        # hẳn phần tri thức là làm hẹp câu trả lời lại.
        dong_bang = self._tra_bang_hoi_dap(
            user_text, session, tinh_huong_id=metrics.get("tinh_huong_id"))
        if dong_bang:
            metrics["bang_hoi_dap"] = dong_bang["id"]
            metrics["bang_diem"] = round(dong_bang.get("diem", 0.0), 3)
            metrics["bang_theo_tinh_huong"] = bool(dong_bang.get("theo_tinh_huong"))
            logger.info("Bảng hỏi-đáp: trúng dòng %r (%s)", dong_bang["id"],
                        "theo tình huống" if dong_bang.get("theo_tinh_huong")
                        else f"{dong_bang.get('diem', 0.0):.3f}")
            rag_context = (f"[Câu trả lời đã duyệt - dùng ĐÚNG nội dung này]\n"
                           f"{dong_bang['tra_loi']}\n\n{rag_context}").strip()
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

        # Sổ căn cứ của CẢ cuộc gọi, để lưới chặn số khỏi chặn nhầm con số đã có
        # căn cứ ở lượt trước. Thứ tự bắt buộc: xét đổi neo TRƯỚC (nó xoá sổ),
        # rồi mới ghi căn cứ của lượt này vào. Xem `so_can_cu.py`.
        so_can_cu = getattr(session, "so_can_cu", None)
        can_cu_phien = ""
        if so_can_cu is not None:
            try:
                if self.rag is not None:
                    so_can_cu.doi_neo(self.rag.san_pham_neo(
                        user_text, getattr(session, "product", "")))
                so_can_cu.ghi_khach(user_text)
                so_can_cu.ghi_tai_lieu(ngu_canh)
                can_cu_phien = so_can_cu.can_cu
            except Exception as e:
                # Sổ chỉ NỚI lưới ra. Hỏng sổ thì quay về hành vi cũ (chặt hơn),
                # tuyệt đối không được làm rơi lượt đang phục vụ khách.
                logger.warning("Sổ căn cứ lỗi (bỏ qua): %s", e)

        # `filler_text` do `_send_filler` ghi vào metrics NGAY TRƯỚC lượt này -
        # tức chữ khách VỪA nghe. Đưa vào prompt để mô hình nói TIẾP thay vì mở
        # đầu lại: đo 06-09-2026, câu đệm "Dạ về phần tài liệu," rồi mô hình đáp
        # "em sẽ gửi thông tin chi tiết về sản phẩm vay tín chấp cho anh ngay" -
        # người dùng nghe thành hai mảnh rời, "rất máy móc, ko nối luôn vào câu".
        system_prompt = self.llm.build_system_prompt(
            customer_name=session.customer_name,
            product=session.product,
            rag_context=ngu_canh,
            scenario=getattr(session, "scenario", None),
            gioi_tinh=getattr(session, "gender", ""),
            gioi_tinh_do_tin=getattr(session, "gender_do_tin", None),
            cau_dem=metrics.get("filler_text", ""),
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

        # Mảnh đang GIỮ LẠI, chưa gửi, chờ xem còn mảnh nào sau nó không.
        #
        # Vì sao phải giữ: cắt cứ 5 từ một thì phần dư ở cuối lượt là bao nhiêu
        # còn lại, thường 1-2 từ. Đo trên bản ghi thật: câu "…anh cứ yên tâm
        # nhé." ra mảnh "nhé." dài 0,33 giây đứng một mình, và F5 sinh nó như
        # MỘT CÂU HOÀN CHỈNH - đủ cả mở đầu lẫn kết thúc - nên nghe tách hẳn ra.
        # Ba lượt trong bản ghi 10 lượt bị thế.
        #
        # Giữ lại một mảnh thì lúc hết lượt còn kịp gộp đuôi ngắn vào nó.
        # Mảnh ĐẦU không giữ: giữ nó là đội thẳng vào thời gian khách chờ tiếng
        # đầu. Từ mảnh thứ hai trở đi thì giữ không tốn gì, vì lúc đó TTS vẫn
        # đang bận mảnh trước - hàng đợi mới là chỗ nghẽn, không phải chỗ này.
        cho_gui: str | None = None

        def _gui_manh(t: str) -> None:
            nonlocal cau_da_loc
            tts_queue.put_nowait((t, bot_lich_su.nghi_truoc_ms))
            cau_da_loc = _noi_manh(cau_da_loc, t)

        # Ollama và F5-TTS dùng chung một GPU, và đây là nút thắt lớn nhất:
        # đo đối chứng cho thấy TTS mất 510-515ms khi GPU rảnh nhưng 1258-1434ms
        # khi Ollama đang sinh token.
        #
        # Đã thử tạm dừng vòng đọc stream để "nhường GPU" - VÔ TÁC DỤNG, vì ngừng
        # đọc không ngăn được Ollama tiếp tục tính phía server. Cách thật sự hiệu
        # quả là giảm khối lượng Ollama phải sinh (llm_max_tokens).
        first_audio_done = asyncio.Event()

        # TIẾNG SẴN (services/tieng_san.py): lượt có chữ cố định (bảng hỏi-đáp
        # đọc nguyên văn, lượt thường gặp) đã dựng tiếng cả câu từ trước thì
        # phát thẳng, không cắt mảnh gọi F5. Chữ vẫn đi qua vòng cắt bên dưới
        # để `response_chunk` và lịch sử y như cũ; chỉ phần tiếng là lấy sẵn,
        # đi kèm mảnh đầu, các mảnh sau không có tiếng riêng (như gộp mảnh).
        tieng_san: bytes | None = None
        ma_tieng_san: str | None = None
        chu_tieng_san: str = ""

        async def tts_consumer():
            idx = 0
            first_audio_sent = False
            # DƯ ĐỊA PHÁT: tiếng đã gửi trừ đi thời gian đã trôi kể từ mảnh
            # tiếng đầu. Đây là thứ duy nhất cho phép chờ gom mảnh mà không
            # tạo quãng im. Câu đệm KHÔNG tính vào đây (nó gửi ở chỗ khác) -
            # thiếu đi thì chỉ khiến ta dè dặt hơn thực tế, hướng an toàn.
            da_gui_ms = 0.0
            t_am_dau = None
            nghi_ms = 0.0        # nhịp nghỉ nợ từ mảnh TRƯỚC, trả vào đầu mảnh này
            # Đếm gộp mảnh. Gộp là thứ bên A đã nghe 100 câu rồi chọn, nhưng nó
            # chỉ xảy ra khi còn đủ thời gian (`cho_gom_ms`) - có lượt ăn, có
            # lượt không, và trước đây KHÔNG có gì trong log cho biết. Bản xuất
            # file thì gộp gần 100%, nên nghe bản xuất rồi duyệt là duyệt nhầm.
            n_manh_sinh = 0      # số mảnh đi qua bước sinh tiếng
            n_lan_sinh = 0       # số lần thật sự gọi F5
            # Vì sao gộp trượt. Chỉ "0%" thì lần sau lại phải mở máy điều tra
            # từ đầu: hết dư địa, hay có dư địa mà chờ vẫn không ra mảnh nào?
            du_dia_tong = 0.0
            doi_tong = 0.0
            n_co_hoi = 0
            while True:
                goi = await tts_queue.get()
                if goi is None:
                    break
                # Quãng nghỉ đi KÈM mảnh: chỗ ngắt câu có thể nằm ở chữ "ạ"
                # đầu mảnh mà `BotLichSu` vừa bỏ, lúc đó mảnh trước không còn
                # dấu câu nào để `nhip_nghi_sau` nhìn ra.
                chunk_text, nghi_them = goi
                # LẤY LỚN HƠN, không cộng dồn. Hai con số này là HAI CÁCH NHÌN
                # cùng MỘT chỗ ngắt: `nghi_ms` là nhịp nghỉ suy từ dấu câu cuối
                # mảnh trước, `nghi_them` là nhịp nghỉ suy từ dấu câu đầu mảnh
                # này (chữ "ạ." mà BotLichSu vừa bỏ). Cộng lại là nghỉ hai lần
                # cho một chỗ.
                #
                # Đo được sau khi đổi sang cắt 5 từ: 360 + 360 = 720ms, xuất
                # hiện lặp đi lặp lại trong bản ghi hội thoại thật và nghe y
                # như F5 bịa quãng dừng. Lỗi vốn có từ trước nhưng cắt ở dấu
                # câu thì hiếm khi hai vế cùng khác 0; mảnh 5 từ làm nó lộ ra.
                #
                # Dòng ngay dưới, xử lý mảnh rỗng, đã dùng đúng `max` từ đầu.
                nghi_ms = max(nghi_ms, nghi_them)

                # Mảnh không có chữ nào (thường là đúng một dấu chấm, sinh ra khi
                # luật "ạ/nhé" cắt trước rồi dấu câu mới tới) - đừng gọi TTS cho
                # nó: tốn một lượt sinh để ra gần như im lặng. Nhưng vẫn phải lấy
                # nhịp nghỉ của nó, không thì mảnh sau mất chỗ ngắt.
                if not chunk_text or not any(c.isalnum() for c in chunk_text):
                    nghi_ms = max(nghi_ms, nhip_nghi_sau(chunk_text))
                    continue

                # GỘP LÔ các mảnh đang xếp hàng - xem `_synthesize_lo_sync`.
                #
                # Vét CƠ HỘI chứ không chờ cho đủ lô: chỉ gom những mảnh ĐÃ có
                # sẵn trong hàng đợi. Chờ cho đủ 4 thì mảnh thứ 2 phải đợi mảnh
                # thứ 5 của LLM, tức đổi thời gian GPU lấy độ trễ - sai hướng.
                #
                # KHÔNG gộp mảnh đầu: nó nằm trên đường găng của TTFA, phải đi
                # ngay khi có chữ. Các mảnh sau thì TTS đã chạy trước tiếng phát
                # ~3,5 lần nên gom lại không ai nghe ra.
                # `nghi_them` của mảnh đầu đã gộp vào `nghi_ms` ở trên rồi; ở đây
                # giữ nguyên số THÔ của từng mảnh, việc cộng dồn để vòng phát ở
                # dưới lo - đúng y hệt thứ tự của đường một mảnh.
                dan = [(chunk_text, 0.0)]
                # GỘP THÀNH MỘT PHÁT NGÔN. Khác hẳn `GOP_LO` ngay dưới: chỗ kia
                # gom để chạy lô cho nhanh GPU nhưng vẫn sinh N phát ngôn RỜI,
                # nên chỗ nối - và chữ ngân ở đó - vẫn còn nguyên. Chỗ này nối
                # chữ lại rồi sinh MỘT lần, chỗ nối biến mất thật.
                #
                # Vét CƠ HỘI, không chờ: chỉ lấy mảnh ĐÃ nằm sẵn trong hàng đợi.
                # Chờ cho LLM sinh nốt để gộp được nhiều hơn là đổi độ trễ lấy
                # ngữ điệu - sai hướng, và khách nghe ra quãng im ngay.
                gop_mot = False
                if settings.f5tts_gop_manh and not GOP_LO and idx > 0 and tieng_san is None:
                    cho = []
                    het_luot = False
                    # CHỜ CÓ ĐIỀU KIỆN. Không chờ thì gộp chỉ ăn được 25% chỗ
                    # nối (đo 16-08): lúc lấy mảnh 2 thì LLM chưa sinh xong mảnh
                    # 3, hàng đợi rỗng, không có gì để gộp.
                    #
                    # Chỉ chờ trong phần DƯ ĐỊA đã đo được, và đã trừ cả thời
                    # gian sinh sắp tới - xem `cho_gom_ms`. Hết dư địa thì chờ
                    # 0ms, tức quay về đúng hành vi cũ. Không bao giờ được đổi
                    # chữ ngân lấy quãng im.
                    if t_am_dau is not None:
                        du_dia = da_gui_ms - (time.perf_counter() - t_am_dau) * 1000
                        doi = cho_gom_ms(du_dia, uoc_sinh_ms(chunk_text))
                        du_dia_tong += du_dia
                        doi_tong += doi
                        n_co_hoi += 1
                        if doi > 0:
                            try:
                                them = await asyncio.wait_for(tts_queue.get(),
                                                              timeout=doi / 1000.0)
                            except asyncio.TimeoutError:
                                them = ...              # không có gì thêm
                            if them is None:
                                het_luot = True
                            elif them is not ...:
                                cho.append(them)
                    # Từ đây tới lúc trả lại hàng đợi KHÔNG được có `await` nào,
                    # nếu không thứ tự mảnh sẽ loạn.
                    while not het_luot:
                        try:
                            them = tts_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                        if them is None:                  # tín hiệu hết lượt
                            het_luot = True
                            break
                        cho.append(them)
                    # Thứ tự chỉ đúng nhờ hai điều: hàng đợi vừa bị vét sạch, và
                    # từ lúc vét tới lúc trả KHÔNG có `await` nào nên không
                    # coroutine nào chen được vào giữa. Việc xếp cụm và xếp thứ
                    # tự trả lại nằm trong `sap_cum_gop`, có test riêng
                    # (`tests/test_sap_cum_gop.py`) vì sai ở đây là mất tiếng.
                    dan, tra_lai = sap_cum_gop((chunk_text, 0.0), cho, het_luot)
                    for goi_du in tra_lai:
                        tts_queue.put_nowait(goi_du)
                    gop_mot = len(dan) > 1
                if GOP_LO and idx > 0 and tieng_san is None:
                    while len(dan) < LO_TOI_DA:
                        try:
                            them = tts_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                        if them is None:              # tín hiệu hết lượt
                            tts_queue.put_nowait(None)
                            break
                        t_chu, t_nghi = them
                        if not t_chu or not any(c.isalnum() for c in t_chu):
                            # Mảnh rỗng vẫn phải nhả nhịp nghỉ của nó, không thì
                            # mảnh sau mất chỗ ngắt - giống nhánh xử lý ở trên.
                            dan[-1] = (dan[-1][0], max(dan[-1][1], t_nghi))
                            continue
                        dan.append((t_chu, t_nghi))

                t_synth = time.perf_counter()
                n_manh_sinh += len(dan)
                if soi:
                    # Chế độ soi: KHÔNG sinh tiếng. Vẫn đi trọn vòng cắt mảnh và
                    # vẫn gửi `response_chunk` bên dưới, nên chữ hiện ra đúng
                    # từng mảnh y như đường thoại - chỉ bỏ đúng phần chiếm GPU.
                    # `tieng = None` nên các nhánh `if tieng` tự bỏ qua, không
                    # phải rắc thêm điều kiện xuống dưới.
                    song = [None] * len(dan)
                elif tieng_san is not None:
                    # Cả lượt đã có tiếng dựng sẵn: đi kèm mảnh ĐẦU, mảnh sau
                    # chỉ hiện chữ. Không gọi F5 lần nào trong lượt này.
                    song = [tieng_san if idx == 0 else None] + [None] * (len(dan) - 1)
                elif gop_mot:
                    n_lan_sinh += 1
                    # MỘT lần sinh cho cả cụm - đó chính là chỗ chữ ngân biến
                    # mất. Tiếng đi kèm mảnh đầu; các mảnh sau vẫn được gửi
                    # `response_chunk` để chữ hiện đúng như cũ, chỉ không có
                    # tiếng riêng.
                    mot = noi_lo([d[0] for d in dan])
                    tieng_gop = await self._try_synthesize(
                        mot, voice=session.voice_name, session=session)
                    if tieng_gop is None:
                        # Đường lùi: gộp hỏng thì sinh từng mảnh như cũ, thà
                        # còn chữ ngân hơn là khách nghe im cả cụm.
                        logger.warning("gộp mảnh hỏng - lùi về sinh từng mảnh")
                        # Gộp trượt: lần sinh gộp không ra tiếng, thay bằng
                        # từng mảnh. Trừ lại lần đã đếm để tỷ lệ không báo dư.
                        n_lan_sinh += len(dan) - 1
                        song = [await self._try_synthesize(
                            d[0], voice=session.voice_name, session=session) for d in dan]
                    else:
                        song = [tieng_gop] + [None] * (len(dan) - 1)
                elif len(dan) > 1:
                    n_lan_sinh += len(dan)
                    song = await self._try_synthesize_lo(
                        [d[0] for d in dan], voice=session.voice_name, session=session)
                else:
                    n_lan_sinh += 1
                    song = [await self._try_synthesize(
                        chunk_text, fast=(idx == 0), voice=session.voice_name,
                        session=session)]
                synth_ms = round((time.perf_counter() - t_synth) * 1000)

                for (t_chu, t_nghi), tieng in zip(dan, song):
                    # Nợ nhịp nghỉ của mảnh trước, gộp với nhịp mà chính mảnh
                    # này mang theo (chỗ ngắt nằm ở chữ "ạ" mà BotLichSu vừa bỏ).
                    # LẤY LỚN HƠN chứ không cộng - hai cách nhìn cùng một chỗ.
                    nghi_ms = max(nghi_ms, t_nghi)
                    # Mảnh ĐẦU của lượt: ranh giới với CÂU ĐỆM vừa phát. Đây là
                    # ranh giới phẩy duy nhất trong hệ thống không được chèn
                    # nhịp, xem `_nghi_noi_cau_dem`.
                    if not first_audio_sent:
                        nghi_ms = max(nghi_ms, self._nghi_noi_cau_dem(metrics))
                    # Trả lại nhịp nghỉ mà trim_silence đã cắt mất ở ranh giới
                    # mảnh. Chèn vào ĐẦU mảnh này chứ không nối vào cuối mảnh
                    # trước, nên mảnh cuối không bị thêm đuôi lặng thừa.
                    #
                    # Mảnh ĐẦU trước đây không bao giờ được chèn, để giữ TTFA.
                    # Nay có MỘT ngoại lệ: khi câu đệm còn đang phát thì chỗ nối
                    # với nó là một ranh giới phẩy thật và phải được nghỉ như mọi
                    # ranh giới khác - lúc đó khách đang nghe TIẾNG chứ không
                    # nghe im, nên 180ms này không thành khoảng lặng.
                    if tieng and nghi_ms > 0:
                        tieng = chen_lang_dau_wav(tieng, nghi_ms)
                    nghi_ms = nhip_nghi_sau(t_chu)

                    if tieng and not first_audio_sent:
                        metrics["ttfa_ms"] = round((time.perf_counter() - t_start) * 1000)
                        # Bóc tách TTFA: không đo riêng thì đoạn giữa RAG và
                        # audio đầu là hộp đen, không biết LLM hay TTS mới chậm.
                        metrics["tts_first_ms"] = synth_ms
                        metrics["tts_first_chars"] = len(t_chu)
                        first_audio_sent = True
                        first_audio_done.set()   # trả GPU lại cho LLM

                    if tieng:
                        await self._send_audio(ws, tieng, chunk_id=idx,
                                               turn_id=session.turn_id,
                                               text=t_chu)
                        if t_am_dau is None:
                            t_am_dau = time.perf_counter()
                        da_gui_ms += dai_wav_ms(tieng)
                    await self._send_event(ws, "response_chunk",
                                           {"text": t_chu, "chunk_id": idx})
                    idx += 1

            # Gộp mảnh ăn được bao nhiêu chỗ nối trong LƯỢT NÀY. Không ghi lại
            # thì không ai biết nó còn chạy hay đã tắt ngóm - `f5tts_gop_manh`
            # tắt đi, hay lượt nào cũng thiếu thời gian, log đều im như nhau.
            ty_le = ty_le_gop(n_manh_sinh, n_lan_sinh)
            if ty_le is not None and tieng_san is None:
                metrics["gop_manh"] = f"{n_manh_sinh - n_lan_sinh}/{n_manh_sinh - 1}"
                metrics["gop_ty_le"] = round(ty_le, 2)
                logger.info(
                    "Gộp mảnh: bỏ được %d/%d chỗ nối (%.0f%%) - %d mảnh, %d lần "
                    "gọi F5. Dư địa TB %.0fms, chờ TB %.0fms trên %d cơ hội. "
                    "Mỗi chỗ nối bỏ được là một chữ ngân giữa câu biến mất.",
                    n_manh_sinh - n_lan_sinh, n_manh_sinh - 1, ty_le * 100,
                    n_manh_sinh, n_lan_sinh,
                    du_dia_tong / n_co_hoi if n_co_hoi else 0.0,
                    doi_tong / n_co_hoi if n_co_hoi else 0.0, n_co_hoi)

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
        elif dong_bang and doc_nguyen_van(dong_bang):
            # Khách hỏi gần đúng cách đã soạn -> đọc NGUYÊN VĂN nội dung đã
            # duyệt, bỏ qua mô hình. Đo được: đưa nội dung vào ngữ cảnh kèm nhãn
            # "dùng ĐÚNG nội dung này" thì mô hình VẪN viết lại và bỏ sạch con
            # số. Đây là tư vấn tài chính, sai số là sai cam kết với khách.
            metrics["bang_doc_thang"] = True
            logger.info("Bảng hỏi-đáp: đọc NGUYÊN VĂN dòng %r (%.3f), bỏ qua mô hình",
                        dong_bang["id"], dong_bang.get("diem", 0.0))
            nguon_token = _phat_lai(dong_bang["tra_loi"])
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
            # `prefill`: chữ khách VỪA NGHE (câu đệm). Mô hình viết TIẾP câu đó
            # thay vì mở đầu lại - xem `llm_service.stream_response` cho số đo và
            # ba cách dặn-bằng-prompt đã thất bại trước nó.
            nguon_token = self.llm.stream_response(
                session.history, system_prompt,
                prefill=metrics.get("filler_text", ""))

        # Lượt chữ cố định -> tra kho tiếng sẵn. Chưa có thì lượt này vẫn đi F5
        # như cũ và dựng NỀN sau khi xong lượt (xem cuối hàm), lần sau phát sẵn.
        if dap_san:
            ma_tieng_san, chu_tieng_san = f"ltg_{dap_san[0]}", dap_san[1]
        elif dong_bang and doc_nguyen_van(dong_bang):
            ma_tieng_san, chu_tieng_san = f"hd_{dong_bang['id']}", dong_bang["tra_loi"]
        if ma_tieng_san and settings.tieng_san_bat and self._tts_available:
            tieng_san = kho_tieng_san.lay(
                self.tts, ma_tieng_san, chu_tieng_san,
                self.tts._giong_thuc(session.voice_name))
            metrics["tieng_san"] = ma_tieng_san if tieng_san else "chua_co"
            if tieng_san:
                logger.info("Tiếng sẵn: phát %r, không gọi F5", ma_tieng_san)

        da_chan_bia = False
        da_chan_thu_nhap = False
        # Lưới VỪA thay cả mảnh ở lượt gọi này, và mảnh phát ra ngay
        # trước có bỏ lửng câu không. Hai thứ này quyết định câu thay
        # thế phải đi đường nào - xem `_luoc_va_chan`.
        vua_thay_cau = [False]
        manh_truoc_dang_do = [False]
        # Lời khách TRONG CẢ CUỘC, không phải ngữ cảnh tài liệu. Lưới thu
        # nhập chỉ được tin đúng nguồn này - xem `chan_gan_thu_nhap`.
        khach_da_noi = " ".join(
            [t.get("content") or "" for t in session.history
             if t.get("role") == "user"] + [user_text or ""])

        def _doi_cau_neu_lap(ra: str) -> str:
            """Chặn hai lượt liền mà phát y hệt một câu thì khách nghe ra là AI
            chỉ biết mỗi một câu - xem `cau_chan_lap.py`. Đổi câu, và từ lần thứ
            hai thì HỎI LẠI con số vì đó mới là thứ gỡ được vòng lặp."""
            if ra != CAU_KIEM_TRA_LAI:
                return ra
            luot = getattr(session, "turn_count", 0)
            so_lan, moc = dem_chan_lien_tiep(
                luot, getattr(session, "luot_chan_cuoi", None),
                getattr(session, "so_lan_chan_lien_tiep", 0))
            session.luot_chan_cuoi = moc
            session.so_lan_chan_lien_tiep = so_lan
            # Truyền `da_co_cau_dem`: câu đệm vừa phát đã hứa "em kiểm tra
            # lại rồi báo lại", câu chặn số 1 hứa y hệt -> hai lần một ý trong
            # CÙNG một lượt. `dem_chan_lien_tiep` không thấy được vì nó chỉ
            # đếm lặp giữa các lượt.
            #
            # CHỈ ở mảnh ĐẦU. Câu đệm đứng đầu lượt, nên chỉ mảnh đầu mới trùng
            # với nó. Chặn ở giữa lượt mà đổi câu là chèn một CÂU HỎI vào giữa
            # câu đang nói dở - nghe thật 06-09-2026, lượt 3 cuộc gọi 1d690897:
            #   "Nếu anh vay trong 60 tháng, Dạ để em khỏi nói sai, anh chị
            #    nhắc lại giúp em con số mình đang cần"
            # Giữa lượt thì không có gì để trùng, cứ dùng câu cũ.
            # Truyền CHỮ của câu đệm chứ không phải cờ có/không: rút gọn thành
            # "Dạ vâng ạ." chỉ đúng khi câu đệm ĐÃ hứa kiểm tra. Xem
            # `cau_chan_lap.hua_kiem_tra` cho ca hỏng đã đo.
            moi = cau_chan(so_lan,
                           cau_dem=(metrics.get("filler_text", "")
                                    if chunks_enqueued == 0 else ""))
            if moi != ra:
                logger.info("Câu chặn lặp lần %d - đổi câu: %r", so_lan, moi[:60])
            return moi

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
            # Hàng rào ĐẦU: tài liệu không có phần trăm nào mà câu lại nêu ->
            # con số đó lấy từ TRÍ NHỚ mô hình, không phải từ tài liệu. Phải
            # đứng trước `chan_so_sai` vì hàm đó chỉ sửa khi tài liệu CÓ số.
            #
            # Thay CẢ MẢNH được vì mảnh cắt theo NGUYÊN CÂU (`CAT_THEO_CAU`),
            # nên câu thay vào vẫn đúng ngữ pháp. Chỉ thay MỘT lần mỗi lượt:
            # hai câu cùng nêu phần trăm mà thay cả hai thì khách nghe "em xin
            # phép kiểm tra lại" hai lần liền.
            nonlocal da_chan_bia, da_chan_thu_nhap
            # TUÂN THỦ trước SỐ: câu dính chữ cấm thì bị thay nguyên câu, chạy
            # tiếp mấy lưới số trên câu thay là vô nghĩa.
            ra, sua_cam = chan_tu_cam(doan)
            if sua_cam:
                logger.warning("CHẶN CHỮ CẤM: %s | %r -> %r",
                               sua_cam, doan[:60], ra[:60])
                metrics["chan_tu_cam"] = sua_cam
                vua_thay_cau[0] = True
                return ra
            if not da_chan_thu_nhap:
                ra, sua_tn = chan_gan_thu_nhap(doan, khach_da_noi=khach_da_noi)
                if sua_tn:
                    da_chan_thu_nhap = True
                    logger.warning("CHẶN GÁN THU NHẬP: %s | %r -> %r",
                                   sua_tn, doan[:60], ra[:60])
                    metrics["chan_gan_thu_nhap"] = sua_tn
                    vua_thay_cau[0] = True
                    return ra
            if not da_chan_bia:
                ra, sua_bia = chan_lai_suat_bia(doan, ngu_canh,
                                                can_cu_them=can_cu_phien)
                if sua_bia:
                    da_chan_bia = True
                    logger.warning("CHẶN LÃI SUẤT BỊA: %s | %r -> %r",
                                   sua_bia, doan[:60], ra[:60])
                    metrics["chan_lai_suat_bia"] = sua_bia
                    vua_thay_cau[0] = True
                    return _doi_cau_neu_lap(ra)
            ra, sua = chan_so_sai(doan, ngu_canh, can_cu_them=can_cu_phien)
            if sua:
                logger.warning("CHẶN SỐ SAI: %s | %r -> %r", sua, doan[:50], ra[:50])
                metrics["chan_so_sai"] = sua
            # Lưới THUỘC TÍNH: con số đúng vẫn có thể gán sai chủ thể. Chạy sau
            # `chan_so_sai` để phán trên bản đã sửa số đọc nhầm.
            #
            # Bắt được thì SỬA CÂU chứ không im lặng: thay số bằng giá trị trong
            # tài liệu, không thay được thì bỏ mệnh đề, bỏ hết mới dùng câu mẫu.
            # Xem `config.thuoc_tinh_sua_cau` cho lý do bật mặc định.
            _, sua_tt = chan_thuoc_tinh_sai(
                ra, ngu_canh, self._bang_thuoc_tinh, khach_noi=user_text,
                can_cu_them=can_cu_phien)
            if sua_tt:
                logger.warning("THUỘC TÍNH LỆCH: %s | %r", sua_tt, ra[:60])
                metrics["chan_thuoc_tinh"] = sua_tt
                if settings.thuoc_tinh_sua_cau:
                    moi, cach_sua = sua_theo_tai_lieu(
                        ra, ngu_canh, self._bang_thuoc_tinh, khach_noi=user_text,
                        can_cu_them=can_cu_phien)
                    # Bỏ sạch thì mới dùng câu mẫu - đây là nhánh HIẾM, giữ nó
                    # hiếm chính là thứ tránh được "trả lời 1 kiểu".
                    ra = moi.strip() or CAU_KIEM_TRA_LAI
                    metrics["thuoc_tinh_da_sua"] = cach_sua or "bỏ cả câu"
                    logger.info("THUỘC TÍNH đã sửa: %s | %r", cach_sua, ra[:60])
            # Hàng rào thứ hai: SỐ TIỀN. Truyền cả câu khách vừa nói để không
            # "sửa" con số do chính khách nêu ra - AI nhắc lại số của khách là
            # đúng, chặn nó mới là sai.
            ra, sua_tien = chan_tien_sai(ra, ngu_canh, khach_noi=user_text,
                                         can_cu_them=can_cu_phien)
            if sua_tien:
                logger.warning("CHẶN TIỀN SAI: %s | %r", sua_tien, ra[:50])
                metrics["chan_tien_sai"] = sua_tien
                vua_thay_cau[0] = True
                ra = _doi_cau_neu_lap(ra)
            return ra

        # Bớt "ạ"/"Dạ" thừa. Bỏ "Dạ" mở đầu khi: (a) vừa phát filler - gần hết
        # filler đã mở bằng "Dạ" rồi, để nguyên thì khách nghe "Dạ vâng ạ. Dạ
        # hiện bên em..." hai lần liền; hoặc (b) lượt chẵn - mở đầu lượt nào cũng
        # "Dạ" thì nghe như máy, mà bỏ sạch lại cộc, xen kẽ là vừa.
        # Một đối tượng cho MỖI LƯỢT - xem chú thích ở lớp.
        bo_hua_suong = BoHuaSuong()
        # Câu đệm vừa nêu chủ đề thì câu MÔ HÌNH viết không được nêu lại ngay chữ
        # đầu - xem `bo_chu_de_da_neu`. Câu nguyên văn (bảng hỏi-đáp, lượt thường
        # gặp) thì KHÔNG: nó phát bằng tiếng dựng sẵn, cắt chữ là chữ một đằng
        # tiếng một nẻo, lại còn sửa câu kịch bản đã duyệt.
        cau_dem_mo_hinh = "" if (dap_san or (dong_bang and doc_nguyen_van(dong_bang))) else metrics.get("filler_text", "")
        bot_lich_su = BotLichSu(
            bo_da=bool(metrics.get("filler_text")) or session.turn_count % 2 == 0,
            cau_dem=cau_dem_mo_hinh)

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

        from backend.services.gender_detect import xung_ho as _xh_goi
        _goi_khach = _xh_goi(getattr(session, "gender", ""),
                             getattr(session, "gender_do_tin", None))

        def _don_loi(doan: str) -> str:
            # `sua_xung_ho` chạy TRƯỚC: nó bỏ số thứ tự đầu câu, mà các bước sau
            # xét chữ đầu ("Dạ", con số) nên phải sạch trước khi tới đó.
            #
            # `bo_cau_lui_thua` đứng SAU `sua_xung_ho` để câu lùi đã về đúng dạng
            # "anh/chị" trước khi đem so, và TRƯỚC `_chan_so` để phần bị cắt bỏ
            # không mang theo con số nào làm lệch bộ chặn số.
            #
            # Truyền `goi_khach`: `sua_xung_ho` ép luôn "bạn" về đúng đại từ.
            # Model nhỏ hay tuột về "bạn" dù prompt đã dặn - đo 08-08 trên
            # qwen2.5:3b: 4/9 lượt gọi khách là "bạn".
            # `chan_chu_ngoai` chạy ĐẦU TIÊN: các bước sau xét chữ đầu và đếm
            # số, mà chữ Hán lẫn vào làm lệch cả hai.
            doan, lot = chan_chu_ngoai(doan)
            if lot:
                logger.warning("Model để lọt chữ nước ngoài %r - đã bỏ. "
                               "Lọt nhiều thì model đang trượt khỏi tiếng Việt.", lot)
            # `bo_hua_suong` đứng SAU `_chan_so`: câu hứa bị bỏ không được mang
            # theo con số nào ra khỏi tầm nhìn của bộ chặn số, và nó cần thấy
            # đúng con số đã qua kiểm để quyết "mảnh này là nội dung thật".
            vua_thay_cau[0] = False
            sau_chan = _chan_so(bo_cau_lui_thua(
                sua_chu_mo_hinh(sua_xung_ho(doan, goi_khach=_goi_khach))))
            if vua_thay_cau[0]:
                # ĐI VÒNG qua `bo_hua_suong`. Câu này do LƯỚI chèn, là thứ BẮT
                # BUỘC phải tới tai khách - không phải hứa suông của mô hình.
                # Tái hiện được: `BoHuaSuong()(CAU_KIEM_TRA_LAI)` trả CHUỖI RỖNG,
                # nên mảnh bị chặn biến mất và khách chỉ nghe mảnh TRƯỚC nó. Bản
                # ghi 07-09-2026: "Với khách hàng mới vay tín chấp," rồi hết.
                #
                # KHÔNG sửa `BoHuaSuong`: với câu do mô hình sinh thì xoá hứa
                # suông vẫn đúng việc của nó. Chỉ đường này mới được miễn.
                ra = self._cau_thay_the(sau_chan, manh_truoc_dang_do[0])
            else:
                ra = bo_hua_suong(sau_chan)
            ra = bot_lich_su(ra)
            # Ghi lại cho mảnh SAU: mảnh cắt ở dấu phẩy (`TACH_O_PHAY`) thì câu
            # còn dang dở, câu thay thế của mảnh sau phải nối tiếp chứ không
            # được mở câu mới bằng "Dạ".
            if ra.strip():
                manh_truoc_dang_do[0] = self._con_dang_do(ra)
            return ra

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

                # tach_manh chứ không phải should_flush: nó cắt ĐÚNG 5 từ đầu và
                # TRẢ LẠI phần đệm còn dư, nên mẩu token dở dang ("ng" của
                # "ngay") ở lại chờ token sau thay vì bị giao cho TTS.
                # Cỡ mảnh TĂNG DẦN - xem `CO_MANH_TANG_DAN`. Mảnh đầu nhỏ để
                # tiếng ra sớm, các mảnh sau to dần cho ngữ điệu liền mạch.
                manh, text_buffer = tach_manh(
                    text_buffer, n=co_manh(chunks_enqueued),
                    first_chunk=(chunks_enqueued == 0))
                if manh is not None:
                    chunk_text = manh.strip()
                    if chunk_text:
                        if chunks_enqueued == 0:
                            # LLM phải sinh đủ chữ cho câu đầu thì TTS mới có việc.
                            # Tách riêng khỏi TTFT: chờ token đầu và gom đủ câu là
                            # hai nguyên nhân chậm khác nhau, cách xử lý cũng khác.
                            metrics["llm_chunk1_ms"] = round((time.perf_counter() - t_llm) * 1000)
                        chunk_text = _don_loi(chunk_text)
                        # Mảnh ĐẦU đi ngay để không đội thời gian chờ tiếng đầu.
                        # Từ mảnh thứ hai thì GIỮ LẠI MỘT MẢNH, chỉ gửi khi đã có
                        # mảnh kế - xem `_gui_manh` để biết vì sao.
                        if chunks_enqueued == 0:
                            _gui_manh(chunk_text)
                        else:
                            if cho_gui is not None:
                                _gui_manh(cho_gui)
                            cho_gui = chunk_text
                        chunks_enqueued += 1
        except Exception as e:
            logger.error(f"LLM error: {e}")
            await self._send_event(ws, "error", {"message": f"LLM error: {e}"})

        # Xả nốt phần còn trong đệm. ĐUÔI NGẮN thì gộp vào mảnh đang giữ chứ
        # không gửi riêng - xem `_gui_manh`.
        du = _don_loi(text_buffer.strip()) if text_buffer.strip() else ""
        if du and cho_gui is not None and len(du.split()) < TOI_THIEU_TU_MANH_CUOI:
            cho_gui = f"{cho_gui} {du}".strip()
            du = ""
        if cho_gui is not None:
            _gui_manh(cho_gui)
            cho_gui = None
        if du:
            _gui_manh(du)
        tts_queue.put_nowait(None)
        try:
            await consumer_task
        except Exception as e:
            logger.error(f"TTS consumer error: {e}")

        metrics["total_ms"] = round((time.perf_counter() - t_start) * 1000)
        _ghi_im_lang(session, t_start, metrics)
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

        # Dựng tiếng sẵn cho lượt chữ cố định vừa phải đi F5, để lần sau phát
        # thẳng. Chạy NỀN sau khi khách đã nghe xong, giữ tham chiếu mạnh như
        # `_schedule_persist`. Lỡ lượt bị cắt thì vẫn dựng: chữ không đổi.
        if (ma_tieng_san and tieng_san is None and settings.tieng_san_bat
                and self._tts_available):
            task = asyncio.create_task(kho_tieng_san.dung_mot(
                self.tts, ma_tieng_san, chu_tieng_san,
                self.tts._giong_thuc(session.voice_name)))
            _bg_writes.add(task)
            task.add_done_callback(_bg_writes.discard)

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
        elif metrics.get("filler_bo_qua"):
            # BỎ QUA CÓ CHỦ Ý, không phải hỏng. Đường đang nhanh thì một khoảng
            # lặng ngắn nghe tự nhiên hơn hẳn câu đệm chèn vào.
            #
            # Tách khỏi nhánh dưới vì bản cũ gộp cả hai và LUÔN in "KHÔNG có
            # filler" - đọc log không phân biệt được máy đang chạy đúng hay kho
            # câu đệm hỏng, và đó đúng là thứ đã làm mất một buổi truy lỗi.
            logger.info("Bỏ câu đệm (%s) -> khách chờ %sms, ngắn nên nghe tự nhiên",
                        metrics["filler_bo_qua"], metrics.get("ttfa_ms", "-"))
        elif soi:
            # Chế độ soi không sinh tiếng, nên "khách chờ im lặng" ở nhánh dưới
            # là vô nghĩa: không có khách và không có tiếng nào để chờ. Để nó rơi
            # xuống đó là dựng lại ĐÚNG cái log gây hiểu nhầm mà chú thích ngay
            # trên vừa nói đã tốn một buổi truy lỗi.
            logger.info("Chế độ soi: không câu đệm, không sinh tiếng (đúng thiết kế)")
        else:
            # Tới đây mới THẬT SỰ là không tìm được câu đệm nào - khách phải chờ
            # im lặng hết TTFA. `pick_filler` đã ghi log chi tiết vì sao trượt.
            logger.warning(
                "KHÔNG có filler cho giọng '%s' -> khách chờ im lặng đủ %sms",
                session.voice_name, metrics.get("ttfa_ms", "-"),
            )
        logger.info(
            "Turn complete%s: TTFA=%sms Total=%dms | %d token, %d mảnh%s",
            " (soi)" if soi else "",
            metrics.get("ttfa_ms", "-"), metrics["total_ms"], n_tokens, chunks_enqueued,
            # "mảnh TTS" khi KHÔNG gọi TTS là đọc log ra kết luận sai. Mảnh vẫn
            # được cắt như thường, chỉ không ai sinh tiếng cho nó.
            " (đã cắt, không sinh tiếng)" if soi else " TTS",
        )

    async def _send_audio(self, ws: WebSocket, wav_bytes: bytes, chunk_id: int = 0,
                          is_filler: bool = False, turn_id: int = 0,
                          text: str = ""):
        # turn_id: client so với lượt nó đang chờ, lệch thì bỏ. Huỷ lượt cũ ở
        # phía server đã chặn gần hết, nhưng mảnh đã nằm trong đệm socket thì
        # vẫn tới nơi - đây là chốt chặn cuối.
        #
        # `text` là chữ của chính mảnh này. Đường thoại ghi nó vào sổ mảnh phát
        # (`SoManhPhat`) để biết khách nghe tới đâu khi bị cắt lời - không có nó
        # thì lúc cắt chỉ biết bỏ bao nhiêu KHUNG, không biết đó là những CHỮ
        # nào, và không thể đọc nốt phần dở. Trình duyệt bỏ qua trường lạ.
        data = base64.b64encode(wav_bytes).decode()
        await ws.send_json({
            "type": "audio", "data": data, "chunk_id": chunk_id,
            "is_filler": is_filler, "turn_id": turn_id, "text": text,
        })

    async def _send_event(self, ws: WebSocket, event_type: str, payload: dict):
        await ws.send_json({"type": event_type, **payload})
