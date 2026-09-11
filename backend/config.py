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
    #
    # 05-09-2026: người dùng cho biết giọng BẮC, đã đo bằng `scripts/do_moi_bac.py`
    # (14 câu, chạy xen kẽ cả hai chiều qua đúng `STTService.transcribe`) và
    # vẫn ĐỂ TRỐNG vì mồi "bac" làm TỆ ĐI:
    #     tiếng sạch 16kHz   không mồi 0,0036  mồi bac 0,0036   (0/14 câu đổi)
    #     qua kênh 8kHz      không mồi 0,0062  mồi bac 0,0171   (2 câu tệ đi,
    #                        0 câu tốt lên: "tài khoản" -> "tái khoản")
    # Lưu ý phạm vi phép đo: câu khách do F5 đọc ĐÚNG chính tả, nên nó chỉ đo
    # được phần HẠI. Phần LỢI của mồi vùng miền chỉ hiện ra khi người nói thật
    # sự lẫn l/n, tr/ch - muốn biết thì phải có mẫu thu của chính người dùng
    # (`data/test_vung_mien/bac/`, hiện CHƯA CÓ) rồi chạy `do_vung_mien.py`.
    stt_vung_mien: str = ""

    # Ollama LLM - Vistral-7B-Chat (Vietnamese)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "vistral-7b-chat"
    # Đo 2026-09-02 (qwen2.5:7b, prompt_eval_count thật): lời dặn + tri thức
    # đã ăn 1414 token. Ở 2048 thì hội thoại chỉ còn 484 token ~ 6 lượt, rồi
    # Ollama cắt bỏ phần đầu KHÔNG BÁO GÌ - đó là lỗi "nói chuyện một lúc là
    # bot quên". 8192 cho ~88 lượt, tốn thêm ~340MB VRAM (bộ nhớ đệm khoá-giá
    # trị của qwen2.5-7B ~56KB/token). Xem `services/cua_so_nho`.
    llm_num_ctx: int = 8192

    # F5-TTS
    f5tts_ckpt_path: str = "./models/tts/F5-TTS-Vietnamese-ViVoice/model_last.pt"
    f5tts_vocab_path: str = "./models/tts/F5-TTS-Vietnamese-ViVoice/vocab.txt"
    f5tts_ref_audio: str = "./models/tts/ref_voices/default.wav"
    f5tts_ref_text: str = "xin chào, tôi là nhân viên tư vấn ngân hàng"
    f5tts_nfe_step: int = 16
    # Chunk đầu đánh đổi chất lượng lấy TTFA.
    #
    # ĐỔI 16 -> 12 ngày 14-08-2026. Lần chốt TRƯỚC (giữ lại để đừng ai lật đi
    # lật lại): đo 6 câu mở đầu ngắn, nfe 8 -> WER 25%, nfe 12 -> 17%,
    # nfe 16 -> 7%; ở nfe thấp chữ "Dạ" bị đọc thành "Giả"/"Sạc" - hỏng đúng từ
    # khách nghe đầu tiên. Nên chốt 16 và chấp nhận chunk đầu chậm.
    #
    # Quyết định đó ĐÚNG ở thời điểm của nó, nhưng điều kiện đã đổi hẳn: tốc đọc
    # về 0,98, hệ số thoại về 1,00, và "Dạ" nay được tách bằng dấu phẩy. Đo lại
    # trên 16 câu mở đầu thật (`scripts/nfe_manh_dau_ky.py`), cho STT nghe lại:
    #     nfe 16   chữ ĐẦU đúng 13/16   từ sai 2,2%   451ms
    #     nfe 12   chữ ĐẦU đúng 14/16   từ sai 1,6%   244ms
    # nfe 12 tốt HƠN ở cả hai thước đo mà nhanh hơn 207ms. Chỗ "Dạ -> Giả" nay
    # xảy ra ở CẢ HAI mức gần như nhau, nên nó không còn phân biệt được hai mức.
    #
    # Đây là chunk ĐẦU của mỗi lượt, phần khách nghe ngay sau câu đệm - nên
    # 200ms ở đây rơi thẳng vào TTFA. Đo trên cuộc gọi thật: TTFA 1991-2829ms,
    # trong đó "TTS mảnh đầu" chiếm 601-799ms, là khoản lớn nhất.
    #
    # Ai đổi lại thì đo bằng chính script trên, và đo CHỮ ĐẦU chứ không chỉ WER
    # cả câu - hỏng ở đây là hỏng từ khách nghe đầu tiên.
    f5tts_nfe_step_first: int = 12
    f5tts_speed: float = 1.0
    # Hai núm chất lượng của F5. Trước 16-08-2026 KHÔNG chỉnh được: đường một
    # mảnh gọi `infer_batch_process` mà không truyền (ăn mặc định thư viện),
    # còn đường gộp lô ghi cứng 2.0 / -1.
    #
    # Người dùng: "âm sắc như máy, không ra chất người". Đo được chữ ký của nó -
    # đầu ra KHÔNG méo mà ngược lại, quá đều và quá sạch so với 5 clip gốc của
    # chính người đó:
    #     người thật:  phẳng phổ 0.0155 | F0 dao động 16.5% | jitter 2.15% | HNR 5.87dB
    #     nfe16 cũ  :  phẳng phổ 0.0197 | F0 dao động 13.3% | jitter 1.99% | HNR 6.95dB
    #
    # Quét 16 cấu hình, thước đo = lệch trung bình so với người thật trên 4 đặc
    # trưng đó, kèm CER cho STT nghe lại (6 câu/cấu hình):
    #     nfe48 cfg2.0 sway 0.0   lệch  8.3%   CER 1.44%   1084ms/mảnh
    #     nfe32 cfg3.0 sway-1.0   lệch 10.0%   CER 1.74%    725ms
    #     nfe32 cfg2.0 sway-1.0   lệch 12.4%   CER 2.32%    728ms
    #     nfe16 cfg2.0 sway-1.0   lệch 18.0%               370ms   <- cũ
    # Cấu hình gần người thật nhất CŨNG là cấu hình đọc rõ nhất - hai thước đo
    # độc lập cùng chỉ một hướng.
    #
    # HAI NÚM NÀY KHÔNG ĐỘC LẬP, đừng vặn lẻ: sway 0.0 ghép với cfg 3.0 đo ra
    # lệch 88% và HNR tụt còn 1.56dB. Đổi thì quét lưới lại.
    #
    # Checkpoint KHÔNG ảnh hưởng: `finetuned/giong_nam` 18.0% vs gốc ViVoice
    # 16.5% ở cùng cấu hình. Đừng đi đổi checkpoint để chữa âm sắc.
    #
    # Mặc định giữ ĐÚNG hành vi cũ (2.0 / -1.0) để máy nào chưa sửa .env thì
    # không âm thầm đổi giọng. Khoá bằng `tests/test_cfg_va_sway.py`.
    f5tts_cfg_strength: float = 2.0
    f5tts_sway_sampling_coef: float = -1.0
    # Gộp các mảnh đang xếp hàng thành MỘT phát ngôn thay vì sinh từng mảnh.
    #
    # F5 kéo dài âm tiết cuối mỗi mảnh; ở giữa câu thì nghe như "ngân dài". Gộp
    # lại thì chỗ nối biến mất. Đo trên 12 lượt thật: chữ ngân 447 -> 332ms
    # (-26%), đổi lại tổng quãng nghỉ 629 -> 316ms (-50%).
    #
    # Bên A đã nghe hai bộ 100 câu (bản thường và bản gộp) và chọn bản GỘP
    # ngày 16-08-2026. Chi tiết và các hướng ĐÃ LOẠI: xem `text_chunker.py`
    # phần `TRAN_AM_TIET_GOP`.
    #
    # Chỉ áp dụng từ mảnh THỨ HAI trở đi - mảnh đầu nằm trên đường găng TTFA.
    f5tts_gop_manh: bool = True
    # Kho TIẾNG SẴN (services/tieng_san.py): câu trả lời chữ cố định (bảng
    # hỏi-đáp đọc nguyên văn, lượt thường gặp) dựng tiếng một lần ra đĩa rồi
    # phát lại, không gọi F5 lúc khách chờ và không còn chỗ nối giữa mảnh.
    # Dựng cả bảng hỏi-đáp lúc khởi động; lượt thường gặp dựng NỀN sau lần
    # nói đầu tiên (chữ phụ thuộc tên ngân hàng/nhân viên/sản phẩm của kịch bản).
    tieng_san_bat: bool = True
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
    #
    # ĐÃ ĐO 04-09-2026 (scripts/do_gop_cfg.py): "reduce-overhead" CHẠY ĐƯỢC và
    # ăn thêm 15% trên nền gộp CFG (290 -> 247ms/câu, câu ngắn 184 -> 140ms).
    # Lần thử 05-08 chết CppCompileError vì máy Win thiếu cl.exe trong PATH,
    # không phải vì CUDA graphs không hợp - load() giờ tự nạp vcvars64.bat.
    # Mỗi ĐỘ DÀI mới gặp lần đầu tốn ~150ms ghi graph, sau đó miễn phí; hâm
    # hình dạng ở startup đã che phần lớn. Bật bằng F5TTS_COMPILE_MODE trong .env.
    f5tts_compile_mode: str = ""
    # Gộp hai lượt CFG (cond + uncond) của mỗi bước khuếch tán thành MỘT forward
    # batch=2, như F5 upstream >= 1.1. Đo: 340 -> 290ms/câu, chất lượng không
    # đổi (cùng seed, tương quan 0,98-0,9999). Chi tiết ở services/f5_gop_cfg.py.
    f5tts_gop_cfg: bool = True
    # >0: chỉ dẫn dắt (CFG) ở N bước đầu, bỏ ở các bước sau. 12/16 bước -34%,
    # 8/16 bước -41% nhưng TIẾNG KHÁC HẲN (tương quan 0,44-0,98) - chưa ai
    # nghe, để 0 cho tới khi tai người duyệt.
    f5tts_cfg_buoc: int = 0

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

    # Nạp TRỌN tài liệu sản phẩm + FAQ thay cho hai mảnh RAG.
    #
    # Đo 09-09-2026 trên 60 câu hỏi thật của khách, qwen2.5:7b:
    #     mảnh RAG top_k=2 (cũ) .... 1005 ký tự, TTFT trung vị 100ms
    #     trọn tài liệu + FAQ ...... 2920 ký tự, TTFT trung vị  28ms
    # Gần gấp ba ký tự mà NHANH HƠN: mảnh RAG đổi mỗi lượt nên phá cache tiền tố
    # của llama.cpp, còn tài liệu thì đứng yên suốt cuộc gọi. Đo riêng bằng
    # `prompt_eval_duration`, xen kẽ ba vòng: 1562 token đổi mỗi lượt tốn 92ms,
    # 2896 token đứng yên tốn 17ms.
    #
    # Bỏ luôn được lượt mã hoá bge-m3 trên đường găng.
    #
    # KHÔNG bớt bịa - đó là việc của lưới thuộc tính và của việc có đủ tài liệu.
    # Đây thuần tuý là thay đổi về ĐỘ TRỄ.
    #
    # Tắt (False) thì rơi về mảnh RAG như cũ. Lượt chưa biết sản phẩm cũng tự
    # rơi về RAG, không cần tắt cờ.
    ngu_canh_tron_tai_lieu: bool = True

    # Lưới thuộc tính bắt được thì SỬA CÂU, không chỉ ghi nhật ký.
    #
    # Thang xử lý ở `thuoc_tinh.sua_theo_tai_lieu`: thay số bằng giá trị trong
    # tài liệu khi tài liệu có đúng một giá trị; không thì bỏ mệnh đề chứa số
    # sai và giữ phần còn lại; bỏ hết mới dùng `CAU_KIEM_TRA_LAI`. KHÔNG bao giờ
    # im lặng, và câu mẫu chỉ còn ở phần rất nhỏ - tránh đúng cái "trả lời 1
    # kiểu" mà lưới số cũ đã gây ra.
    #
    # BẬT MẶC ĐỊNH dù chưa có tỉ lệ đánh dấu nhầm trên cuộc gọi thật, vì hai
    # chiều sai KHÔNG cân nhau: đánh dấu nhầm thì mất một mệnh đề đúng, còn bỏ
    # sót thì khách nghe một con số bịa trong cuộc bán sản phẩm tài chính. Và
    # bản sửa không tự nghĩ ra số nào - nó chỉ chép từ tài liệu hoặc bỏ đi.
    #
    # Tắt: đặt False trong .env. Lúc đó lưới quay về chỉ ghi nhật ký.
    thuoc_tinh_sua_cau: bool = True

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
    #
    # CHỈ DÙNG ĐỂ GIEO MẦM. Nguồn thật của tên tổ chức / nhân viên là KỊCH BẢN
    # trong CSDL (`scenarios.org_name` / `agent_name`); mọi đường chạy đọc qua
    # `scenarios_db.ten_to_chuc` / `ten_nhan_vien`. Hai giá trị dưới đây chỉ được
    # dùng ở hai chỗ:
    #   1. `core/startup.ensure_default` - tạo kịch bản đầu tiên khi bảng còn trống
    #   2. lưới cuối trong hai hàm trên, cho phiên chưa kịp gắn kịch bản
    #
    # Nên ĐỔI TÊN Ở TRANG KỊCH BẢN, đừng sửa `.env` rồi chờ nó ăn: kịch bản đè
    # lên `.env`, và `ensure_default` chỉ chạy một lần lúc CSDL trống nên sửa
    # `.env` sau đó không đồng bộ ngược lại. Tên còn nằm cả trong `opening_line`
    # của kịch bản dưới dạng chữ ghi thẳng trong câu - phải sửa cả trường đó.
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

    # Đệm AudioTrack CHIỀU XUỐNG trên máy Android (`BridgeService.demXuongMs`),
    # mili giây. None = không truyền gì, app giữ mặc định 500 của nó.
    #
    # Đo 07-09-2026 trên hai cuộc gọi thật giống hệt nhau, chỉ đổi mỗi số này
    # (`scripts/do_tre_vong.py`, đo bằng chirp vọng về):
    #
    #     đệm 500ms -> trễ vòng 962ms (n=11, ±11)
    #     đệm 200ms -> trễ vòng 817ms (n=12, ±16)
    #
    # tức hạ xuống 200 rút được 145ms ± 19ms trên đường thật. Dưới 200 thì vô
    # ích: `bufferSizeInBytes = max(minTrk, demXuongBytes)` kẹp ở sàn hệ thống,
    # đo trong máy với 100 và 50 không cắt thêm gì.
    #
    # CÁI GIÁ chưa đo xong: backend bắn `phone_dem_mo_ms` (250ms) tức thì vào
    # buffer này, nhỏ hơn chừng đó thì `WRITE_BLOCKING` chặn luồng vbridge.
    phone_dem_xuong_ms: int | None = None

    # Khách phải nói LIÊN TỤC bấy nhiêu mili giây thì mới coi là cắt lời.
    #
    # Luật cũ dừng AI sau 80ms tiếng (`VAD_ON_FRAMES=4`), nên tiếng ho, tiếng
    # "dạ" khách đế theo khi đang nghe, và tiếng AI vọng ngược vào micro đều
    # cắt được lời AI. 700ms dài hơn một tiếng đế (200-300ms) và ngắn hơn một
    # câu hỏi thật.
    #
    # Cái giá: khách nói thật vẫn bị AI nói đè trong chừng ấy thời gian. Hạ số
    # này xuống thì AI nhạy hơn nhưng dễ bị cắt oan trở lại.
    phone_cat_loi_min_ms: int = 700

    # Ngưỡng RMS coi là khách BẮT ĐẦU nói. Đây là SÀN: ngưỡng thật là
    # `max(sàn này, nền_kênh × VAD_HE_SO_ON)`, xem `phone_call_service.nguong_on`.
    #
    # 700 -> 500 (07-09-2026). Sàn 700 làm máy ĐIẾC với khách nói nhỏ: cuộc
    # 08c0d3e0 khách hỏi "lãi suất bao nhiêu" ở giây 25,8 mà không mở được lượt,
    # phải hỏi lại lần hai ở giây 30,3 mới được nghe. Người dùng báo "nói BOT
    # không nghe thấy".
    #
    # Vì sao nhánh thích nghi không cứu được: nền cầu tiếng điện thoại rất sạch -
    # trung vị 8, p90 20, MAX 30 trên 73 cuộc gọi thật - nên `nền × 3` chưa bao
    # giờ vượt sàn, ngưỡng đứng nguyên ở 87 lần mức nền. Chú thích cũ nói tới nền
    # ~1235 là đo trên MICRO MÁY TÍNH, không phải đường này.
    #
    # Chọn số bằng cách đo 454 lời khách thật trích từ 73 bản ghi
    # (`scripts/do_nguong_bat_vad.py`):
    #     700 -> mở được 417/454 (91,9%)      400 -> 438 (96,5%)
    #     600 -> 425 (93,6%)                  300 -> 445 (98,0%)
    #     500 -> 434 (95,6%)
    # Lấy 500 vì đó là chỗ gãy: 700->500 cứu 17 lời, 500->400 chỉ cứu thêm 4 nữa
    # mà số lượt mở thêm tăng gần gấp đôi (15 -> 24 trên 73 cuộc).
    #
    # KHÔNG được hạ xuống dải 400-500: đó là dải tiếng lạo xạo của `decf104f`,
    # xem chú thích `phone_vad_rms_off` ngay dưới. Đã kiểm riêng cuộc đó và ba
    # cuộc có TV (64b6f2ac, 022eb3e5, 1c1c3b16): số lượt mở y hệt nhau ở 500/600/
    # 700, vì lạo xạo không đủ 4 khung LIÊN TIẾP trên 500 (`VAD_ON_FRAMES`).
    #
    # Bằng nhau với `phone_vad_rms_off` trên kênh sạch là CỐ Ý, không phải quên
    # chừa trễ: bật cần 4 khung (80ms), tắt cần 50 khung (1000ms), nên hai chiều
    # đã lệch nhau 12 lần về thời gian - không có chuyện lượt chớp tắt.
    phone_vad_rms_on: float = 500.0

    # Ngưỡng RMS coi là khách ĐÃ NGỪNG tiếng. Từ đây `silence_ms` mới bắt đầu
    # đếm tới `phone_silence_end_ms`.
    #
    # 400 là số cũ và nó KẸT trên kênh thật: cuộc gọi `decf104f` (06-09-2026) có
    # tiếng lạo xạo mức 400-500 rải rác, nên suốt 18,4 giây kênh khách không có
    # lấy một khoảng im 1000ms nào (dài nhất 920ms) và lượt chỉ đóng khi chạm
    # trần MAX_TURN_MS - khách nói xong ngồi chờ 15 giây. Quét lại trên chính
    # bản ghi đó (`scripts/quet_nguong.py`), khoảng im dài nhất trong vùng ấy:
    #     400 -> 920ms  (KẸT)      600 -> 1240ms
    #     500 -> 1240ms (thoát)    800 -> 1260ms
    # Chọn 500 vì đó là mức thấp nhất thoát được - nâng cao hơn thì tiếng nói
    # nhỏ cuối câu dễ bị coi là im và đuôi câu khách bị cắt.
    phone_vad_rms_off: float = 500.0

    # Ngưỡng tắt TƯƠNG ĐỐI: trong một lượt, khung dưới ngần này phần đỉnh của
    # lượt coi là im, dù vẫn trên `phone_vad_rms_off`. Sinh ra từ cuộc gọi
    # 64b6f2ac (06-09-2026): khách nói 2,4s (đỉnh 3300-8200) rồi im, nhưng TV
    # trong phòng phát tiếng người ở 800-2500 suốt 15 giây; ngưỡng cố định 500
    # không đóng nổi lượt, lưới gió vô dụng vì đó là tiếng người thật. Khách ở
    # gần micro nên to hơn hẳn tiếng nền - 0,15 (≈−16dB dưới đỉnh) đóng lượt
    # sau 3,3s đúng lúc khách dứt lời (`scripts/do_muc_tv.py`); 0,10 vẫn mất
    # 10,9s. Hạ về 0 là tắt hẳn luật này.
    phone_tat_theo_dinh: float = 0.15

    # Mức khách ĐÃ BIẾT (đỉnh của các lượt khách trước, suy giảm dần): tiếng nền
    # nhỏ hơn ngần này phần mức đó thì không được mở lượt mới / không được cắt
    # lời AI. Cuộc 022eb3e5 (06-09-2026, TV mở): khách đỉnh 6383-6713, TV
    # 800-1800 vẫn cắt lời AI và thành lượt 13s được AI đáp. Đo 9 cuộc thật
    # (`scripts/do_dinh_tung_luot.py`): lượt khách thật thấp nhất 0,39× mức to
    # nhất trước đó, TV 0,14-0,27×. Biên mỏng, nên mở lượt lấy 0,20 (bỏ sót lượt
    # khách là nặng), cắt lời lấy 0,30 (bỏ sót một lần cắt lời là nhẹ).
    # Ngưỡng suy ra bị chặn trên bởi `phone_tran_nguong_khach` để khách nói to
    # bất thường một lần không khoá luôn máy. Đặt 0 là tắt.
    phone_mo_theo_muc_khach: float = 0.20
    phone_cat_theo_muc_khach: float = 0.30
    phone_tran_nguong_khach: float = 2000.0
    # Mức khách đã biết giảm một nửa sau ngần này giây không có lượt mới, để khách
    # nói nhỏ đi hay đổi tay cầm máy vẫn được nghe.
    phone_muc_khach_ban_ra_s: float = 90.0

    # Bật bộ khử tiếng AI vọng ngược vào kênh khách (`services/khu_vong.py`).
    # MẶC ĐỊNH TẮT cho tới khi nghiệm thu offline trên bản ghi thật đạt: bản
    # đầu (06-09-2026) phân kỳ trên dữ liệu thật, đầu ra TO HƠN đầu vào 11-32dB
    # và đẻ thêm lượt giả trong phép chạy lại VAD - tệ hơn không làm gì.
    phone_khu_vong: bool = False

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

    # NHẮC KHI HAI BÊN CÙNG IM. Bắt trong cuộc gọi thật `99ee5360`: AI trả lời
    # xong rồi im tuyệt đối 6 giây (đo trên bản ghi, kênh AI bằng 0), khách tưởng
    # đứt máy nên cúp. Pipeline chỉ chạy khi VAD cắt được lượt của khách, mà
    # khách không nói thì không có lượt nào - nên không có gì phá vỡ im lặng.
    #
    # 4 giây: dài hơn quãng nghỉ tự nhiên giữa hai câu (đo trên các cuộc gọi
    # thật là 1-2s), ngắn hơn mốc 6 giây mà khách đã cúp.
    # TẮT từ 06-09-2026 theo yêu cầu người dùng: *"bỏ cơ chế hỏi, nếu AI không
    # nghe thấy chữ mới hỏi hoặc chữ có vấn đề"*.
    #
    # Nhắc theo ĐỒNG HỒ sai về nguyên tắc - im lặng không có nghĩa là hỏng,
    # người ta im để nghĩ. Và nó đã đẻ ra năm lỗi liên tiếp trên cuộc gọi thật:
    # bám ngay sau mỗi câu trả lời, lọt vào lịch sử làm mô hình mất mạch, cờ kẹt
    # làm chết cơ chế, quãng STT+LLM không ai canh, ngưỡng dùng chung cho cả hai
    # lần. Thay bằng `pipeline/hoi_lai.py`: chỉ hỏi khi CÓ LÝ DO NGHE ĐƯỢC.
    #
    # Mã và test giữ nguyên, bật lại bằng biến môi trường nếu cần đối chứng.
    phone_nhac_im_lang: bool = False
    # 6 giây, KHÔNG phải 4. Đo trên cuộc gọi thật `f2f61c42`: ngưỡng 4 giây bắn
    # 6 câu nhắc trong 47 giây, giục khách ngay lúc họ đang nghĩ. Lần nhắc thứ
    # hai còn được nới thêm (xem `HE_SO_LAN_SAU` trong `nhac_im_lang`).
    phone_nhac_sau_giay: float = 6.0
    phone_nhac_toi_da: int = 2

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
    # Mức xuống điện thoại - MỘT nguồn duy nhất: `chuan_muc_thoai` (RMS) và
    # khâu độ to cuối `can_do_to_cuoi` (BS.1770) cùng nhắm con số này.
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
