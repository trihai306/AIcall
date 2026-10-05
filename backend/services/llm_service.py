import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
import httpx
import ollama
from backend.config import settings
from backend.services.cua_so_nho import canh_bao_tran, doc_so_token
from backend.pipeline.text_normalizer import bo_chu_la, co_chu_la
from backend.core.logging_config import Timer

logger = logging.getLogger(__name__)

# Chuỗi bắt model DỪNG sinh.
#
# Trước 08-09 chỉ có ["Khách:", "\n\n"] và nó KHÔNG đủ. Bắt được lượt này trong
# bản ghi hội thoại thật:
#
#     AI: ...Anh có nhu cầu vay bao nhiêu tiền và thời gian thế nào
#         user
#         Alo em chào anh, anh đang cần vay tín chấp thì lãi suất bao nhiêu?
#
# Model tuột về khuôn ChatML thô, tự viết nhãn vai trò rồi ĐỌC LẠI CÂU HỎI CỦA
# KHÁCH. Khách nghe thành "AI lặp lại ở cuối câu". Hai chuỗi cũ đều trượt:
# "Khách:" là tiếng Việt còn model nhả nhãn tiếng Anh "user"; "\n\n" cần HAI
# dòng trống trong khi model chỉ xuống MỘT dòng.
#
# Nên chặn cả ba họ: nhãn vai trò tiếng Anh, nhãn tiếng Việt, và token đặc biệt
# của khuôn mẫu. Đặt sau "\n" để không cắt nhầm chữ "user" hay "khách" nằm giữa
# câu (vd "khách hàng của bên em").
CHUOI_DUNG = [
    "\n\n",
    "\nuser", "\nUser", "\nUSER",
    "\nassistant", "\nAssistant",
    "\nsystem", "\nSystem",
    "Khách:", "\nKhách", "\nKhach", "\nNhân viên:", "\nTư vấn viên:",
    "<|im_end|>", "<|im_start|>", "<|endoftext|>",
]

# ĐỪNG ĐẶT CON SỐ DẠNG PHẦN TRĂM VÀO BẤT KỲ VÍ DỤ NÀO TRONG PROMPT DƯỚI ĐÂY.
#
# Đã mắc một lần và mất khá lâu mới tìm ra: hai chỗ trong prompt có ví dụ
# "sáu phẩy năm phần trăm" (một ở quy tắc viết số thành chữ, một ở ví dụ độ dài
# câu trả lời). Mô hình CHÉP NGUYÊN con số đó ra làm LÃI SUẤT, trong khi tài liệu
# ghi 7.9%/năm - tức báo cho khách một mức thấp hơn thực tế 1.4 điểm phần trăm,
# trong cuộc gọi bán sản phẩm tài chính.
#
# Đã tách bạch bằng thí nghiệm (scripts/soi_nguon_65.py): với prompt tối giản
# kèm tài liệu, mô hình trả lời ĐÚNG 7.9%; chỉ khi dùng prompt đầy đủ này nó mới
# ra 6.5%. Nên lỗi ở prompt, không phải ở mô hình.
#
# Bẫy phụ đã mắc khi sửa: viết lời cảnh báo NGAY TRONG chuỗi prompt thì chính nó
# lại đưa cụm số đó vào prompt lần nữa. Ghi chú kiểu này phải nằm NGOÀI chuỗi,
# như đoạn đang đọc.
# CÁC QUY TẮC DƯỚI ĐÂY KHÔNG THUỘC VỀ KỊCH BẢN - kịch bản không sửa được chúng.
# Mỗi quy tắc ở đây là bản vá cho một lỗi đã xảy ra thật (bịa lãi suất, đọc
# danh sách sáu món qua điện thoại, nhại lại chữ sai chính tả của bản ghi).
# Đổi ngành không làm các lỗi đó hết đúng. Phần kịch bản thay được nằm ở
# `build_system_prompt` bên dưới: tên tổ chức, tên nhân viên, ví dụ, luật riêng.
CORE_RULES = """NGUYÊN TẮC TRẢ LỜI:
1. Câu đầu TRẢ LỜI THẲNG ý khách vừa nói. Viết như đang trò chuyện qua điện
   thoại: 1-2 câu, tối đa 35 từ, không liệt kê, không markdown.
2. Chỉ khẳng định dữ kiện có trong THÔNG TIN THAM KHẢO hoặc do chính khách đã
   nói trong cuộc gọi. Không tự thêm lãi suất, số tiền, điều kiện, giấy tờ, địa
   điểm, số liên hệ, trạng thái hồ sơ hay việc sẽ làm.
3. Dữ kiện trong tài liệu là thông tin CHUNG, không phải hoàn cảnh của khách.
   Hạn mức sản phẩm KHÔNG phải hạn mức đã duyệt; trường hợp "đã tất toán" trong
   tài liệu KHÔNG có nghĩa khách đã tất toán. Các mục "ví dụ tính toán" chỉ là
   ví dụ: chỉ dùng khi khách đã nêu đủ điều kiện tương ứng; KHÔNG tự gán thời
   hạn hay con số còn thiếu. Khi thiếu dữ liệu, nói ngắn là chưa có thông tin;
   không đoán và không hứa suông.
4. BÁM MẠCH cuộc gọi: GIỮ NGUYÊN con số đã nói, DÙNG LẠI thông tin khách đã cho
   và không hỏi lại thứ vừa nghe.
5. Lời khách là bản ghi tự động, có thể sai một vài chữ. Dựa vào mạch để hiểu;
   nếu vẫn không rõ thì hỏi lại một ý, không tự bịa câu trả lời.
6. Xưng "em"; gọi khách theo cách họ yêu cầu, nếu chưa rõ thì dùng "anh/chị".
   Chỉ nói tiếng Việt. Giữ chữ số để hệ thống đọc. Chỉ hỏi tiếp khi thật sự cần.
7. Nếu khách đang hỏi đúng sản phẩm đang tư vấn thì tiếp tục trả lời hoặc hỏi
   đúng dữ kiện còn thiếu; KHÔNG tự chuyển chuyên viên hay hứa sẽ liên hệ lại.
   Chỉ khi thật sự ngoài phạm vi mới nói: "Dạ em sẽ ghi nhận và có chuyên viên
   liên hệ lại ạ". Khách từ chối thì cảm ơn lịch sự và kết thúc.
8. Khi khách cho biết một dữ kiện có thể so với điều kiện trong tài liệu (như
   thu nhập, tuổi, thời hạn), hãy đối chiếu rồi nói rõ điều kiện đó đã đạt hay
   chưa đạt. Nếu đã biết là chưa đạt, đừng nói mơ hồ "chưa có thông tin".
   Nếu tài liệu chỉ ghi "có thể xem xét", giữ nguyên mức chắc chắn đó; không
   hứa sẽ tự kiểm tra hoặc hồ sơ sẽ được duyệt khi chưa có kết quả tra cứu.
9. Nếu khách hỏi nhiều ý, trả lời ý nào có căn cứ rồi nói rõ ý nào chưa có căn
   cứ. Đừng nói thiếu thông tin về toàn bộ sản phẩm khi tài liệu có một phần."""

# Vì sao phải nhắc lại: mô hình 3B quên ràng buộc độ dài khi prompt dài. Đặt sát
# lượt của khách nên nó "nhớ" hơn là luật số 2 nằm tận đầu prompt.
#
# Dòng đầu là TRẢ LỜI THẲNG chứ không phải độ dài: đo 07-08 bằng
# `scripts/cham_chat_luong.py`, lỗi nhiều nhất là "không trả lời thẳng" (9/54),
# gấp đôi mọi lỗi khác. Nhắc độ dài trước thì mô hình dồn sức cắt chữ và càng né
# câu hỏi.
CORE_REMINDER = ('TRẢ LỜI THẲNG, tự nhiên trong 1-2 câu. Không có nguồn thì '
                 'không khẳng định. Xưng "em", mở đầu lịch sự theo cách khách chọn; '
                 'không lặp "Dạ" ở mọi lượt.')

# Bản dùng khi lượt này ĐÃ phát câu đệm. Hai khác biệt, cả hai đều cần:
#
#   1. Đưa NGUYÊN VĂN câu đệm vào. Mô hình cần biết đã nói CHỮ GÌ để khỏi lặp ý,
#      chứ biết "đã có câu đệm" thì không đủ - đo 06-09-2026: câu đệm nói "Dạ về
#      phần tài liệu," rồi mô hình đáp "em sẽ gửi thông tin chi tiết về sản phẩm
#      vay tín chấp cho anh ngay", tức nói lại đúng ý vừa nói.
#   2. BỎ lời dặn 'mở đầu bằng "Dạ"'. Câu đệm gần như luôn mở bằng "Dạ" rồi; giữ
#      lại là khách nghe "Dạ ... Dạ ..." hai lần liền. Bản cũ chữa bằng cách XOÁ
#      chữ "Dạ" sau khi mô hình đã sinh (`BotLichSu(bo_da=...)`) - chữa được cái
#      chữ nhưng không chữa được việc mô hình MỞ ĐẦU LẠI cả câu.
#
# Là DỮ KIỆN của lượt, không phải quy tắc chung: quy tắc "bám mạch" thêm cùng
# ngày đã không ăn vì bị quy tắc số 3 đè (khối THÔNG TIN THAM KHẢO nằm sát câu
# hỏi hơn). Dữ kiện cụ thể thì không có gì để đè.
# Bản dùng khi lượt này ĐÃ phát câu đệm. Chỉ khác `CORE_REMINDER` ở chỗ BỎ lời
# dặn 'mở đầu bằng "Dạ"': câu đệm gần như luôn mở bằng "Dạ" rồi, giữ lại là khách
# nghe "Dạ ... Dạ ..." hai lần liền.
#
# KHÔNG dặn gì thêm về việc nối câu - việc đó do `prefill` lo, xem
# `stream_response`. Ba lần thử dặn bằng chữ đều hỏng, mỗi lần một kiểu.
NHAC_CO_CAU_DEM = ('TRẢ LỜI THẲNG, tự nhiên trong 1-2 câu. Không có nguồn thì '
                   'không khẳng định. Xưng "em".')

# Dùng khi kịch bản không khai ví dụ nào. Không có ví dụ thì mô hình hay trả lời
# dài gấp đôi - đây là chỗ nó học ĐỘ DÀI, không phải học nội dung.
_FALLBACK_EXAMPLES: list[dict] = []


class LLMService:
    """Ollama streaming client for LLM inference."""

    _INVENTORY_TTL_S = 30.0
    _INVENTORY_TIMEOUT_S = 2.0
    _CAPABILITY_TIMEOUT_S = 2.0

    def __init__(self):
        self.model = settings.ollama_model
        # httpx mặc định đóng kết nối nhàn rỗi sau 5 giây. Khách nói cách nhau lâu
        # hơn thế, nên mỗi lượt phải bắt tay TCP lại: đo được TTFT 520ms thay vì
        # 180-250ms. Giữ kết nối 10 phút để không trả cái giá đó mỗi lượt.
        self.client = ollama.AsyncClient(
            host=settings.ollama_base_url,
            limits=httpx.Limits(max_keepalive_connections=4, keepalive_expiry=600.0),
        )
        # Model có khai năng lực "thinking" không (qwen3.x có, qwen2.5 không).
        # None = chưa hỏi Ollama; lúc đó đoán theo tên. Xem `_nen_think`.
        self._ho_tro_think: bool | None = None
        self._production_model = self.model
        self._routing_state = self._new_routing_state()
        self._routing_state["services"][self._normalize_model(self.model)] = self

    @staticmethod
    def _new_routing_state() -> dict:
        """State dùng chung giữa service gốc và các service đã định tuyến."""
        return {
            "lock": asyncio.Lock(),
            "cached": False,
            "models": None,
            "expires_at": 0.0,
            "service_lock": asyncio.Lock(),
            "services": {},
            "capabilities": {},
        }

    def _get_routing_state(self) -> dict:
        # Một số test cũ dựng service bằng __new__, không chạy __init__.
        state = getattr(self, "_routing_state", None)
        if state is None:
            state = self._new_routing_state()
            self._routing_state = state
            normalized = self._normalize_model(getattr(self, "model", ""))
            if normalized:
                state["services"][normalized] = self
        return state

    @staticmethod
    def _normalize_model(name: str) -> str:
        """Chuẩn hoá duy nhất tag ngầm `latest`, vẫn so khớp tên chính xác."""
        name = (name or "").strip()
        return name if not name or ":" in name else f"{name}:latest"

    @staticmethod
    def _models_from_inventory(result) -> frozenset[str]:
        models = result.get("models", []) if isinstance(result, dict) else getattr(result, "models", [])
        names: set[str] = set()
        for item in models or []:
            if isinstance(item, dict):
                name = item.get("model") or item.get("name") or ""
            else:
                name = getattr(item, "model", None) or getattr(item, "name", "")
            normalized = LLMService._normalize_model(str(name or ""))
            if normalized:
                names.add(normalized)
        return frozenset(names)

    async def _installed_models(self) -> frozenset[str] | None:
        """Đọc inventory có cache; None nghĩa là không đọc được Ollama."""
        state = self._get_routing_state()
        now = time.monotonic()
        if state["cached"] and now < state["expires_at"]:
            return state["models"]

        async with state["lock"]:
            now = time.monotonic()
            if state["cached"] and now < state["expires_at"]:
                return state["models"]
            try:
                result = await asyncio.wait_for(
                    self.client.list(), timeout=self._INVENTORY_TIMEOUT_S
                )
                installed: frozenset[str] | None = self._models_from_inventory(result)
            except Exception as exc:
                # Không có inventory thì giữ nguyên đường production. Lỗi gọi
                # model cụ thể vẫn do đường sinh hiện hữu báo như trước.
                logger.warning("Không đọc được danh sách model Ollama: %s", exc)
                installed = None

            state["cached"] = True
            state["models"] = installed
            state["expires_at"] = time.monotonic() + self._INVENTORY_TTL_S
            return installed

    @staticmethod
    def _thinking_capability(info) -> bool:
        caps = (
            info.get("capabilities")
            if isinstance(info, dict)
            else getattr(info, "capabilities", None)
        ) or []
        return "thinking" in [str(capability).lower() for capability in caps]

    async def _service_for_model(self, model: str) -> "LLMService":
        if self._normalize_model(model) == self._normalize_model(self.model):
            return self

        state = self._get_routing_state()
        normalized = self._normalize_model(model)
        async with state["service_lock"]:
            cached = state["services"].get(normalized)
            if cached is not None:
                return cached

            try:
                info = await asyncio.wait_for(
                    self.client.show(model), timeout=self._CAPABILITY_TIMEOUT_S
                )
                supports_thinking: bool | None = self._thinking_capability(info)
            except Exception as exc:
                # None giữ đúng fallback hiện hữu của `_nen_think`: chỉ đoán
                # theo tên khi Ollama không cho biết năng lực model.
                logger.warning(
                    "Không đọc được năng lực model định tuyến %s (%s) - đoán theo tên",
                    model,
                    exc,
                )
                supports_thinking = None

            routed = LLMService.__new__(LLMService)
            routed.model = model
            routed.client = self.client
            routed._ho_tro_think = supports_thinking
            routed._production_model = getattr(self, "_production_model", self.model)
            routed._routing_state = state
            state["capabilities"][normalized] = supports_thinking
            state["services"][normalized] = routed
            return routed

    async def route_for(self, task: str) -> "LLMService":
        """Chọn một service model-bound cho `answer_selection` hoặc `response`.

        Thứ tự là model của vai trò, model production, rồi các fallback được
        cấu hình rõ ràng. Inventory chỉ dùng để xác nhận các ứng viên này; mọi
        model khác tình cờ có trên máy đều bị bỏ qua.
        """
        if task not in {"answer_selection", "response"}:
            raise ValueError(f"Unsupported LLM routing task: {task}")
        if not settings.llm_auto_routing:
            return self

        production = getattr(self, "_production_model", self.model)
        role_model = (
            settings.llm_selector_model
            if task == "answer_selection"
            else (settings.llm_response_model or production)
        )
        configured = [role_model, production]
        configured.extend(settings.llm_fallback_models.split(","))

        candidates: list[str] = []
        seen: set[str] = set()
        for candidate in configured:
            candidate = (candidate or "").strip()
            normalized = self._normalize_model(candidate)
            if candidate and normalized not in seen:
                seen.add(normalized)
                candidates.append(candidate)

        installed = await self._installed_models()
        if installed is None:
            return self
        for candidate in candidates:
            if self._normalize_model(candidate) in installed:
                return await self._service_for_model(candidate)
        return self

    async def kiem_nang_luc(self) -> None:
        """Hỏi Ollama model có biết suy nghĩ không. Gọi một lần lúc khởi động."""
        try:
            info = await self.client.show(self.model)
            self._ho_tro_think = self._thinking_capability(info)
            logger.info("LLM %s: %s", self.model,
                        "biết suy nghĩ" if self._ho_tro_think else "không có thinking")
        except Exception as e:
            logger.warning("Không đọc được năng lực model %s (%s) - đoán theo tên",
                           self.model, e)

    def _nen_think(self, prefill: str) -> bool:
        """`think=True` CHỈ khi có prefill và model biết suy nghĩ.

        Đo trên máy Win 13-09-2026, Ollama 0.34.0, qwen3.5:9b, cùng một prompt:
            có prefill, think=False -> "" (0 token, 4/4 lần, cả hai bộ stop)
            có prefill, think=True  -> " theo thông tin bên em là từ 7.9%/năm ạ."
        Ollama không chèn khối <think></think> trước tin nhắn assistant cuối khi
        think=False; qwen3.5 thấy thiếu khối đó nên dừng ngay ở token đầu. Trên
        cuộc gọi f441bc66 mọi lượt có câu đệm đều rơi về "Phần này chưa có quy
        định rõ trong tài liệu" dù tài liệu có đủ - khách nghe như AI đọc thiếu.

        Không prefill thì giữ think=False: bật lên là model suy nghĩ thật, TTFT
        đội lên hàng giây. Model không có thinking (qwen2.5) mà gửi think=True
        thì Ollama từ chối cả lượt, nên phải hỏi năng lực trước.
        """
        if not (prefill or "").strip():
            return False
        # getattr: vài test dựng LLMService bằng __new__, không qua __init__.
        ho_tro = getattr(self, "_ho_tro_think", None)
        if ho_tro is None:
            return "qwen3" in (self.model or "").lower()
        return ho_tro

    def build_system_prompt(
        self,
        customer_name: str = "Anh/Chị",
        product: str = "vay tín chấp",
        rag_context: str = "",
        scenario: dict | None = None,
        co_cong_cu: bool = False,
        gioi_tinh: str = "",
        gioi_tinh_do_tin: float | None = None,
        cau_dem: str = "",
    ) -> str:
        """Assemble the system prompt: fixed core rules + this scenario's parts.

        `scenario` is a row from models/scenarios_db (or {} / None). An empty
        scenario falls back to bank_name/agent_name from .env, which reproduces
        the behaviour from before scenarios existed - so every existing caller
        keeps working without passing anything.
        """
        sc = scenario or {}
        # Đi qua `scenarios_db` chứ không tự đọc: ba đường xưng tên phải dùng
        # CHUNG một luật, không thì cùng một cuộc gọi lại xưng hai tên khác nhau.
        from backend.models import scenarios_db
        org_name = scenarios_db.ten_to_chuc(sc)
        agent_name = scenarios_db.ten_nhan_vien(sc)

        from backend.core.conversation_style import STYLE_GUIDE
        parts = [
            f"Bạn là nhân viên tư vấn của {org_name}, tên là {agent_name}, "
            "đang gọi điện thoại cho khách.",
            "",
            CORE_RULES,
            STYLE_GUIDE,
        ]

        # Luật riêng của ngành, đánh số tiếp theo core để mô hình không thấy hai
        # danh sách rời rạc.
        extra = [line.strip() for line in (sc.get("rules") or "").splitlines() if line.strip()]
        if extra:
            numbered = "\n".join(f"{i}. {line}" for i, line in enumerate(extra, start=12))
            parts.append(numbered)

        parts.append(self._format_examples(sc.get("examples") or _FALLBACK_EXAMPLES, agent_name))

        khach = [f"- Họ tên: {customer_name}"]
        if product:
            khach.append(f"- Sản phẩm quan tâm: {product}")
        # Đã nghe ra giọng nam hay nữ thì gọi thẳng "anh" / "chị".
        #
        # `gender_detect.doan_gioi_tinh` chạy sẵn trên cuộc gọi thật và lưu vào
        # `session.gender` từ lâu, nhưng `xung_ho()` KHÔNG chỗ nào gọi - tức
        # nhận diện xong rồi vứt đi, bot vẫn đọc "anh/chị" cho mọi khách.
        #
        # Nói rõ trong prompt thay vì chỉ đưa dữ liệu: quy tắc 1 bảo "gọi khách
        # là anh/chị", để nguyên thì mô hình theo quy tắc chứ không theo dữ liệu.
        from backend.services.gender_detect import xung_ho
        cach_goi = xung_ho(gioi_tinh, gioi_tinh_do_tin)
        if cach_goi in ("anh", "chị"):
            khach.append(f"- Giới tính: {'nam' if gioi_tinh == 'male' else 'nữ'}")
            parts.append(
                f"CÁCH GỌI KHÁCH (thay cho quy tắc 1): khách này là "
                f"{'nam' if gioi_tinh == 'male' else 'nữ'}, luôn gọi \"{cach_goi}\", "
                f"TUYỆT ĐỐI không dùng \"anh/chị\"."
            )
        parts.append("THÔNG TIN KHÁCH HÀNG:\n" + "\n".join(khach))

        if rag_context:
            parts.append(f"THÔNG TIN THAM KHẢO:\n{rag_context}")

        # Mở đường cho việc gọi hàm. BẮT BUỘC phải có, không phải cho đẹp:
        #
        # Đo được 2026-08-06 - cùng câu hỏi "dư nợ của tôi còn bao nhiêu", cùng
        # bộ công cụ, chỉ khác prompt:
        #     prompt trống    -> GỌI tra_ho_so_khach
        #     prompt thật này -> KHÔNG gọi, trả lời "em sẽ kiểm tra lại và báo anh"
        #
        # Thủ phạm là chính quy tắc 3 và 4 ở CORE_RULES: chúng dạy mô hình rằng
        # thiếu dữ liệu thì NÓI SẼ KIỂM TRA LẠI. Luật đó viết hồi chưa có công cụ
        # và lúc đó đúng - né còn hơn bịa. Giờ có đường lấy dữ liệu thật thì nó
        # chặn mất lựa chọn tốt hơn, nên phải nói rõ THỨ TỰ ƯU TIÊN.
        if co_cong_cu:
            parts.append(
                "CÁCH DÙNG CÔNG CỤ (ưu tiên hơn quy tắc thiếu dữ liệu):\n"
                "- Khách hỏi con số mà THÔNG TIN THAM KHẢO không có -> GỌI HÀM để tra trước.\n"
                "- Khách hỏi về hồ sơ RIÊNG của họ (dư nợ, hợp đồng, ngày đến hạn) "
                "-> luôn GỌI HÀM tra_ho_so_khach, đừng hỏi xin số điện thoại "
                "(hệ thống đã biết số của khách đang gọi).\n"
                "- CHỈ khi gọi hàm xong mà vẫn không có dữ liệu thì mới nói "
                "\"em xin phép kiểm tra lại và báo anh/chị ngay ạ\".\n"
                "- Câu chào hỏi, từ chối, hỏi thăm thì KHÔNG gọi hàm."
            )

        # Câu đệm vừa phát -> lời nhắc NỐI TIẾP thay cho lời nhắc thường.
        # Đặt CUỐI cùng, sát lượt của khách: cùng lý do với `CORE_REMINDER` -
        # mô hình quên ràng buộc nằm tận đầu prompt khi prompt dài.
        parts.append(NHAC_CO_CAU_DEM if (cau_dem or "").strip() else CORE_REMINDER)
        return "\n\n".join(p for p in parts if p)

    @staticmethod
    def _format_examples(examples: list, agent_name: str) -> str:
        """Render worked examples as a Khách:/tên: transcript.

        Anything malformed is skipped rather than raising: these rows come from
        a UI form and a half-filled example must not take down every call.
        """
        lines = []
        for ex in examples:
            if not isinstance(ex, dict):
                continue
            khach = (ex.get("khach") or "").strip()
            tu_van = (ex.get("tu_van") or "").strip()
            if khach and tu_van:
                lines.append(f"Khách: {khach}\n{agent_name}: {tu_van}")
        if not lines:
            return ""
        return (
            "VÍ DỤ ĐỘ DÀI ĐÚNG (chỉ học CÁCH NÓI, KHÔNG lấy con số trong này):\n"
            + "\n".join(lines)
        )

    @staticmethod
    def _extract_content(msg) -> str:
        """Lấy chữ từ một message của Ollama, và CẮT chữ nước ngoài tại đây.

        Đây là chỗ nghẽn DUY NHẤT mà mọi đường lấy chữ từ LLM đều đi qua
        (`stream_response` lẫn `generate_simple`), nên chặn ở đây là chặn cho
        cả đường gọi thật lẫn đường nghe thử - không phải nhớ lắp ở từng nơi.

        Vì sao cần: bộ đọc thử 100 mẫu ngày 18-08-2026 bắt được mô hình trả ra
        *"Em có thể giúp gì cho chị今天天气不错，你打算出去玩吗？"* - 1/136 lượt
        (0,7%). F5 sẽ CỐ ĐỌC chỗ chữ Hán đó ra tiếng, khách nghe được một tràng
        vô nghĩa giữa cuộc tư vấn.
        """
        if msg is None:
            return ""
        chu = (msg.get("content", "") if isinstance(msg, dict)
               else getattr(msg, "content", "")) or ""
        if co_chu_la(chu):
            sach = bo_chu_la(chu)
            logger.warning("LLM trả ra chữ nước ngoài, đã cắt: %r -> %r", chu, sach)
            return sach
        return chu

    @staticmethod
    def _doc_tool_calls(msg) -> list[dict]:
        """Lấy danh sách hàm mô hình muốn gọi, chuẩn hoá về dict thuần.

        Thư viện ollama trả về khi thì dict khi thì đối tượng pydantic tuỳ phiên
        bản; ép về một dạng ngay tại đây để phần gọi không phải đoán.
        """
        if msg is None:
            return []
        tc = msg.get("tool_calls") if isinstance(msg, dict) else getattr(msg, "tool_calls", None)
        if not tc:
            return []
        ra = []
        for item in tc:
            f = item.get("function") if isinstance(item, dict) else getattr(item, "function", None)
            if f is None:
                continue
            ten = f.get("name") if isinstance(f, dict) else getattr(f, "name", "")
            args = f.get("arguments") if isinstance(f, dict) else getattr(f, "arguments", None)
            ra.append({"name": ten or "", "arguments": args or {}})
        return ra

    @staticmethod
    def _la_bankvn(model: str) -> bool:
        return "bankvn" in (model or "").lower()

    @staticmethod
    def _doc_bankvn_tool_calls(text: str) -> list[dict]:
        """Đọc protocol tool-call của model BankVN tự train.

        BankVN không dựa vào tool parser riêng của Ollama. Model học sinh chuỗi
        `<|bankvn_tool_call|>{...}`; backend chuẩn hoá nó về cùng shape với
        native `message.tool_calls` để phần pipeline phía trên không cần biết
        model nào đang chạy.
        """
        marker = "<|bankvn_tool_call|>"
        if marker not in (text or ""):
            return []
        payload = text.split(marker, 1)[1]
        payload = payload.split("<|bankvn_end|>", 1)[0].strip()
        try:
            obj = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            logger.warning("BankVN tool-call JSON không hợp lệ: %r", payload[:300])
            return []

        items = obj if isinstance(obj, list) else [obj]
        ra = []
        for item in items:
            if not isinstance(item, dict):
                continue
            ten = str(item.get("name") or "").strip()
            args = item.get("arguments") or {}
            if ten and isinstance(args, dict):
                ra.append({"name": ten, "arguments": args})
        return ra

    @staticmethod
    def _prompt_tool_bankvn(system_prompt: str, tools: list[dict]) -> str:
        """Nhét schema tool vào prompt cho BankVN mà không phụ thuộc template Ollama."""
        from backend.pipeline.cong_cu_llm import prompt_tool_bankvn
        return prompt_tool_bankvn(system_prompt, tools)

    async def stream_response(
        self,
        messages: list[dict],
        system_prompt: str,
        tools: list[dict] | None = None,
        on_tool_calls=None,
        prefill: str = "",
    ) -> AsyncGenerator[str, None]:
        """Stream LLM response token by token.

        `tools` gắn vào chính lượt stream này chứ không thêm một lượt hỏi riêng.
        Đo được trên máy thật: gắn tools làm TTFT đi từ 107ms lên 108ms, tức
        không tốn gì - trong khi tách thành hai lượt thì mọi lượt thường đều
        phải trả thêm một vòng sinh chữ vô ích.

        Mô hình muốn gọi hàm thì nó KHÔNG sinh chữ; ta báo qua `on_tool_calls`
        rồi kết thúc generator này. Phần chạy hàm và stream lượt hai nằm ở
        `streaming_pipeline` - chỗ đó mới cầm được phiên gọi và RAG.
        """
        bankvn_tools = bool(tools and on_tool_calls is not None and self._la_bankvn(self.model))
        if bankvn_tools:
            system_prompt = self._prompt_tool_bankvn(system_prompt, tools or [])
        from backend.core.banking_fact_precheck import banking_fact_precheck, direct_condition_answer
        direct = direct_condition_answer(messages, system_prompt, prefill)
        if direct:
            logger.info("Trả lời điều kiện đã đối chiếu trực tiếp từ nguồn")
            yield direct
            return
        checked = banking_fact_precheck(messages, system_prompt)
        if checked:
            system_prompt += "\n\nĐỐI CHIẾU ĐIỀU KIỆN VỪA TÍNH TỪ NGUỒN VÀ LỜI KHÁCH:\n" + checked
        from backend.core.conversation_style import requested_region_note, requested_address_note
        region_note = requested_region_note(messages)
        if region_note:
            system_prompt += "\n\n" + region_note
        address_note = requested_address_note(messages)
        if address_note:
            system_prompt += "\n\n" + address_note
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        # PREFILL: đặt chữ khách VỪA NGHE (câu đệm) vào miệng mô hình, nó viết
        # TIẾP thay vì mở đầu lại. Ollama 0.33.2 hỗ trợ - thử trên máy thật:
        #
        #   không prefill -> "Hạn mức vay tín chấp tối đa là 500 triệu đồng."
        #   CÓ prefill    -> " em tư vấn tối đa là 500 triệu đồng."
        #
        # tức nó tự viết thường, tự bỏ chủ ngữ, tự không lặp chữ "hạn mức" - mà
        # không cần một dòng dặn dò nào.
        #
        # VÌ SAO KHÔNG dặn bằng prompt: đã thử BA cách và hỏng ba kiểu khác nhau
        # (06-09-2026, cùng một kịch bản đo):
        #   luật chung        -> bị luật số 3 đè (khối THÔNG TIN THAM KHẢO nằm
        #                        sát câu hỏi hơn)
        #   ví dụ có nhãn SAI -> mô hình CHÉP luôn ví dụ sai
        #   mẫu dạng "A + B"  -> mô hình chép cả vế A ("Dạ về hạn mức vay thì,
        #                        Về hạn mức thì, em xin báo...")
        # Prefill không phải một lời dặn nên không có gì đè được nó.
        if (prefill or "").strip():
            full_messages = full_messages + [{"role": "assistant", "content": prefill}]
        # BankVN dùng protocol text riêng để model from-scratch không phụ thuộc
        # tool parser/template của Ollama. Các model hiện tại vẫn đi native path.
        kw = {"tools": tools} if tools and not bankvn_tools else {}
        bankvn_buffer: list[str] = []

        with Timer("LLM-TTFT", logger):
            first_token = True
            response = await self.client.chat(
                model=self.model,
                messages=full_messages,
                stream=True,
                think=self._nen_think(prefill),
                options={
                    "num_predict": settings.llm_max_tokens,
                    "temperature": 0.0 if bankvn_tools else settings.llm_temperature,
                    "num_ctx": settings.llm_num_ctx,
                    "stop": CHUOI_DUNG,
                },
                **kw,
            )
            async for chunk in response:
                msg = chunk.get("message", {}) if isinstance(chunk, dict) else getattr(chunk, "message", None)

                if tools and on_tool_calls is not None:
                    goi = self._doc_tool_calls(msg)
                    if goi:
                        logger.info("LLM xin gọi hàm: %s", [g["name"] for g in goi])
                        on_tool_calls(goi)
                        return

                token = self._extract_content(msg)
                if token:
                    if bankvn_tools:
                        bankvn_buffer.append(token)
                    else:
                        if first_token:
                            first_token = False
                            logger.info("LLM first token received")
                        yield token

                # Chunk cuối mang số token THẬT của lời dặn + lịch sử. Không
                # đọc thì việc Ollama cắt bớt hội thoại là bẫy im lặng hoàn
                # toàn - xem `cua_so_nho`.
                n_prompt = doc_so_token(chunk)
                if n_prompt is not None:
                    self._soat_cua_so(n_prompt)

            if bankvn_tools:
                text = "".join(bankvn_buffer)
                goi = self._doc_bankvn_tool_calls(text)
                if goi:
                    logger.info("BankVN xin gọi hàm: %s", [g["name"] for g in goi])
                    on_tool_calls(goi)
                    return
                # Giữ contract của stream_response cho caller khác; lượt router
                # hiện tại bỏ phần chữ này, nhưng không nên biến hàm thành im lặng.
                if text:
                    yield text

    def _soat_cua_so(self, prompt_tokens: int) -> None:
        """Kêu lên khi cửa sổ không đủ cho một cuộc tư vấn thật.

        Chỉ kêu MỘT LẦN mỗi tiến trình: cấu hình không đổi giữa chừng nên kêu
        mỗi lượt chỉ làm ngập log rồi không ai đọc nữa.
        """
        logger.debug("LLM prompt: %d/%d token", prompt_tokens, settings.llm_num_ctx)
        if getattr(self, "_da_keu_tran", False):
            return
        loi = canh_bao_tran(prompt_tokens, settings.llm_num_ctx,
                            settings.llm_max_tokens)
        if loi:
            self._da_keu_tran = True
            logger.warning(loi)

    async def generate_simple(self, prompt: str, num_predict: int = 100) -> str:
        """Non-streaming generation for simple tasks."""
        response = await self.client.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            think=False,
            # Dùng chung CHUOI_DUNG với đường chính: đây cũng đi qua model ấy nên
            # rò nhãn vai trò được y hệt, chỉ là chưa ai bắt gặp.
            # PHẢI gửi cùng num_ctx với `stream_response`. Thiếu nó thì Ollama
            # dùng cỡ ngữ cảnh mặc định (2048), khác 8192 của đường chính, và
            # NẠP LẠI model mỗi lần đổi qua lại: đo 05-09-2026 mỗi lượt LLM chờ
            # token đầu 3-6 giây thay vì ~100ms, TTFA 53/60 lượt vượt trần.
            # Bộ tóm tắt gọi hàm này sau mỗi lượt nên lượt nào cũng dính.
            # `num_predict` mặc định 100 là cho câu trả lời MỘT DÒNG (quyết định
            # gọi hàm, câu đệm). Ai cần JSON dài phải tự xin thêm - tóm tắt phiên
            # bị cắt cụt ở đúng 100 token và mất tóm tắt mọi cuộc gọi 06-09-2026.
            options={"num_predict": num_predict, "temperature": 0.3, "stop": CHUOI_DUNG,
                     "num_ctx": settings.llm_num_ctx},
        )
        msg = response.get("message", {}) if isinstance(response, dict) else getattr(response, "message", None)
        return self._extract_content(msg)

    async def health_check(self) -> bool:
        try:
            result = await self.client.list()
            # Ollama trả model local không ghi tag dưới dạng ``name:latest`` ở
            # mọi phiên bản client, còn cấu hình có thể ghi ``name`` hoặc
            # ``name:latest``. Chuẩn hoá đúng hai dạng đó rồi so KHỚP CHÍNH XÁC.
            #
            # Trước đây chỉ so phần trước dấu ``:`` bằng ``startswith``. Vì vậy
            # cấu hình ``qwen3.5:9b`` vẫn báo health OK nếu máy chỉ có
            # ``qwen3.5:4b``. Startup nhìn xanh nhưng lượt đầu mới vỡ vì model
            # cần dùng thực ra chưa được tải.
            if self._normalize_model(self.model) not in self._models_from_inventory(result):
                return False
            if getattr(self, "_ho_tro_think", None) is None:
                await self.kiem_nang_luc()
            return True
        except Exception:
            return False
