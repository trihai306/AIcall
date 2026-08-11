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


async def _ham_hinh_dang_tts(state: AppState):
    """Hâm các hình dạng tensor của TTS. Chạy nền, hỏng cũng không sao."""
    try:
        ket = await state.tts.ham_nong_hinh_dang()
        logger.info("  TTS: đã hâm %d hình dạng (%dms) - lượt đầu khỏi biên dịch",
                    ket["hinh_dang"], ket["ms"])
    except Exception as e:
        logger.warning("  TTS: hâm hình dạng không được (%s) - lượt đầu sẽ chậm hơn", e)


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
    from backend.services.filler_situation import chuan_hoa
    from backend.services.filler_store import lay_kho
    try:
        kho = lay_kho()
        state.kho_vector = {
            t.id: chuan_hoa(state.rag.embed(list(t.vi_du)))
            for t in kho.tinh_huong if t.vi_du
        }
        logger.info("Đã nhúng ví dụ của %d tình huống", len(state.kho_vector))
    except Exception as e:
        # Không có phân loại thì câu đệm rơi về rổ chung, tức đúng hành vi cũ.
        # Đây KHÔNG phải lỗi chặn khởi động.
        state.kho_vector = {}
        logger.warning("Không nhúng được ví dụ tình huống, câu đệm sẽ dùng rổ "
                       "chung: %s", e)

    # 4. Check STT server
    logger.info("[4/6] Checking Whisper STT server...")
    stt_ok = await state.stt.health_check()
    if stt_ok:
        logger.info("  STT server: OK")
    else:
        logger.warning("  STT server: NOT AVAILABLE - start whisper-server first")

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
        await state.tts.dung_fillers(lay_kho())
        logger.info("  TTS: OK")

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
