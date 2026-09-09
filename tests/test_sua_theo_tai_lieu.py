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


# --- số khách nêu ở LƯỢT TRƯỚC ----------------------------------------------
# Lỗi thật của chính bản sửa này, bắt được ngay lượt chạy thử đầu tiên:
#
#   [lượt 2] khách: lương anh 15 triệu thì vay được bao nhiêu
#   [lượt 3] khách: anh cần 800 triệu có vay được không
#            AI   : "Với thu nhập 15 triệu/tháng, ..."      <- ĐÚNG, nhớ lượt trước
#            lưới : thu nhập 15triệu -> 5triệu              <- SỬA HỎNG
#
# "5 triệu" trong tài liệu là thu nhập TỐI THIỂU để vay, không phải thu nhập của
# khách. Lưới lấy nó đè lên con số thật của khách.
#
# Gốc: `khach_noi` chỉ có lượt HIỆN TẠI. Dự án đã có sổ căn cứ theo phiên
# (`so_can_cu.SoCanCu`) mà `chan_so_sai`/`chan_tien_sai` vẫn dùng - sổ này chỉ
# chứa LỜI KHÁCH và TÀI LIỆU, không chứa lời AI, nên dùng làm miễn trừ là an toàn.

def test_so_khach_neu_o_LUOT_TRUOC_thi_khong_dung_toi():
    ra, mo_ta = sua_theo_tai_lieu(
        "Dạ với thu nhập 15 triệu một tháng thì anh vay được 500 triệu ạ.",
        DOC_VAY, THUOC_TINH_MAC_DINH,
        khach_noi="anh cần 800 triệu có vay được không",
        can_cu_them="lương anh 15 triệu một tháng")
    assert mo_ta is None, f"sửa hỏng câu vốn đúng: {mo_ta}"
    assert "15 triệu" in ra


def test_so_KHONG_o_trong_so_thi_van_sua():
    """Nới cho sổ KHÔNG được nới thành lỗ hổng."""
    ra, mo_ta = sua_theo_tai_lieu(
        "Dạ anh vay được tối đa 300 triệu đồng ạ.", DOC_VAY, THUOC_TINH_MAC_DINH,
        can_cu_them="lương anh 15 triệu một tháng")
    assert mo_ta is not None and "500 triệu" in ra


# --- hai lỗi của chính bản sửa, bắt được khi chấm 250 lượt lịch sử ----------

def test_DAI_thi_khong_thay_so_ma_BO_MENH_DE():
    """Thay cả hai đầu dải bằng một giá trị ra câu vô nghĩa.

    Câu thật: "Dạ anh Minh từ 22 - 60 tuổi mới có thể vay tín chấp được ạ."
    Bản đầu sửa thành "từ 18 tuổi - 18 tuổi" - vì tài liệu chỉ có MỘT giá trị
    tuổi nên nó thay lần lượt cả hai đầu.
    """
    doc = "- Điều kiện: từ 18 tuổi trở lên\n"
    ra, _ = sua_theo_tai_lieu("Dạ anh từ 22 - 60 tuổi mới vay được ạ, em hỗ trợ nhé.",
                              doc, THUOC_TINH_MAC_DINH)
    assert "18 tuổi - 18 tuổi" not in ra, f"ra câu vô nghĩa: {ra!r}"
    assert "22" not in ra and "60" not in ra, f"vẫn còn số sai: {ra!r}"


def test_so_viet_bang_DAU_PHAY_van_bo_duoc():
    """"4,2%" - `re.escape("4.2")` ra `4\\.2`, không khớp dấu phẩy nên bỏ trượt.

    Câu thật trong 250 lượt: mô tả ghi "bỏ mệnh đề có lãi suất 4.2%" mà văn bản
    ra KHÔNG ĐỔI GÌ - tức lưới báo đã sửa trong khi khách vẫn nghe số bịa.
    """
    doc = "- Lãi suất: từ 7.9%/năm\n- Giảm 0.5% lãi suất cho khách có lương qua ngân hàng\n"
    ra, mo_ta = sua_theo_tai_lieu(
        "Dạ lãi suất tiết kiệm là 4,2% một năm ạ. Anh có định gửi không ạ?",
        doc, THUOC_TINH_MAC_DINH)
    assert "4,2" not in ra, f"báo đã sửa mà số bịa vẫn còn: {ra!r}"
    assert mo_ta


def test_bao_da_sua_thi_van_ban_PHAI_doi():
    """Ràng buộc lõi: mô tả khác None thì văn bản bắt buộc phải khác bản gốc.

    Thiếu lưới này thì lỗi "báo đã sửa nhưng không sửa" đi qua im lặng - metrics
    đẹp, log đẹp, khách vẫn nghe số bịa.
    """
    doc = "- Lãi suất: từ 7.9%/năm\n- Giảm 0.5% lãi suất\n"
    for cau in ("Dạ lãi suất tiết kiệm là 4,2% một năm ạ. Anh gửi không ạ?",
                "Dạ anh từ 22 - 60 tuổi mới vay được ạ, em hỗ trợ nhé.",
                "Dạ phí rút tiền là 2.500 đồng ạ. Anh cần gì thêm không?"):
        ra, mo_ta = sua_theo_tai_lieu(cau, doc, THUOC_TINH_MAC_DINH)
        if mo_ta:
            assert ra != cau, f"báo sửa {mo_ta!r} mà văn bản y nguyên: {cau!r}"


def test_dai_co_DON_VI_LAP_LAI_van_la_mot_dai():
    """"10 triệu đến 500 triệu" - `_DAI` cũ chỉ nhận "10 - 500 triệu".

    Hậu quả đo được trên 250 lượt: "Thẻ tín dụng có hạn mức từ 10 triệu đến 500
    triệu đồng ạ. ...thu nhập..." bị đọc thành hai số RỜI, 500 trôi sang thu
    nhập, rồi bị thay thành 5 triệu -> "từ 10 triệu đến 5 triệu".

    Tài liệu thẻ cũng viết "Hạn mức: 10 triệu - 500 triệu đồng" nên chính TÀI
    LIỆU cũng đang bị đọc sai thành hai giá trị rời.
    """
    from backend.pipeline.thuoc_tinh import cap_trong, gia_tri_tai_lieu, khoang_tai_lieu
    cap = cap_trong("Thẻ tín dụng có hạn mức từ 10 triệu đến 500 triệu đồng ạ.",
                    THUOC_TINH_MAC_DINH)
    assert {t for t, _, _ in cap} == {"hạn mức"}, f"hai đầu dải lạc nhau: {cap}"

    doc = "- Hạn mức: 10 triệu - 500 triệu đồng\n"
    assert khoang_tai_lieu(doc, THUOC_TINH_MAC_DINH).get("hạn mức"), \
        "tài liệu ghi dải mà không đọc ra dải"
    assert {s for s, _ in gia_tri_tai_lieu(doc, THUOC_TINH_MAC_DINH)["hạn mức"]} \
        == {"10", "500"}


def test_so_TRONG_dai_cua_tai_lieu_thi_cho_qua():
    doc = "- Hạn mức: 10 triệu - 500 triệu đồng\n"
    ra, mo_ta = sua_theo_tai_lieu("Dạ hạn mức thẻ của anh là 200 triệu ạ.",
                                  doc, THUOC_TINH_MAC_DINH)
    assert mo_ta is None, f"200 nằm trong dải 10-500 mà bị sửa: {mo_ta}"


def test_bo_menh_de_xong_phai_DON_dau_treo():
    """Cắt xong còn "hộ khẩu," là khách nghe câu cụt lủng, TTS đọc lên rất kỳ.

    Câu thật trong 250 lượt: "cần CMND/CCCD, hộ khẩu, xác nhận thu nhập hoặc sao
    kê lương trong vòng 3-6 tháng" -> cắt vế cuối còn "cần CMND/CCCD, hộ khẩu,".
    """
    doc = "- Sao kê: sao kê lương 3 tháng gần nhất\n"
    ra, mo_ta = sua_theo_tai_lieu(
        "Anh chị cần CMND/CCCD, hộ khẩu, sao kê lương 3-6 tháng gần nhất ạ.",
        doc, THUOC_TINH_MAC_DINH)
    assert mo_ta
    assert not ra.rstrip().endswith(","), f"còn dấu phẩy treo: {ra!r}"
    assert ra.rstrip().endswith((".", "?", "!")), f"không có dấu kết câu: {ra!r}"
