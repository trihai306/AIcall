import time
import uuid


class CallSession:
    """Manages conversation state for a single call."""

    def __init__(
        self,
        customer_name: str = "Anh/Chị",
        product: str = "vay tín chấp",
        voice_name: str = "default",
        *,
        campaign_id: str = "",
        contact_id: str = "",
        phone: str = "",
        direction: str = "outbound",
        caller_number: str = "",
        scenario: dict | None = None,
        fields: dict | None = None,
    ):
        self.session_id = str(uuid.uuid4())[:8]
        self.customer_name = customer_name
        self.product = product
        self.voice_name = voice_name
        self.history: list[dict] = []
        # Chủ đề bot ĐÃ THẬT SỰ tư vấn trong cuộc này. Mở cổng cho nhóm tình
        # huống chê - xem `filler_situation.loc_theo_ngu_canh`. Chỉ đọc lời BOT:
        # lấy lời khách thì chính câu "lãi cao thế" đang cần phân loại lại tự
        # mở cổng cho mình.
        self.da_tu_van: set[str] = set()
        self.created_at = time.time()
        self.turn_count = 0
        self.latency_log: list[dict] = []

        # --- Cuộc gọi này thuộc về đâu ------------------------------------
        # Báo cáo lọc theo mấy trường này, nên chúng phải đi cùng phiên ngay từ
        # lúc tạo chứ không gắn sau: phiên có thể kết thúc bất cứ lúc nào.
        self.campaign_id = campaign_id
        self.contact_id = contact_id
        self.phone = phone
        self.direction = direction          # outbound | inbound
        self.caller_number = caller_number  # gọi vào: số của khách
        # Các trường tuỳ biến của khách (field1..3), để chèn vào lời chào.
        self.fields: dict = fields or {}

        # Thông tin tra được về CHÍNH khách này từ nguồn dữ liệu ngoài (dư nợ,
        # đơn hàng...). Tra một lần lúc mở phiên rồi gắn vào đây: tra lại mỗi
        # lượt là đọc file Excel giữa đường găng của độ trễ.
        self.ngu_canh_khach = ""
        # Hồ sơ khách dạng BẢNG (tên trường -> giá trị). `ngu_canh_khach` ở trên
        # là bản đã dựng thành văn cho prompt; bản này để `tra_loi_ho_so` đọc
        # thẳng từng trường, khỏi phải nhờ mô hình nhặt số ra khỏi đoạn văn.
        self.ho_so_khach: dict = {}

        # Kịch bản đang chạy. Giữ nguyên cả dict thay vì chỉ id: mỗi lượt đều
        # cần dựng prompt từ nó, tra CSDL mỗi lượt là tự thêm việc vào đường
        # găng của độ trễ.
        self.scenario: dict = scenario or {}
        self.scenario_id = (scenario or {}).get("scenario_id", "")

        # --- Kết quả suy ra trong lúc gọi ---------------------------------
        self.gender = ""            # male | female | unknown, xem gender_detect
        self.gender_do_tin = None   # 0..1; dưới NGUONG_TIN thì vẫn gọi "anh chị"
        self.outcome = ""           # answered | no_answer | busy | voicemail | failed
        self.la_hop_thu_thoai = False
        self.recording_path = ""
        self.recording_size = 0

        # Đếm để quyết định chuyển tiếp sang người thật - xem transfer_service.
        self.so_lan_ngoai_pham_vi = 0
        self.so_lan_rag_trong = 0
        self.khach_doi_gap_nguoi = False
        self.transferred_to = ""
        self.transfer_reason = ""

        # Số thứ tự lượt, do CLIENT cấp và gửi kèm mỗi tin nhắn. Mọi mảnh audio
        # gửi ra đều mang số này để client bỏ được mảnh của lượt đã cũ.
        # Cần vì: khách gửi tin mới trong lúc lượt trước còn đang sinh tiếng thì
        # các mảnh còn lại của lượt cũ vẫn tới nơi và bị phát tiếp - đo được 3
        # mảnh (~8 giây tiếng) tới SAU khi client đã dọn lịch phát.
        self.turn_id = 0

        # Câu khách đang nói dở thì bị chính họ cắt ngang (nói đè lên AI).
        # Sẽ được ghép vào câu kế tiếp - xem danh_dau_bi_cat/ghep_cau_bi_cat.
        self.cau_bi_cat = ""

        # Cờ xin dừng lượt đang chạy. Dùng cờ thay vì cắt cứng task vì cắt cứng
        # giữa lúc STT chưa xong sẽ mất luôn cả câu khách vừa nói - không còn gì
        # để ghép. Pipeline kiểm cờ này ở các điểm an toàn: ngay sau khi đã ghi
        # được câu khách, và giữa các mảnh trả lời.
        self.yeu_cau_huy = False

        # --- Đệm audio cho luồng streaming ---
        # Client đẩy PCM 16kHz ngay trong lúc khách đang nói, thay vì thu xong hết
        # mới gửi một cục. Nhờ vậy khi khách dứt lời thì audio đã nằm sẵn ở server.
        self._audio_buf = bytearray()
        self._audio_t0: float | None = None   # mốc mẩu tiếng đầu, để đo hụt
        # Kết quả đoán trước (phiên âm tạm + ngữ cảnh RAG dựng sẵn trong lúc khách
        # còn đang nói). Chỉ được dùng lại nếu phiên âm cuối cùng khớp.
        self.spec_transcript: str = ""
        self.spec_rag: str = ""
        self.spec_answer: str = ""    # câu trả lời LLM đã soạn sẵn (CHƯA thành tiếng)
        self.spec_bytes: int = 0      # đã đoán ở mốc bao nhiêu byte
        self.spec_running: bool = False
        self.spec_task = None         # tác vụ đoán đang chạy, để huỷ khi khách nói tiếp
        # (số byte audio, phiên âm) của lần đoán gần nhất. Dùng lại được KHI VÀ
        # CHỈ KHI lượt thật có đúng chừng ấy byte - tức bản đoán đã phủ trọn câu,
        # không thiếu chữ nào. Đây là thứ DUY NHẤT cắt được STT khỏi đường găng:
        # `process_turn` vốn luôn phiên âm lại từ đầu, tốn 212-502ms mỗi lượt.
        self.spec_stt: tuple[int, str] | None = None
        # Tình huống đoán được từ phiên âm dở: (số byte đã thấy, id, điểm).
        # `_send_filler` đọc ô này để chọn mẩu mở đầu. Số byte để biết đoán này
        # phủ được bao nhiêu phần câu - đoán trên câu cụt thì dễ trượt.
        self.tinh_huong: tuple[int, str, float] | None = None
        # Đếm số lần mỗi câu đệm đã dùng TRONG CUỘC GỌI NÀY, để chọn câu ít
        # dùng nhất. Thuộc về phiên: khách mới thì không việc gì phải tránh
        # câu đã dùng với khách trước.
        self.dem_filler: dict[str, int] = {}
        # Tần số của tiếng NẰM TRONG đệm. Trình duyệt đẩy 16kHz; đường thoại đẩy
        # 8kHz thô và KHÔNG tự nâng tần - xem `PhoneAudioBridge._read_loop`. Mọi
        # chỗ đọc đệm phải theo số này chứ đừng đoán 16kHz.
        self.audio_rate: int = 16000

    # --- đệm audio ---------------------------------------------------------

    def push_audio(self, chunk: bytes):
        # Ghi mốc mẩu đầu tiên để đo hụt tiếng ở take_audio(). Client thu bằng
        # createScriptProcessor - API chạy trên LUỒNG CHÍNH, nên lúc trang bận
        # (vẽ tin nhắn, giải mã tiếng TTS) trình duyệt bỏ nhịp onaudioprocess và
        # mất nguyên mẩu 128ms. Không đo thì chỉ thấy triệu chứng "mất chữ" mà
        # không biết chữ rơi trước khi tới server hay do nhận dạng sai.
        if not self._audio_buf:
            self._audio_t0 = time.time()
        self._audio_buf.extend(chunk)

    def set_audio(self, data: bytes):
        """THAY nguyên bộ đệm tiếng, không nối thêm.

        Cần cho đường thoại: nó gom tiếng gốc 8kHz của CẢ lượt rồi đặt lại toàn
        bộ mỗi lần đoán trước, thay vì nối thêm từng khối đã nâng tần. Nối khối
        đã nâng để lại điểm gãy ở mỗi mối và làm hỏng phụ âm đầu - đo được "anh
        cần vay" thành "anh tần vay". Xem `_read_loop`.
        """
        if not self._audio_buf:
            self._audio_t0 = time.time()
        self._audio_buf = bytearray(data)

    def audio_len(self) -> int:
        return len(self._audio_buf)

    def peek_audio(self) -> bytes:
        return bytes(self._audio_buf)

    def do_hut_tieng(self) -> dict | None:
        """So thời lượng tiếng NHẬN ĐƯỢC với thời gian khách thật sự nói.

        Hụt nhiều nghĩa là mẩu tiếng rơi trước khi tới server - lúc đó có chỉnh
        tham số nhận dạng cũng vô ích.
        """
        if not self._audio_buf or self._audio_t0 is None:
            return None
        # PCM 16-bit, 1 kênh, tần số tuỳ đường vào (xem `audio_rate`). Chốt cứng
        # 16000 ở đây thì đường thoại 8kHz bị báo hụt gấp đôi so với thật.
        giay_nhan = len(self._audio_buf) / 2 / self.audio_rate
        giay_thuc = time.time() - self._audio_t0
        if giay_thuc <= 0.2:
            return None
        return {
            "giay_nhan": round(giay_nhan, 2),
            "giay_thuc": round(giay_thuc, 2),
            "hut_pct": round(max(0.0, 1 - giay_nhan / giay_thuc) * 100, 1),
        }

    def take_audio(self) -> bytes:
        """Lấy toàn bộ audio đã nhận và dọn đệm cho lượt sau."""
        data = bytes(self._audio_buf)
        self._audio_buf.clear()
        self._audio_t0 = None
        return data

    def clear_speculation(self):
        if self.spec_task is not None and not self.spec_task.done():
            self.spec_task.cancel()
        self.spec_task = None
        self.spec_transcript = ""
        self.spec_rag = ""
        self.spec_answer = ""
        self.spec_bytes = 0
        self.spec_stt = None
        self.tinh_huong = None

    def add_turn(self, role: str, content: str):
        self.history.append({"role": role, "content": content})
        if role == "user":
            self.turn_count += 1
        else:
            # Ghi tại ĐÂY chứ không ở đường thoại: ba đường (gọi ra, gọi vào,
            # chat) đều đi qua add_turn, vá từng chỗ là chắc chắn sót một chỗ.
            from backend.services.filler_situation import chu_de_da_noi
            self.da_tu_van |= chu_de_da_noi(content)

    # --- Khách cắt lời AI --------------------------------------------------
    def danh_dau_bi_cat(self):
        """AI bị khách nói đè lên: bỏ lượt vừa rồi khỏi lịch sử, giữ lại câu
        khách đã nói để ghép với câu sắp nói.

        Vì sao bỏ: câu trả lời đó khách chưa nghe hết (thường mới được vài chữ),
        để lại trong lịch sử thì lượt sau LLM tưởng đã trả lời rồi.
        Vì sao giữ câu khách: người ta cắt lời hầu như luôn vì nói chưa hết ý
        hoặc AI hiểu sai - "cho em hỏi" (AI đáp) "lãi suất bao nhiêu" là MỘT câu
        bị chẻ đôi, trả lời riêng từng nửa thì nửa nào cũng trật.
        """
        # Bỏ câu trả lời dở của AI nếu có
        if self.history and self.history[-1]["role"] == "assistant":
            self.history.pop()
        # Nhấc câu khách vừa nói ra khỏi lịch sử để ghép vào câu kế tiếp
        if self.history and self.history[-1]["role"] == "user":
            self.cau_bi_cat = self.history.pop()["content"]
            self.turn_count = max(0, self.turn_count - 1)
        else:
            self.cau_bi_cat = ""
        self._tinh_lai_da_tu_van()

    def _tinh_lai_da_tu_van(self):
        """Dựng lại `da_tu_van` từ lịch sử còn lại.

        Cần vì lượt bị cắt đã bị nhấc khỏi lịch sử: khách cắt lời khi bot mới
        nói "Dạ lãi suất bên em" thì khách CHƯA NGHE mức lãi nào. Vẫn tính là đã
        tư vấn thì cổng mở sớm, và câu HỎI lãi ngay sau đó bị chấm thành CHÊ.
        """
        from backend.services.filler_situation import chu_de_da_noi
        self.da_tu_van = set()
        for t in self.history:
            if t.get("role") == "assistant":
                self.da_tu_van |= chu_de_da_noi(t.get("content") or "")

    def ghep_cau_bi_cat(self, cau_moi: str) -> str:
        """Nối câu bị cắt với câu vừa nói. Trả về câu đã ghép, và xoá trạng thái."""
        cu = getattr(self, "cau_bi_cat", "")
        self.cau_bi_cat = ""
        if not cu:
            return cau_moi
        cu = cu.strip().rstrip(".,!?")
        # Khách nhắc lại gần nguyên văn thì lấy câu mới, đừng nối thành câu lặp.
        if cau_moi.strip().lower().startswith(cu.lower()[:20]) and len(cu) > 10:
            return cau_moi
        return f"{cu} {cau_moi.strip()}".strip()

    def log_latency(self, metrics: dict):
        metrics["turn"] = self.turn_count
        metrics["timestamp"] = time.time()
        self.latency_log.append(metrics)

    @property
    def duration_seconds(self) -> float:
        return time.time() - self.created_at

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "customer_name": self.customer_name,
            "product": self.product,
            "voice_name": self.voice_name,
            "turn_count": self.turn_count,
            "duration_seconds": round(self.duration_seconds, 1),
            "history": self.history,
            "latency_log": self.latency_log,
            "campaign_id": self.campaign_id,
            "contact_id": self.contact_id,
            "scenario_id": self.scenario_id,
            "phone": self.phone,
            "direction": self.direction,
            "caller_number": self.caller_number,
            "gender": self.gender,
            "outcome": self.outcome,
            "transferred_to": self.transferred_to,
        }


class SessionStore:
    """In-memory session storage."""

    def __init__(self):
        self._sessions: dict[str, CallSession] = {}

    def create(self, **kwargs) -> CallSession:
        session = CallSession(**kwargs)
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> CallSession | None:
        return self._sessions.get(session_id)

    def remove(self, session_id: str):
        self._sessions.pop(session_id, None)

    def list_active(self) -> list[dict]:
        return [s.to_dict() for s in self._sessions.values()]
