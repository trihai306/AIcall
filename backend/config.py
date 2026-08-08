from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # STT - PhoWhisper (VinAI) via faster-whisper server
    whisper_server_url: str = "http://localhost:8178"
    whisper_model: str = "vinai/PhoWhisper-small"
    # Vùng miền của khách: "" (không mồi) | bac | trung | nam.
    # Chỉ nghiêng bộ giải mã về chính tả chuẩn của các cặp âm vùng đó không phân
    # biệt - xem MOI_VUNG_MIEN trong services/stt_service.py. ĐO TRƯỚC KHI BẬT:
    # mồi lợi hại lẫn lộn, chạy scripts/do_vung_mien.py trên mẫu thu thật.
    stt_vung_mien: str = ""

    # Ollama LLM - Vistral-7B-Chat (Vietnamese)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "vistral-7b-chat"
    llm_num_ctx: int = 2048

    # F5-TTS
    f5tts_ckpt_path: str = "./models/tts/F5-TTS-Vietnamese-ViVoice/model_last.pt"
    f5tts_vocab_path: str = "./models/tts/F5-TTS-Vietnamese-ViVoice/vocab.txt"
    f5tts_ref_audio: str = "./models/tts/ref_voices/default.wav"
    f5tts_ref_text: str = "xin chào, tôi là nhân viên tư vấn ngân hàng"
    f5tts_nfe_step: int = 16
    # Chunk đầu vốn để đánh đổi chất lượng lấy TTFA. Đo trên 6 câu mở đầu ngắn:
    # nfe 8 -> WER 25%, nfe 12 -> 17%, nfe 16 -> 7%. Ở nfe thấp chữ "Dạ" (mở đầu
    # gần như mọi câu) bị đọc thành "Giả"/"Sạc" - hỏng đúng từ khách nghe đầu tiên.
    # Chốt bằng nfe_step: ưu tiên đọc đúng, chấp nhận chunk đầu chậm hơn ~1.6s.
    # Để bằng nhau thì cờ fast=True thành vô hiệu - đó là chủ ý, không phải quên.
    f5tts_nfe_step_first: int = 16
    f5tts_speed: float = 1.0
    # Hạt giống cho nhiễu ngẫu nhiên của F5. KHÔNG chỗ nào trong repo lẫn trong
    # `utils_infer.py` đặt seed, nên mỗi lần sinh là một lần bốc nhiễu mới: cùng
    # một câu mỗi lần đọc một kiểu. Khách phản ánh đúng điều này 2026-08-08
    # ("Cùng 1 câu, mỗi lần gen ra 1 kiểu").
    # Đặt số cố định -> cùng chữ + cùng giọng + cùng tốc luôn cho ra ĐÚNG MỘT
    # file. Nghĩa là bản nghe thử chính là bản cuộc gọi thật sẽ dùng, và lỗi nào
    # tái hiện được thì mới sửa được.
    # Đánh đổi: seed cố định KHÔNG làm giọng hay hơn, nó chỉ khoá lại một lần
    # bốc. Câu nào rơi vào lần bốc xấu thì xấu mãi - đổi `f5tts_seed` sang số
    # khác là bốc lại. Để trống trong .env thì quay về ngẫu nhiên như cũ.
    f5tts_seed: int | None = 0
    # torch.compile cho DiT. Cần Triton; máy Windows ĐÃ CÓ (gói `triton`), nên
    # bật được — trước đây tắt vì tưởng thiếu.
    #
    # ĐÂY LÀ CÁCH TĂNG TỐC DUY NHẤT KHÔNG ĐÁNH ĐỔI CHẤT LƯỢNG: cùng trọng số,
    # cùng phép toán, chỉ hợp nhất kernel. Đo trên 4 câu thật
    # (scripts/cham_chat_luong_compile.py):
    #     không compile  737ms  CER 0.004
    #     có compile     560ms  CER 0.004     -> nhanh hơn 176ms (24%)
    # CER trùng khít từng câu (0.018, 0, 0, 0 ở cả hai bên), không phải xấp xỉ.
    # Đo riêng lần khác cho 573 -> 393ms (31%).
    #
    # Giá phải trả: khởi động lâu thêm ~40 giây để biên dịch, MỘT LẦN duy nhất.
    # Với dịch vụ chạy dài thì đổi được; với script chạy một phát rồi thoát thì
    # không đáng - nên để bật/tắt bằng F5TTS_COMPILE trong .env.
    f5tts_compile: bool = False
    # Chế độ cho torch.compile. "" = mặc định. "reduce-overhead" bật CUDA graphs -
    # gom cả chuỗi kernel thành một lần phóng, đúng thuốc cho F5 vì đo được GPU
    # chạy 94% xung mà chỉ ăn 46% điện, tức phần lớn thời gian là chờ giữa các
    # kernel nhỏ chứ không phải tính toán.
    # ĐÁNH ĐỔI: CUDA graphs cần shape CỐ ĐỊNH, mà câu dài ngắn khác nhau -> có
    # thể phải bắt lại đồ thị liên tục và thành CHẬM HƠN. Phải đo, đừng tin.
    f5tts_compile_mode: str = ""

    # Database - call history (SQLite)
    db_path: str = "./data/app.db"

    # Ghi âm cuộc gọi (Điều 6, mục Báo cáo)
    recordings_path: str = "./data/recordings"
    # Số ngày giữ bản ghi. 0 = giữ mãi. Chiến dịch vài nghìn số mỗi tháng thì
    # đây là thứ quyết định ổ đĩa đầy sau bao lâu.
    recordings_giu_ngay: int = 90

    # RAG
    chroma_db_path: str = "./data/chroma_db"
    embedding_model: str = "BAAI/bge-m3"
    embedding_device: str = "cpu"  # keep VRAM free for STT/LLM/TTS

    # VAD
    vad_threshold: float = 0.5
    vad_min_silence_ms: int = 220

    # Pipeline
    tts_chunk_words: int = 8
    tts_first_chunk_words: int = 4
    llm_max_tokens: int = 80
    llm_temperature: float = 0.7

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"

    # Banking
    bank_name: str = "Ngân hàng ABC"
    agent_name: str = "Lan"

    # --- Đường điện thoại ---------------------------------------------------
    # HAI CHIỀU CÓ TẦN SỐ RIÊNG - đừng gộp lại làm một.
    #
    # Chiều xuống (tiếng AI -> điện thoại): đo được máy trộn âm ở 48kHz
    # (AudioFlinger "Sample rate: 48000 Hz"), KHÔNG có trần 8k như từng tưởng.
    # Đã chạy thật ở 24000: AudioTrack nhận, 0 underrun trên 5,6s tiếng liên tục.
    # Chỉ hạ về 8000 khi tiếng phải chui qua CUỘC GỌI GSM THẬT: AMR-NB lấy mẫu
    # 8kHz nên gửi cao hơn cũng bị hạ, chỉ tốn thêm một lần đổi tần và chút méo.
    #   nghe thẳng trên máy / app VoIP  -> 24000
    #   cuộc gọi GSM (AMR-NB)           -> 8000
    #   VoLTE (AMR-WB, cần SIM)         -> 16000
    phone_rate_xuong: int = 24000
    # Chiều lên (micro -> STT): giữ 8000. Tiếng cuộc gọi thật vốn chỉ có nội dung
    # tới 4kHz, thu 24k rồi lại hạ xuống 16k cho STT chỉ tốn băng thông và CPU.
    phone_rate_len: int = 8000

    # Đệm mồi gửi trước cho máy, mili giây. 60ms là quá mỏng: đo được AudioTrack
    # đói dữ liệu 20913 lần/giây khi phát (lúc rảnh 0), nghe thành tiếng "dè".
    # Đổi lại, đệm dày làm cắt lời chậm đi đúng bằng chừng đó.
    phone_dem_mo_ms: int = 250

    # Máy phone farm đang dùng. Cần để dựng lại `adb forward` khi ổ cắm chết
    # giữa cuộc gọi - máy chủ adb trên Windows tự khởi động lại thì forward mất
    # theo, và trước đây luồng gửi chết luôn nên nửa sau cuộc gọi câm tiếng.
    phone_serial: str = "21f10e44220c7ece"
    # Khe SIM dùng để gọi ra, đánh số từ 0. Để -1 nghĩa là không chỉ định, để máy
    # tự chọn. PHẢI chỉ định trên máy hai khe: với số chưa gọi bao giờ, Android
    # bật hộp "chọn SIM" và hộp đó CHỜ NGƯỜI BẤM - cuộc gọi đứng im, nhìn từ
    # ngoài giống hệt "không ai bắt máy".
    phone_sim_slot: int = -1
    # Khách im bao lâu thì coi là dứt lời (ms). Xem chú thích dài ở
    # `phone_call_service.SILENCE_END_MS` để biết vì sao con số này khó chọn.
    # Để ở đây thay vì hằng số cứng: nó phụ thuộc CÁCH NÓI của từng nhóm khách,
    # nên phải chỉnh được ngoài hiện trường mà không phải sửa code.
    # Đo lại bằng scripts/do_khoang_nghi_khach.py trên bản ghi cuộc gọi thật.
    phone_silence_end_ms: int = 750

    # Đường đưa tiếng AI vào chiều lên của cuộc gọi:
    #   "codec" - trộn trong codec ở AIF1TX1 Input 2. Chạy được nhưng nghe "dè".
    #   "usb"   - đường thiết bị ngoài Samsung dựng sẵn cho tai nghe USB, kèm cờ
    #             ERAP báo nguồn không phải micro cầm tay.
    phone_duong_tiem: str = "codec"

    # Lọc tiếng khách trước khi đưa vào STT: cắt ngoài dải tiếng nói, hạ nhiễu
    # nền, chuẩn mức.
    #
    # MẶC ĐỊNH TẮT vì đo được là KHÔNG GIÚP. Chấm bằng CER trên câu có bản chép
    # đúng, trộn nhiễu hồng (scripts/do_loc_nhieu.py):
    #     SNR 20dB  0.050 -> 0.045      SNR 12dB  0.048 -> 0.059
    #     SNR  6dB  0.059 -> 0.096      SNR  0dB  0.301 -> 0.323
    # PhoWhisper vốn đã chịu được mức nhiễu này; lọc thêm chỉ lấy đi thông tin.
    # Giữ lại để bật khi gặp kênh nhiễu kiểu khác - nhưng ĐO LẠI trước khi tin.
    phone_loc_tieng_khach: bool = False

    # Tiếng TTS nghe ổn qua tai nghe nhưng sang điện thoại thì mỏng và đục. Đo
    # được nguyên nhân: giọng nặng dải trầm - năng lượng 1-3.4kHz (chỗ chứa phụ
    # âm, quyết định nghe rõ) chỉ bằng 0.14-0.25 lần dải 100Hz-1kHz. Loa điện
    # thoại không phát được dải trầm nên tới tai khách chỉ còn phần vốn đã yếu.
    # Bộ xử lý này lọc bỏ dải trầm vô ích, nâng dải độ rõ, và chuẩn mức.
    # Đo sau khi bật: độ nghiêng phổ 0.14-0.25 -> 0.33-0.59.
    #
    # CHỈ ÁP DỤNG KHI ĐƯỜNG XUỐNG HẸP BĂNG (phone_rate_xuong <= 16000). Ở 24kHz
    # tiếng ra thẳng loa máy, không có loa thoại hẹp băng nào để bù, nên bộ này
    # chỉ còn tác dụng phụ: cắt trầm 37.5% -> 18.3% và nâng dải 2.2kHz gấp đôi,
    # tức là tự tay tạo ra đúng tiếng "dè" mà nó sinh ra để chữa.
    phone_toi_uu_am: bool = True
    # Hạ nhiễu nền kiểu Wiener trước khi đưa vào bộ mã hoá của mạng.
    # ĐÃ THỬ VÀ KHÔNG ĂN THUA - để mặc định TẮT.
    # Ý tưởng: AMR-NB là vocoder, nó dựng lại giọng theo mô hình tiếng người;
    # nhiễu của mô hình khuếch tán làm nó dựng sai. Nhưng đo thật thì HNR sau
    # khi qua điện thoại chỉ đổi 5.1 -> 5.0 dB, tức không cải thiện.
    # Mốc để so: bản thu NGƯỜI THẬT qua cùng đường đạt 7.2 dB. Khoảng cách 2.1 dB
    # đó nằm ở chính mô hình sinh tiếng, hậu xử lý không bù được.
    phone_lam_sach: bool = False
    phone_muc_dbfs: float = -19.0     # chuẩn thoại; to hơn thì codec méo ở đỉnh
    phone_dinh_toi_da: float = 0.89   # chừa ~1dB dự trữ
    phone_loc_tram_hz: float = 200.0  # dưới mức này loa điện thoại không phát được
    phone_nang_do_ro_db: float = 6.0  # nâng quanh 2.2kHz

    # Tăng tính tuần hoàn trước khi vào bộ mã của mạng - chữa tiếng kim loại.
    # KHÁC HẲN `phone_lam_sach` ở trên (thứ đã thử và thất bại): cái kia hạ nhiễu
    # theo vạch phổ, cái này làm tín hiệu LẶP LẠI đúng chu kỳ cao độ - thứ bộ dự
    # đoán chu kỳ (LTP) của AMR bám vào để dựng lại giọng.
    #
    # Đo trên tiếng F5 THẬT qua AMR-NB 12.2k (scripts/thu_tts_that.py):
    #   chưa xử lý  6.25 dB  ->  có xử lý  7.35 dB   (+1.10)
    #   mốc người thật 7.24 dB, tức bản có xử lý đã VƯỢT giọng người.
    # Chi phí 24.7ms cho 3.78s tiếng (0.65% thời gian thực).
    #
    # MẶC ĐỊNH TẮT cho tới khi nghe kiểm trên cuộc gọi thật. Lý do thận trọng:
    # đo được méo phổ 7.8-8.6 dB, tức tín hiệu bị đổi khá nhiều. Phần lớn là do
    # bỏ nền nhiễu giữa các hài (đúng chủ đích), nhưng quá tay thì sinh tiếng
    # rỗng/máy móc mà con số HNR không bắt được.
    # CHỈ CÓ TÁC DỤNG KHI `phone_rate_xuong <= 16000` - băng rộng thì không đi
    # qua bộ mã nào để mà chiều nó.
    phone_tang_tuan_hoan: bool = False
    phone_luoc_alpha: float = 0.4     # lọc lược; cao hơn = tuần hoàn hơn, dễ rỗng
    phone_du_alpha: float = 0.7       # trên phần dư LP; giữ nguyên âm sắc

    @property
    def project_dir(self) -> Path:
        return Path(__file__).parent.parent

    @property
    def db_file(self) -> Path:
        """Absolute path to the call-history SQLite file (uvicorn may run from anywhere)."""
        p = Path(self.db_path)
        return p if p.is_absolute() else self.project_dir / p

    @property
    def recordings_dir(self) -> Path:
        p = Path(self.recordings_path)
        return p if p.is_absolute() else self.project_dir / p

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
