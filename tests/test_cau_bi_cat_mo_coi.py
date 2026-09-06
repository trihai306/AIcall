"""Câu bị cắt lời không được để MỒ CÔI.

CUỘC GỌI THẬT 06-09-2026 (phiên 13d99921). Người dùng: "xem vì sao bị ngắt khi
nói". Log:

    16:43:16  khách: anh vay sáu tháng thì chơi bao nhiêu   <- lượt mở
    16:43:17  khách cắt lời — bỏ 77 khung tiếng AI
    16:43:17  Lượt dừng vì khách cắt lời. Giữ câu để ghép: 'anh vay sáu tháng…'
    16:43:18  bỏ đoạn 120ms - ngắn hơn MIN_TURN_MS=130      <- mẩu sau BỊ VỨT
    16:43:30  đã đóng cầu tiếng                              <- 12 GIÂY IM LẶNG

`cau_bi_cat` CHỈ được ghép khi có lượt MỚI mở (`ghep_cau_bi_cat` trong
`process_turn`). Mẩu nói tiếp ngắn hơn `MIN_TURN_MS` thì không lượt nào mở, nên
câu giữ lại nằm đó mãi - khách hỏi xong không bao giờ được trả lời.

Đối chiếu bản ghi xác nhận: đoạn tiếng AI cuối chỉ dài 0,9 giây ('giảm mức lãi
hiện.') rồi im tới hết cuộc gọi.
"""
from backend.pipeline.session_manager import viec_cho_doan_ngan


def test_doan_ngan_ma_con_cau_bi_cat_thi_TRA_LOI_no():
    assert viec_cho_doan_ngan(120, 130, "anh vay sáu tháng thì chơi bao nhiêu") == \
        "anh vay sáu tháng thì chơi bao nhiêu"


def test_doan_ngan_ma_khong_co_gi_treo_thi_thoi():
    """Khách hắng giọng, không có câu nào đang chờ -> đúng là bỏ đi."""
    assert viec_cho_doan_ngan(120, 130, "") is None
    assert viec_cho_doan_ngan(120, 130, "   ") is None


def test_doan_du_dai_thi_di_duong_thuong():
    """Đủ dài thì `process_turn` tự ghép - đừng chen ngang đường đang đúng."""
    assert viec_cho_doan_ngan(500, 130, "anh vay sáu tháng") is None


def test_dung_moc_bang_dung_la_du_dai():
    assert viec_cho_doan_ngan(130, 130, "câu treo") is None
