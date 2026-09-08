"""Mô hình phải biết câu đệm vừa phát, để NÓI TIẾP thay vì mở đầu lại.

Người dùng 06-09-2026, kèm ảnh chụp: câu đệm nói "Dạ về phần tài liệu," rồi mô
hình đáp "em sẽ gửi thông tin chi tiết về sản phẩm vay tín chấp cho anh ngay" —
"nghe nó vẫn rất máy móc, ko nối luôn vào câu".

Cơ chế cũ chỉ XOÁ chữ "Dạ" ở đầu câu trả lời (`BotLichSu(bo_da=...)`) — xử lý
hậu kỳ trên chuỗi. Mô hình vẫn sinh câu như thể chưa ai nói gì, nên nó mở đầu
lại và lặp ý của chính câu đệm.

Đây là DỮ KIỆN thật đưa vào lượt, không phải một quy tắc chung nữa: quy tắc
"bám mạch" thêm vào prompt hôm nay đã không ăn, vì nó bị quy tắc 3 (mọi con số
lấy từ THÔNG TIN THAM KHẢO) đè - khối tham khảo nằm sát câu hỏi hơn.
"""
from backend.services.llm_service import LLMService


def _prompt(cau_dem: str = "") -> str:
    llm = LLMService.__new__(LLMService)
    return LLMService.build_system_prompt(
        llm, customer_name="Khách thử", product="vay tín chấp",
        rag_context="", cau_dem=cau_dem)


def test_co_cau_dem_thi_BO_dan_mo_dau_bang_da():
    """Câu đệm gần như luôn mở bằng "Dạ"; giữ lời dặn đó là khách nghe
    "Dạ ... Dạ ..." hai lần liền."""
    assert 'mở đầu bằng "Dạ"' not in _prompt("Dạ về hạn mức thì,")


def test_khong_co_cau_dem_thi_GIU_NGUYEN():
    p = _prompt("")
    assert 'mở đầu bằng "Dạ"' in p, "mất lời dặn của lượt không có câu đệm"


def test_KHONG_con_dan_noi_cau_bang_chu():
    """Ba cách dặn bằng prompt đã thử và hỏng ba kiểu (06-09-2026):

        luật chung        -> bị luật số 3 đè
        ví dụ nhãn SAI    -> mô hình CHÉP ví dụ sai
        mẫu dạng "A + B"  -> mô hình chép cả vế A

    Việc nối câu nay do `prefill` lo. Còn sót lời dặn bằng chữ là mời mô hình
    chép lại chúng - đúng cái bẫy vừa thoát ra.
    """
    p = _prompt("Dạ về hạn mức thì,")
    for dau in ("VẾ SAU", "SAI :", "ĐÚNG:", "Dạ về hạn mức thì,"):
        assert dau not in p, f"prompt còn sót {dau!r}"


def test_prefill_duoc_gan_vao_messages():
    """Canh đúng cơ chế: câu đệm phải vào `messages` với role assistant, KHÔNG
    phải vào system prompt."""
    import inspect
    from backend.services import llm_service
    src = inspect.getsource(llm_service.LLMService.stream_response)
    assert '"role": "assistant", "content": prefill' in src


def test_prefill_rong_thi_khong_them_gi():
    """Lượt bị bỏ câu đệm phải giữ nguyên hành vi cũ."""
    import inspect
    from backend.services import llm_service
    src = inspect.getsource(llm_service.LLMService.stream_response)
    assert 'if (prefill or "").strip():' in src


# --- filler_text phai la CHU THAT, khong phai nhan --------------------------

def test_chu_cua_filler_dung_ghep_that():
    """`prefill` chỉ có tác dụng khi chuỗi khớp TỪNG KÝ TỰ với tiếng khách nghe.

    Lỗi đã xảy ra 06-09-2026: nơi gọi tự suy chữ từ `id_duoi`, và khi kho đuôi
    rỗng nó ghi nhãn "(chỉ mẩu mở đầu)". Prefill nhét nguyên cái nhãn đó vào
    miệng mô hình -> mô hình bỏ qua và viết câu mới, lặp lại nguyên chủ đề:
    "Dạ về hạn mức vay thì, Hạn mức vay tín chấp tối đa lên đến 500 triệu ạ."

    Nay chữ đi CÙNG clip, dựng bằng đúng `ghep()` đã dùng lúc dựng clip.
    """
    import types
    from backend.services.tts_service import F5TTSService

    kho = types.SimpleNamespace(
        duoi=(),
        tinh_huong=(types.SimpleNamespace(
            id="hoi_han_muc", mo_dau=("Dạ về hạn mức vay thì,", "Dạ hạn mức bên em thì,")),),
    )
    assert F5TTSService._chu_cua_filler(kho, "hoi_han_muc", 0, "") == "Dạ về hạn mức vay thì,"
    assert F5TTSService._chu_cua_filler(kho, "hoi_han_muc", 1, "") == "Dạ hạn mức bên em thì,"


def test_chu_cua_filler_khong_no_khi_thieu_du_lieu():
    """Tình huống vừa bị xoá trên giao diện mà clip còn trên đĩa - không được ném
    lỗi giữa lượt đang phục vụ khách."""
    import types
    from backend.services.tts_service import F5TTSService
    kho = types.SimpleNamespace(duoi=(), tinh_huong=())
    assert F5TTSService._chu_cua_filler(kho, "khong_ton_tai", 0, "") == ""
    assert F5TTSService._chu_cua_filler(kho, "khong_ton_tai", 99, "") == ""


# --- Prefill: DUNG luot va KHONG dung luot ---------------------------------

def _nguon(ten_ham: str) -> str:
    import inspect
    from backend.pipeline.streaming_pipeline import StreamingPipeline
    return inspect.getsource(getattr(StreamingPipeline, ten_ham))


def test_luot_dinh_tuyen_goi_ham_KHONG_duoc_prefill():
    """Suýt vá nhầm 07-09-2026: tưởng `stream_response` trong `_tra_bang_cong_cu`
    là lượt sinh câu trả lời sau khi gọi hàm. Không phải - đó là lượt ĐỊNH TUYẾN,
    mô hình chỉ quyết có gọi hàm không, chữ nó sinh ra bị vứt.

    Nhét prefill vào đó là có hại: thấy câu dở, mô hình viết tiếp thay vì xin
    gọi hàm - đúng bẫy dự án đã ghi (prompt tư vấn giết chết việc gọi hàm).
    """
    src = _nguon("_tra_bang_cong_cu")
    assert "PROMPT_QUYET_DINH" in src, "lượt định tuyến đã đổi chỗ, cập nhật test"
    assert "prefill" not in src, "lượt định tuyến gọi hàm KHÔNG được nhận prefill"


def test_luot_tra_loi_that_PHAI_prefill():
    """Kết quả gọi hàm chảy vào system prompt rồi vào đúng lượt này - nên đường
    gọi hàm đã có prefill mà không cần vá riêng."""
    src = _nguon("_generate_response")
    assert 'prefill=metrics.get("filler_text", "")' in src
