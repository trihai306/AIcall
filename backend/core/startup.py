import asyncio
import time
import logging
from backend.config import settings
from backend.models.db import init_db, close_db
from backend.models import scenarios_db
from backend.services.stt_service import STTService
from backend.services.llm_service import LLMService
from backend.services.tts_service import F5TTSService
from backend.services.rag_service import RAGService
from backend.services.vad_service import VADService
from backend.pipeline.streaming_pipeline import StreamingPipeline
from backend.services.filler_store import lay_kho
from backend.pipeline.session_manager import SessionStore
from backend.core.device import get_system_info

logger = logging.getLogger(__name__)


class AppState:
    """Holds all services and shared state."""

    def __init__(self):
        self.stt = STTService()
        self.llm = LLMService()
        self.tts = F5TTSService()
        self.rag = RAGService()
        self.vad = VADService()
        self.sessions = SessionStore()
        self.pipeline: StreamingPipeline | None = None
        self.kho_vector: dict = {}
        # Bảng hỏi-đáp: {id: dòng} và {id: ma trận đã chuẩn hoá}.
        self.hoi_dap: dict = {}
        self.hoi_dap_vector: dict = {}
        self.hoi_dap_provenance: dict = {}


async def _ham_hinh_dang_tts(state: AppState):
    """Hâm các hình dạng tensor của TTS. Chạy nền, hỏng cũng không sao."""
    try:
        ket = await state.tts.ham_nong_hinh_dang()
        logger.info("  TTS: đã hâm %d hình dạng (%dms) - lượt đầu khỏi biên dịch",
                    ket["hinh_dang"], ket["ms"])
    except Exception as e:
        logger.warning("  TTS: hâm hình dạng không được (%s) - lượt đầu sẽ chậm hơn", e)


def _nhung_theo_nhom(rag, nhom):
    """Nhúng nhiều nhóm văn bản bằng đúng một lần gọi model.

    Trả ``{id: ma_tran_da_chuan_hoa}``, giữ nguyên thứ tự ví dụ trong từng nhóm.
    BGE-M3 có overhead đáng kể cho mỗi lần ``encode``; lúc startup ta đã có sẵn
    toàn bộ văn bản nên gom batch sẽ rẻ hơn nhiều so với gọi từng tình huống.
    """
    from backend.services.filler_situation import chuan_hoa

    van_ban = []
    lat_cat = []
    for ma, ds in nhom:
        ds = list(ds or ())
        if not ds:
            continue
        bat_dau = len(van_ban)
        van_ban.extend(ds)
        lat_cat.append((ma, bat_dau, len(van_ban)))

    if not van_ban:
        return {}

    vector = chuan_hoa(rag.embed(van_ban))
    if vector.shape[0] != len(van_ban):
        raise ValueError(
            f"Embedding trả {vector.shape[0]} vector cho {len(van_ban)} văn bản"
        )
    return {ma: vector[bat_dau:ket_thuc]
            for ma, bat_dau, ket_thuc in lat_cat}


async def _nhung_cpu(rag, nhom):
    """Keep the caller's serialization scope until native encoding ends."""
    task = asyncio.create_task(asyncio.to_thread(_nhung_theo_nhom, rag, nhom))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # Repeated cancellation must not cancel the asyncio wrapper either:
        # the native thread would continue after its serialization lock exits.
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
        task.result()
        raise


def _tep_vector_hoi_dap():
    """Tệp giữ vector đã nhúng của kho trả lời, riêng cho từng model nhúng."""
    import hashlib
    from pathlib import Path
    from backend.services.bang_hoi_dap import RETRIEVAL_LAYOUT_VERSION
    khoa = hashlib.sha1(
        f"{settings.embedding_model}|{RETRIEVAL_LAYOUT_VERSION}".encode()).hexdigest()[:12]
    return Path(settings.hoi_dap_vector_cache_dir) / f"hoi_dap_vector_{khoa}.npz"


def _doc_vector_da_luu() -> dict:
    """{sha1(văn bản): vector đã chuẩn hoá}. Hỏng hay thiếu thì coi như rỗng."""
    import numpy as np
    try:
        with np.load(_tep_vector_hoi_dap(), allow_pickle=False) as tep:
            return dict(zip(tep["khoa"].tolist(), tep["vector"]))
    except Exception:
        return {}


def _ghi_vector_da_luu(theo_khoa: dict) -> None:
    import os
    import numpy as np
    if not theo_khoa:
        return
    tep = _tep_vector_hoi_dap()
    try:
        tep.parent.mkdir(parents=True, exist_ok=True)
        tam = tep.with_suffix(".tmp.npz")
        khoa = list(theo_khoa)
        np.savez(tam, khoa=np.asarray(khoa), vector=np.stack([theo_khoa[k] for k in khoa]))
        os.replace(tam, tep)
    except Exception as e:
        logger.warning("Không lưu được vector kho trả lời: %s", e)


# Từ ngần này văn bản mới trở lên thì mượn GPU một lúc thay vì nhúng trên CPU.
NHUNG_GPU_TU = 200


def _nhung_tam_tren_gpu(texts: list[str]):
    """Nhúng hàng loạt bằng một bản model TẠM trên GPU rồi trả VRAM ngay.

    Model nhúng thường trú ở CPU để nhường VRAM cho STT/LLM/TTS, đủ cho một câu
    khách mỗi lượt nhưng nhúng cả kho thì 15.000 văn bản mất 36 phút. Đo
    08-10-2026 trên RTX 5070: bản fp16 trên GPU nhúng 3.000 văn bản trong 1,0s,
    đỉnh 2,6GB, cosine so với bản CPU thấp nhất 0,999997. Lỗi gì (không có GPU,
    hết VRAM) cũng trả None để đường CPU cũ lo.
    """
    try:
        import numpy as np
        import torch
        if not torch.cuda.is_available():
            return None
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(settings.embedding_model, device="cuda")
        try:
            model.half()
            vec = np.asarray(model.encode(texts, batch_size=128), dtype=np.float32)
        finally:
            del model
            torch.cuda.empty_cache()
        chuan = np.linalg.norm(vec, axis=1, keepdims=True)
        chuan[chuan == 0] = 1.0
        return vec / chuan
    except Exception as e:
        logger.warning("Nhúng tạm trên GPU không được, quay về CPU: %s", e)
        return None


async def _nhung_bang_hoi_dap(state, dong):
    """Nhúng kho trả lời, CHỈ tính những văn bản chưa có trong tệp đã lưu.

    Trước 08-10-2026 mỗi lần khởi động nhúng lại TRỌN kho trên CPU: 2.700 đáp án
    mất ~10 phút, 5.500 đáp án (16.000 văn bản, 511 lô) mất 36 phút - backend
    không trả lời nổi một câu trong suốt quãng đó. Vector của một văn bản không
    đổi khi kho thêm dòng, nên giữ lại theo sha1 của chữ; lần sau chỉ nhúng phần
    mới. Đổi model nhúng hay bố cục truy hồi là sang tệp khác (xem khoá tên tệp).
    """
    import hashlib
    import numpy as np
    from backend.services.bang_hoi_dap import retrieval_texts, RETRIEVAL_LAYOUT_VERSION

    def khoa(text: str) -> str:
        return hashlib.sha1(text.encode("utf-8")).hexdigest()

    rag = state.rag
    groups = [(row["id"], retrieval_texts(row)) for row in dong]
    da_luu = _doc_vector_da_luu()
    thieu = list(dict.fromkeys(
        text for _, texts in groups for text in texts if khoa(text) not in da_luu))
    if thieu:
        logger.info("Kho trả lời: nhúng %d văn bản mới, dùng lại %d vector đã lưu",
                    len(thieu), len(da_luu))
        nhanh = None
        if len(thieu) >= NHUNG_GPU_TU:
            nhanh = await asyncio.to_thread(_nhung_tam_tren_gpu, thieu)
        if nhanh is not None:
            da_luu.update({khoa(text): vec for text, vec in zip(thieu, nhanh)})
        else:
            nhom = [(text, (text,)) for text in thieu]
            if str(settings.embedding_device).lower() == "cpu":
                moi = await _nhung_cpu(rag, nhom)
            else:
                moi = _nhung_theo_nhom(rag, nhom)
            da_luu.update({khoa(text): np.asarray(moi[text][0]) for text in thieu})
    can = {khoa(text) for _, texts in groups for text in texts}
    if thieu or len(da_luu) > len(can):
        # Chỉ giữ vector của văn bản còn trong kho, không để tệp phình mãi.
        _ghi_vector_da_luu({k: v for k, v in da_luu.items() if k in can})
    vectors = {ma: np.stack([da_luu[khoa(text)] for text in texts])
               for ma, texts in groups if texts}
    state.hoi_dap_vector = vectors
    state._hoi_dap_vector_rag = rag
    state._hoi_dap_vector_layout = RETRIEVAL_LAYOUT_VERSION


async def startup(state: AppState):
    """Initialize all services at app startup."""
    logger.info("=" * 50)
    logger.info("Starting AI Banking Call System")
    logger.info("=" * 50)

    sys_info = get_system_info()
    state.system_info = sys_info
    logger.info(f"  Platform: {sys_info['platform']} ({sys_info['arch']})")
    logger.info(f"  Device:   {sys_info['device']} - {sys_info.get('gpu_name', 'CPU')}")
    logger.info(f"  PyTorch:  {sys_info['torch']}")

    # 1. Call history database (fast, local)
    logger.info("[1/6] Initializing SQLite database...")
    await init_db(settings.db_file)
    # Quarantine generated answers whose knowledge file changed while the app
    # was stopped, before the existing Q&A vector snapshot is constructed.
    try:
        from backend.services.answer_bank_learning import prepare_sources
        prepare_sources()
    except Exception as e:
        logger.warning("Không kiểm tra được độ mới thư viện trả lời: %s", e)
    # An install upgraded from before scenarios existed has none at all, and a
    # campaign with no scenario would lose the worked examples that used to be
    # hard-coded in the prompt. Seed the shipped one from .env, once.
    if await scenarios_db.ensure_default(settings.bank_name, settings.agent_name):
        logger.info("  Đã tạo kịch bản mặc định từ cấu hình trong .env")

    # 2. VAD (lightweight, CPU)
    logger.info("[2/6] Loading VAD...")
    state.vad.load()

    # 3. RAG + Knowledge base
    logger.info("[3/6] Loading RAG + Knowledge base...")
    state.rag.load()
    state.rag.ingest_directory("./knowledge")

    # Nhúng sẵn ví dụ của mọi tình huống. Làm một lần ở đây chứ không mỗi lượt:
    # lúc khách đang nói ta chỉ được nhúng ĐÚNG MỘT chuỗi (phiên âm dở), so với
    # ma trận đã có sẵn.
    from backend.services.filler_store import MA_NHOM_CHUNG, lay_kho
    try:
        kho = lay_kho()
        # BỎ nhóm chung, cùng lý do với `api/fillers._nhung_lai_vi_du`: nó là
        # đường rơi cuối chứ không phải một chủ đề để tranh điểm. Hai chỗ nhúng
        # PHẢI cùng luật - sót một chỗ thì lần khởi động sau nó lại vào bộ chấm
        # và mọi thứ âm thầm quay về như cũ.
        state.kho_vector = _nhung_theo_nhom(
            state.rag,
            ((t.id, t.vi_du) for t in kho.tinh_huong
             if t.vi_du and t.id != MA_NHOM_CHUNG),
        )
        logger.info("Đã nhúng ví dụ của %d tình huống", len(state.kho_vector))

        # Managed answers are retrieval evidence; question examples are optional.
        # Hỏng thì bỏ qua, KHÔNG chặn khởi động - bảng rỗng nghĩa là chạy y như
        # trước khi có nó.
        try:
            from backend.models import db as _db
            from backend.services.bang_hoi_dap import doc_dong
            conn = _db.connection()
            dong = doc_dong(conn) if conn is not None else []
        except Exception as e:
            dong = []
            logger.warning("Không đọc được bảng hỏi-đáp: %s", e)
        state.hoi_dap = {d["id"]: d for d in dong}
        try:
            from backend.services.answer_bank_learning import active_provenance
            state.hoi_dap_provenance = active_provenance()
        except Exception:
            state.hoi_dap_provenance = {}
        await _nhung_bang_hoi_dap(state, dong)
        if dong:
            logger.info("Đã nhúng %d dòng bảng hỏi-đáp", len(state.hoi_dap_vector))
    except Exception as e:
        # Không có phân loại thì câu đệm rơi về rổ chung, tức đúng hành vi cũ.
        # Đây KHÔNG phải lỗi chặn khởi động.
        state.kho_vector = {}
        logger.warning("Không nhúng được ví dụ tình huống, câu đệm sẽ dùng rổ "
                       "chung: %s", e)

    # 4. Check STT server
    logger.info("[4/6] Checking STT engine: %s...", state.stt.engine)
    stt_ok = await state.stt.health_check()
    if stt_ok:
        logger.info("  STT server: OK")
    else:
        logger.warning("  STT unavailable - check %s model/runtime", state.stt.engine)

    # 5. Check LLM
    logger.info("[5/6] Checking Ollama LLM...")
    llm_ok = await state.llm.health_check()
    if llm_ok:
        logger.info("  LLM: OK")
    else:
        logger.warning("  LLM: NOT AVAILABLE - start ollama and pull model first")

    # 6. TTS (GPU, slowest to load)
    logger.info("[6/6] Loading F5-TTS Vietnamese...")
    try:
        state.tts.load()
        if settings.cau_dem_bat or settings.cau_dem_luot_sinh:
            # Câu đệm muộn (`cau_dem_luot_sinh`) dùng chung kho clip này.
            await state.tts.dung_fillers(lay_kho())
        else:
            logger.info("  Câu đệm đang TẮT (CAU_DEM_BAT=false): bỏ qua dựng tiếng câu đệm")
        logger.info("  TTS: OK")

        # Tiếng sẵn cho bảng hỏi-đáp (services/tieng_san.py): chữ cố định,
        # dựng một lần ra đĩa; lượt trúng bảng phát thẳng không gọi F5. Vài chục
        # câu, mỗi câu ~1s - khác hẳn câu đệm (hàng nghìn clip). Hỏng thì bỏ
        # qua, lượt vẫn đi F5 như trước.
        if settings.tieng_san_bat and state.hoi_dap:
            try:
                from backend.services.answer_bank_learning import provenance_for_ids
                from backend.services.tieng_san import kho_tieng_san
                generated = set(provenance_for_ids(tuple(state.hoi_dap)))
                legacy = {f"hd_{ma}": d.get("tra_loi", "")
                          for ma, d in state.hoi_dap.items() if ma not in generated}
                kq = await kho_tieng_san.dung_nhieu(
                    state.tts, legacy, state.tts.default_voice_name())
                logger.info("  Tiếng sẵn bảng hỏi-đáp: dựng %d, đã có %d, bỏ qua %d, "
                            "hỏng %d (%dms)", kq["dung"], kq["da_co"], kq["bo_qua"],
                            kq["hong"], kq["ms"])
            except Exception as e:
                logger.warning("  Tiếng sẵn bảng hỏi-đáp hỏng, bỏ qua: %s", e)

        # Đáp án Shinhan cố định đã có nguồn đối chiếu: dựng cả bản nói độc lập
        # và bản nối sau câu đệm "Dạ" trước khi báo app sẵn sàng. Nếu bỏ qua,
        # khách đầu tiên phải đợi F5 dù tra đáp án chỉ tốn vài mili giây.
        if settings.tieng_san_bat:
            try:
                from backend.pipeline.noi_cau_dem import loi_sau_dem
                from backend.pipeline.shinhan_fast_facts import dap_an_da_xac_minh
                from backend.services.tieng_san import kho_tieng_san

                cac = {}
                for ma, answer in dap_an_da_xac_minh().items():
                    key = f"ltg_shinhan_{ma}"
                    cac[key] = answer
                    continuation = loi_sau_dem("Dạ", answer)
                    if continuation != answer:
                        cac[key + "_noi_dem"] = continuation
                if cac:
                    kq = await kho_tieng_san.dung_nhieu(
                        state.tts, cac, state.tts.default_voice_name())
                    logger.info("  Tiếng sẵn Shinhan: dựng %d, đã có %d, hỏng %d (%dms)",
                                kq["dung"], kq["da_co"], kq["hong"], kq["ms"])
            except Exception as e:
                logger.warning("  Tiếng sẵn Shinhan hỏng, lượt vẫn dùng F5: %s", e)

        # HÂM HÌNH DẠNG TTS. Cùng lý lẽ với phần hâm LLM ngay dưới đây.
        #
        # torch.compile lưu đồ thị theo hình dạng tensor, mà `fix_duration` cấp
        # thời lượng theo số âm tiết nên mỗi độ dài là một hình dạng riêng. Đo
        # được: lần đầu gặp một độ dài mất 610ms, các lần sau 315ms. Trên 12 câu
        # độ dài khác nhau thì lượt một tốn hơn lượt hai 30%.
        #
        # Không hâm thì cái giá đó rơi vào những lượt đầu của cuộc gọi đầu -
        # đúng lúc khách vừa bắt máy. Chạy NỀN để web mở được ngay.
        asyncio.create_task(_ham_hinh_dang_tts(state))
    except Exception as e:
        # exc_info: không có stack trace thì chỉ biết "nạp hỏng" chứ không biết
        # hỏng ở đâu, mà đây là lỗi làm toàn bộ sản phẩm câm tiếng.
        logger.error(f"  TTS: NẠP HỎNG - {e}", exc_info=True)
        logger.error("  Hệ thống chạy tiếp ở chế độ CHỈ VĂN BẢN - mọi lượt sẽ không có tiếng.")

    # HÂM MODEL LLM. Bắt buộc, không phải tối ưu cho vui.
    #
    # Đo ba lần trong cùng một buổi: lượt LLM ĐẦU TIÊN sau khi khởi động backend
    # mất 5906-7225ms, trong khi lượt thứ hai chỉ 150ms. Chênh gần 50 lần.
    # Ollama nạp trọng số vào VRAM và dựng đồ thị tính toán ở lần gọi đầu.
    #
    # Không hâm ở đây thì người trả giá là CUỘC GỌI ĐẦU TIÊN của ngày - đúng lúc
    # khách vừa bắt máy, im lặng 7 giây rồi mới nghe tiếng. Hâm ở đây thì cái giá
    # đó rơi vào lúc khởi động, không ai nghe thấy.
    #
    # Chạy NỀN chứ không chặn: hâm mất vài giây, mà web phải mở được ngay.
    async def _ham_llm():
        try:
            t0 = time.perf_counter()
            await state.llm.generate_simple("xin chào")
            logger.info("  LLM: đã hâm (%.0fms) - cuộc gọi đầu không phải trả giá này",
                        (time.perf_counter() - t0) * 1000)
        except Exception as e:
            logger.warning("  LLM: hâm không được (%s) - cuộc gọi đầu sẽ chậm ~6 giây", e)

    asyncio.create_task(_ham_llm())

    # Hâm chuỗi xử lý tiếng xuống điện thoại. Lần gọi ĐẦU của tiến trình mất
    # 442ms (đo trên Win 11-09-2026; sau đó 8-32ms/mảnh) - không hâm thì cái giá
    # đó rơi đúng vào câu chào của cuộc gọi đầu tiên.
    async def _ham_duong_xuong():
        try:
            import numpy as np
            from backend.services.phone_call_service import xu_ly_tieng_xuong
            t0 = time.perf_counter()
            x = np.random.default_rng(0).normal(0, 0.05, 24000).astype(np.float32)
            await asyncio.to_thread(xu_ly_tieng_xuong, x, 24000)
            logger.info("  Đường xuống: đã hâm (%.0fms)", (time.perf_counter() - t0) * 1000)
        except Exception as e:
            logger.warning("  Đường xuống: hâm không được (%s)", e)

    asyncio.create_task(_ham_duong_xuong())

    # Dựng sẵn tiếng cho câu của luật có con số hay gặp (số tiền, kỳ hạn), để
    # mọi tổ hợp ghép ra tiếng ngay - xem `services/dung_san_manh_so.py`. Chạy
    # nền, từng câu một, nghỉ khi đang có cuộc gọi.
    from backend.services import dung_san_manh_so
    state._viec_dung_san_manh = asyncio.create_task(dung_san_manh_so.chay_nen(state))

    # Build pipeline
    state.pipeline = StreamingPipeline(
        stt=state.stt,
        llm=state.llm,
        tts=state.tts,
        rag=state.rag,
    )

    # Hàng đợi tóm tắt cuộc gọi. Chạy nền, tuần tự, sau khi cuộc gọi kết thúc.
    from backend.services.summarizer import bo_tom_tat
    bo_tom_tat.khoi_dong(state.llm)

    # Hẹn giờ gửi tổng hợp cuối ngày qua Telegram. Không có kênh nào thì nó chỉ
    # thức dậy mỗi phút rồi ngủ tiếp — không tốn gì.
    from backend.services.notify_service import lich_tong_hop
    lich_tong_hop.khoi_dong()

    # Bật lại tự nhận cuộc gọi trên các máy đã bật từ lần chạy trước. Không có
    # bước này thì mỗi lần khởi động lại là mọi cuộc gọi vào rơi vào hư không mà
    # không ai biết.
    try:
        from backend.services.inbound_service import goi_vao
        await goi_vao.khoi_phuc(state)
    except Exception as e:
        logger.warning(f"Không bật lại được tự nhận cuộc gọi: {e}")

    # The worker starts only after LLM/TTS checks and the live pipeline exist.
    # It immediately yields to customer turns/training and resumes checkpoints.
    try:
        from backend.services.answer_bank_learning import bo_hoc_tra_loi
        bo_hoc_tra_loi.khoi_dong(state)
    except Exception as e:
        logger.warning("Không khởi động được bộ chuẩn bị thư viện trả lời: %s", e)

    logger.info("=" * 50)
    logger.info("System ready!")
    logger.info(f"  Open http://localhost:{settings.port} in your browser")
    logger.info("=" * 50)


async def shutdown(state: AppState):
    """Cleanup on app shutdown."""
    logger.info("Shutting down...")
    # Dừng chiến dịch TRƯỚC khi đóng CSDL: mỗi cuộc gọi đang chạy còn phải ghi
    # kết quả, và số nào đang ở trạng thái 'calling' phải được trả về hàng đợi.
    try:
        from backend.services.campaign_runner import campaigns
        await campaigns.stop_all()
    except Exception as e:
        logger.warning(f"Không dừng gọn được chiến dịch đang chạy: {e}")
    try:
        from backend.services.inbound_service import goi_vao
        await goi_vao.tat_het()
    except Exception as e:
        logger.warning(f"Không dừng gọn được bộ nhận cuộc gọi: {e}")
    for ten, dung in (
        ("thư viện trả lời tự động", "backend.services.answer_bank_learning:bo_hoc_tra_loi"),
        ("tóm tắt", "backend.services.summarizer:bo_tom_tat"),
        ("hẹn giờ tổng hợp", "backend.services.notify_service:lich_tong_hop"),
    ):
        try:
            mod, attr = dung.split(":")
            await getattr(__import__(mod, fromlist=[attr]), attr).dung()
        except Exception as e:
            logger.debug(f"Không dừng được tác vụ nền {ten}: {e}")
    await state.stt.close()
    await close_db()
