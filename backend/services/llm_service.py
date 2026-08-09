import logging
from collections.abc import AsyncGenerator
import httpx
import ollama
from backend.config import settings
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
CORE_RULES = """QUY TẮC BẮT BUỘC:
1. Luôn xưng "em" và gọi khách là "anh/chị"
2. CÂU ĐẦU TIÊN phải TRẢ LỜI THẲNG thứ khách vừa hỏi, rồi mới nói thêm.
   - Khách hỏi "được không" thì câu đầu phải là được hoặc không được.
   - Khách hỏi con số thì câu đầu phải có con số đó.
   Sau đó TỐI ĐA 3 câu, TỐI ĐA 45 từ cả lượt. Đây là cuộc gọi thoại, không phải chat.
3. MỌI CON SỐ (giá, lãi suất, hạn mức, phí, thời hạn) PHẢI lấy đúng từ mục THÔNG TIN
   THAM KHẢO bên dưới. Con số trong phần VÍ DỤ chỉ minh hoạ CÁCH NÓI - TUYỆT ĐỐI
   không dùng lại.
   THÔNG TIN THAM KHẢO CÓ dữ liệu thì PHẢI trả lời bằng dữ liệu đó ngay. Câu
   "em xin phép kiểm tra lại và báo anh/chị" CHỈ dùng khi thật sự KHÔNG tìm thấy
   trong THÔNG TIN THAM KHẢO - đừng nói câu đó rồi lại trả lời được ngay sau.
4. Nếu khách hỏi ngoài phạm vi, nói: "Dạ em sẽ ghi nhận và có chuyên viên liên hệ lại ạ"
5. Nếu khách từ chối, cảm ơn lịch sự và kết thúc
6. KHÔNG dùng markdown, emoji, gạch đầu dòng - chỉ văn nói tự nhiên
7. Viết số bằng CHỮ SỐ đúng như trong THÔNG TIN THAM KHẢO (ví dụ: 500 triệu,
   24 giờ). KHÔNG tự đọc thành chữ - hệ thống đọc hộ rồi.
8. Chỉ nói tiếng Việt, không chèn từ tiếng Anh
9. KHÔNG liệt kê dài. Khách hỏi "cần những giấy tờ gì" thì nói HAI ba thứ chính là
   đủ - qua điện thoại không ai nhớ được danh sách dài.
   CHỈ hỏi lại khi thật sự cần thêm thông tin để tư vấn tiếp. Đừng kết thúc lượt
   nào cũng bằng một câu hỏi cho có.
10. CÂU KHÁCH LÀ BẢN GHI TỰ ĐỘNG TỪ ĐƯỜNG THOẠI, CÓ THỂ SAI CHÍNH TẢ. Hãy đoán ý
   thật từ ngữ cảnh trước khi trả lời. Trả lời theo Ý ĐOÁN ĐƯỢC, đừng nhắc lại
   chữ sai và đừng hỏi lại chỉ vì một chữ lạ.
11. Chỉ khi câu KHÔNG ĐOÁN NỔI ý (quá ngắn, rời rạc, không liên quan chủ đề đang
   trao đổi) thì mới hỏi lại: "Dạ anh/chị nói lại giúp em được không ạ?". ĐỪNG bịa
   một câu trả lời cho câu mình không hiểu.
12. Phần VÍ DỤ bên dưới chỉ để học ĐỘ DÀI và giọng điệu. TUYỆT ĐỐI không chép lại
   nguyên văn câu nào trong đó, trừ khi tình huống của khách đúng y như tình huống
   của ví dụ."""

# Vì sao phải nhắc lại: mô hình 3B quên ràng buộc độ dài khi prompt dài. Đặt sát
# lượt của khách nên nó "nhớ" hơn là luật số 2 nằm tận đầu prompt.
#
# Dòng đầu là TRẢ LỜI THẲNG chứ không phải độ dài: đo 07-08 bằng
# `scripts/cham_chat_luong.py`, lỗi nhiều nhất là "không trả lời thẳng" (9/54),
# gấp đôi mọi lỗi khác. Nhắc độ dài trước thì mô hình dồn sức cắt chữ và càng né
# câu hỏi.
CORE_REMINDER = """NHẮC LẠI TRƯỚC KHI TRẢ LỜI: câu đầu phải TRẢ LỜI THẲNG thứ khách vừa
hỏi. Sau đó tối đa 3 câu, tối đa 45 từ, mở đầu bằng "Dạ", xưng "em"."""

# Dùng khi kịch bản không khai ví dụ nào. Không có ví dụ thì mô hình hay trả lời
# dài gấp đôi - đây là chỗ nó học ĐỘ DÀI, không phải học nội dung.
_FALLBACK_EXAMPLES = [
    # Ví dụ TRẢ LỜI THẲNG phải đứng ĐẦU. Hai ví dụ cũ đều là tình huống NÉ (khách
    # bận, khách hỏi mơ hồ) nên mô hình học đúng cái đó và mang ra dùng cho cả
    # câu hỏi có dữ liệu rõ ràng - đo được 07-08: hỏi "bao lâu giải ngân" mà mở
    # đầu bằng "em xin phép gọi lại lúc khác".
    #
    # CỐ Ý KHÔNG có con số sản phẩm nào ở đây: bộ nhớ dự án ghi lại một lỗi nặng
    # là con số trong ví dụ rò ra thành lãi suất thật báo cho khách.
    {"khach": "Vay mức đó có được không?",
     "tu_van": "Dạ được ạ, mức đó nằm trong hạn mức của bên em. "
               "Anh chuẩn bị giấy tờ tuỳ thân và sao kê lương là được ạ."},
    {"khach": "Tôi bận lắm.",
     "tu_van": "Dạ em xin lỗi đã làm phiền ạ. Em xin phép gọi lại lúc khác ạ."},
    {"khach": "Cái này là gì thế?",
     "tu_van": "Dạ bên em đang có chương trình phù hợp với anh/chị ạ. "
               "Anh/chị cho em xin một phút được không ạ?"},
]


class LLMService:
    """Ollama streaming client for LLM inference."""

    def __init__(self):
        self.model = settings.ollama_model
        # httpx mặc định đóng kết nối nhàn rỗi sau 5 giây. Khách nói cách nhau lâu
        # hơn thế, nên mỗi lượt phải bắt tay TCP lại: đo được TTFT 520ms thay vì
        # 180-250ms. Giữ kết nối 10 phút để không trả cái giá đó mỗi lượt.
        self.client = ollama.AsyncClient(
            host=settings.ollama_base_url,
            limits=httpx.Limits(max_keepalive_connections=4, keepalive_expiry=600.0),
        )

    def build_system_prompt(
        self,
        customer_name: str = "Anh/Chị",
        product: str = "vay tín chấp",
        rag_context: str = "",
        scenario: dict | None = None,
        co_cong_cu: bool = False,
        gioi_tinh: str = "",
        gioi_tinh_do_tin: float | None = None,
    ) -> str:
        """Assemble the system prompt: fixed core rules + this scenario's parts.

        `scenario` is a row from models/scenarios_db (or {} / None). An empty
        scenario falls back to bank_name/agent_name from .env, which reproduces
        the behaviour from before scenarios existed - so every existing caller
        keeps working without passing anything.
        """
        sc = scenario or {}
        org_name = sc.get("org_name") or settings.bank_name
        agent_name = sc.get("agent_name") or settings.agent_name

        parts = [
            f"Bạn là nhân viên tư vấn của {org_name}, tên là {agent_name}, "
            "đang gọi điện thoại cho khách.",
            "",
            CORE_RULES,
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
                "CÁCH DÙNG CÔNG CỤ (ưu tiên hơn quy tắc 3 và 4):\n"
                "- Khách hỏi con số mà THÔNG TIN THAM KHẢO không có -> GỌI HÀM để tra trước.\n"
                "- Khách hỏi về hồ sơ RIÊNG của họ (dư nợ, hợp đồng, ngày đến hạn) "
                "-> luôn GỌI HÀM tra_ho_so_khach, đừng hỏi xin số điện thoại "
                "(hệ thống đã biết số của khách đang gọi).\n"
                "- CHỈ khi gọi hàm xong mà vẫn không có dữ liệu thì mới nói "
                "\"em xin phép kiểm tra lại và báo anh/chị ngay ạ\".\n"
                "- Câu chào hỏi, từ chối, hỏi thăm thì KHÔNG gọi hàm."
            )

        parts.append(CORE_REMINDER)
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
        """Extract text content from an Ollama message (handles both dict and object)."""
        if msg is None:
            return ""
        if isinstance(msg, dict):
            return msg.get("content", "") or ""
        return getattr(msg, "content", "") or ""

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

    async def stream_response(
        self,
        messages: list[dict],
        system_prompt: str,
        tools: list[dict] | None = None,
        on_tool_calls=None,
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
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        kw = {"tools": tools} if tools else {}

        with Timer("LLM-TTFT", logger):
            first_token = True
            response = await self.client.chat(
                model=self.model,
                messages=full_messages,
                stream=True,
                think=False,
                options={
                    "num_predict": settings.llm_max_tokens,
                    "temperature": settings.llm_temperature,
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
                    if first_token:
                        first_token = False
                        logger.info("LLM first token received")
                    yield token

    async def generate_simple(self, prompt: str) -> str:
        """Non-streaming generation for simple tasks."""
        response = await self.client.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            think=False,
            # Dùng chung CHUOI_DUNG với đường chính: đây cũng đi qua model ấy nên
            # rò nhãn vai trò được y hệt, chỉ là chưa ai bắt gặp.
            options={"num_predict": 100, "temperature": 0.3, "stop": CHUOI_DUNG},
        )
        msg = response.get("message", {}) if isinstance(response, dict) else getattr(response, "message", None)
        return self._extract_content(msg)

    async def health_check(self) -> bool:
        try:
            result = await self.client.list()
            models = result.get("models", []) if isinstance(result, dict) else getattr(result, "models", [])
            prefix = self.model.split(":")[0]
            for m in models:
                name = m.get("model", "") if isinstance(m, dict) else getattr(m, "model", "")
                if name.startswith(prefix):
                    return True
            return False
        except Exception:
            return False
