"""Lưới bắt được thì SỬA CÂU, không phải im lặng và cũng không phải câu mẫu.

Trước 09-09-2026 lưới thuộc tính chỉ ghi nhật ký - khách vẫn nghe nguyên câu
bịa. Câu hỏi của người dùng: "chặn thì nó im lặng không trả lời à?"

Không. Thang xử lý, rẻ trước:

  1. THAY SỐ   - tài liệu có ĐÚNG MỘT giá trị cho thuộc tính đó thì thay vào.
                 Giữ nguyên câu, nghe tự nhiên nhất.
  2. BỎ MỆNH ĐỀ - tài liệu không có, hoặc có nhiều giá trị không biết chọn cái
                 nào. Bỏ đúng mệnh đề chứa số sai, giữ phần còn lại.
  3. rỗng      - bỏ xong không còn gì. Chỗ gọi dùng `CAU_KIEM_TRA_LAI`.

VÌ SAO KHÔNG thay cả câu bằng câu mẫu ngay từ đầu: đó chính là cách đã đẻ ra
lời than "trả lời 1 kiểu" của người dùng - lưới thay hai câu khác nhau bằng
cùng một câu. Xem `chat-ai-luoi-so-chan-nham`.

VÌ SAO chỉ thay số khi tài liệu có ĐÚNG MỘT giá trị: tài liệu vay tín chấp có
cả "7.9%/năm" lẫn "Giảm 0.5% lãi suất", nên "lãi suất" có hai giá trị. Đoán bừa
một trong hai rồi đọc cho khách nghe còn tệ hơn bỏ hẳn mệnh đề.
"""
from backend.pipeline.thuoc_tinh import THUOC_TINH_MAC_DINH, sua_theo_tai_lieu

DOC_VAY = """- Lãi suất: từ 7.9%/năm
- Hạn mức: lên đến 500 triệu đồng
- Thời hạn: 12 - 60 tháng
- Giải ngân: trong vòng 24 giờ
"""


def test_tai_lieu_co_MOT_gia_tri_thi_THAY_SO():
    """Câu thật AI đã nói: "vay tối đa 300 triệu" trong khi tài liệu ghi 500."""
    ra, mo_ta = sua_theo_tai_lieu(
        "Dạ anh vay được tối đa 300 triệu đồng ạ.", DOC_VAY, THUOC_TINH_MAC_DINH)
    assert "500 triệu" in ra, f"chưa thay số: {ra!r}"
    assert "300" not in ra
    assert mo_ta and "300" in mo_ta


def test_thay_so_GIU_NGUYEN_phan_con_lai_cua_cau():
    ra, _ = sua_theo_tai_lieu(
        "Dạ anh vay được tối đa 300 triệu đồng ạ, em hỗ trợ hồ sơ nhanh gọn.",
        DOC_VAY, THUOC_TINH_MAC_DINH)
    assert "em hỗ trợ hồ sơ nhanh gọn" in ra


def test_tai_lieu_KHONG_CO_thuoc_tinh_thi_BO_MENH_DE():
    """Câu thật: "phí rút tiền mặt tại ATM là 2.500 đồng" - tài liệu không có."""
    ra, mo_ta = sua_theo_tai_lieu(
        "Dạ bên em giải ngân trong 24 giờ, phí rút tiền mặt là 2.500 đồng ạ.",
        DOC_VAY, THUOC_TINH_MAC_DINH)
    assert "2.500" not in ra and "2500" not in ra, f"vẫn còn số bịa: {ra!r}"
    assert "24 giờ" in ra, f"bỏ nhầm cả phần đúng: {ra!r}"
    assert mo_ta


def test_bo_het_thi_tra_RONG_de_cho_goi_quyet():
    """Không còn gì để nói -> trả rỗng, chỗ gọi mới dùng câu "em kiểm tra lại"."""
    ra, mo_ta = sua_theo_tai_lieu(
        "Dạ phí rút tiền mặt là 2.500 đồng ạ.", DOC_VAY, THUOC_TINH_MAC_DINH)
    assert ra == "" and mo_ta


def test_NHIEU_gia_tri_thi_khong_doan_bua():
    """Tài liệu có 7.9% và 0.5% cho lãi suất - không biết chọn cái nào thì BỎ."""
    doc = DOC_VAY + "- Giảm 0.5% lãi suất cho khách có lương qua ngân hàng\n"
    ra, _ = sua_theo_tai_lieu("Dạ lãi suất chỉ 5% một năm ạ, rất ưu đãi.",
                              doc, THUOC_TINH_MAC_DINH)
    assert "5%" not in ra and "7.9" not in ra, f"đoán bừa: {ra!r}"


def test_cau_DUNG_thi_khong_dung_toi():
    ra, mo_ta = sua_theo_tai_lieu("Dạ hạn mức lên đến 500 triệu đồng ạ.",
                                  DOC_VAY, THUOC_TINH_MAC_DINH)
    assert mo_ta is None and ra == "Dạ hạn mức lên đến 500 triệu đồng ạ."


def test_so_NAM_TRONG_DAI_thi_khong_dung_toi():
    ra, mo_ta = sua_theo_tai_lieu("Dạ vay trong 36 tháng ạ.", DOC_VAY,
                                  THUOC_TINH_MAC_DINH)
    assert mo_ta is None and "36" in ra


def test_so_do_KHACH_neu_thi_khong_dung_toi():
    ra, mo_ta = sua_theo_tai_lieu(
        "Dạ hạn mức anh cần là 400 triệu ạ.", DOC_VAY, THUOC_TINH_MAC_DINH,
        khach_noi="anh muốn vay 400 triệu")
    assert mo_ta is None and "400" in ra


def test_van_ban_rong_thi_khong_no():
    assert sua_theo_tai_lieu("", DOC_VAY, THUOC_TINH_MAC_DINH) == ("", None)
