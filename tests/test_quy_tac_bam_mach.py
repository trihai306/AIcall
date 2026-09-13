"""Lời dặn phải có quy tắc BÁM MẠCH hội thoại.

Người dùng 06-09-2026 sau cuộc gọi thật: "cái tôi thấy nó chưa nhớ lại lịch sử
nhiều". Đo lại thì lịch sử KHÔNG hề bị cắt:

    lịch sử gửi cho mô hình : [system] + TOÀN BỘ history, không cắt dòng nào
    cửa sổ nhớ còn          : 6722 token = ~89 lượt (cuộc gọi chỉ 5-7 lượt)
    tên tổ chức trong prompt: đúng, không hỏng mã

Chỗ hỏng là LỜI DẶN: 12 quy tắc cũ đều nói về cách trả lời MỘT LƯỢT ĐƠN LẺ, không
quy tắc nào bảo mô hình bám vào những gì đã trao đổi. Nó đọc được lịch sử nhưng
không có lý do gì để dùng.

Thấy rõ nhất trên cuộc gọi `c6246696`:
    lượt 1 - AI: "Anh có thể vay tối đa 50 triệu đồng"
    lượt 4 - AI: "Với thu nhập 8 triệu, anh có thể vay tối đa 300 triệu"
tức nó không đối chiếu với chính mình sau ba lượt.
"""
import re

from backend.services.llm_service import LLMService


def _prompt() -> str:
    llm = LLMService.__new__(LLMService)
    return LLMService.build_system_prompt(
        llm, customer_name="Khách thử", product="vay tín chấp", rag_context="")


def test_co_quy_tac_bam_mach():
    p = _prompt()
    assert "BÁM MẠCH" in p, "mất quy tắc bám mạch -> mô hình lại trả lời từng lượt rời nhau"


def test_dan_giu_nguyen_con_so_da_noi():
    """Ràng buộc cụ thể, không phải lời chung chung: đây là lỗi ĐÃ XẢY RA
    (50 triệu rồi 300 triệu trong cùng một cuộc)."""
    p = _prompt()
    assert "GIỮ NGUYÊN" in p


def test_dan_dung_lai_thong_tin_khach_da_cho():
    """Hỏi lại thứ khách vừa nói là dấu hiệu rõ nhất của việc không bám mạch."""
    p = _prompt()
    assert "DÙNG LẠI" in p


def test_vi_du_tinh_toan_khong_duoc_bien_thanh_dieu_kien_cua_khach():
    """Lỗi đo 13-09-2026: khách chỉ nói muốn vay 200 triệu nhưng model tự gán
    luôn 36 tháng vì thấy đúng dòng ví dụ trong tài liệu sản phẩm."""
    p = _prompt()
    assert "ví dụ tính" in p.lower()
    assert re.search(r"KHÔNG tự gán\s+thời\s+hạn", p)


def test_tai_lieu_khong_duoc_bien_thanh_hoan_canh_cua_khach():
    """Lỗi đo 13-09-2026: khách hỏi "nghe rõ không" nhưng model lấy dòng FAQ
    "đã tất toán trên 1 năm" rồi hỏi lại như thể khách vừa nói điều đó."""
    p = _prompt()
    assert "thông tin CHUNG" in p
    assert "KHÔNG có nghĩa khách đã tất toán" in p


def test_khong_day_khach_dang_hoi_dung_san_pham_sang_chuyen_vien():
    """Lỗi đo 13-09-2026: khách chỉ nói cần vay 50 triệu nhưng model tự hứa
    chuyển chuyên viên, dù đây chính là sản phẩm nó đang tư vấn."""
    p = _prompt()
    assert "KHÔNG tự chuyển chuyên viên" in p
    assert "đúng sản phẩm đang tư vấn" in p


def test_prompt_khong_phinh_qua_muc():
    """Prompt dài làm loãng chính những quy tắc đang chạy đúng - dự án đã có bài
    học đắt: nhét thêm nội dung tư vấn vào một lượt có mục đích khác thì mô hình
    bỏ việc được giao (xem lượt định tuyến gọi hàm).

    Trần 6000 ký tự: bản trước quy tắc 13 là ~3960, thêm quy tắc này ~4400.
    """
    n = len(_prompt())
    assert n < 6000, f"prompt đã {n} ký tự - cân nhắc rút gọn trước khi thêm nữa"
