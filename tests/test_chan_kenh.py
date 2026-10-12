"""Lưới kênh: câu mô hình viết chỉ được nêu kênh làm việc mà TÀI LIỆU có.

Lỗi thật 12-10-2026, bộ thử 156 lượt: hỏi "apply online được không" về thẻ tín
dụng thì nhận "nộp hồ sơ trực tuyến trên ứng dụng hoặc website của ngân hàng".
"""
from backend.pipeline.chan_kenh import CAU_CHUA_CO_KENH, chan_kenh_la, kenh_duoc_phep, kenh_la

THE = "# Thẻ Tín Dụng\n- Hạn mức: 10 triệu - 500 triệu đồng\n- Từ 18 tuổi trở lên\n"
GUI = ("# Gửi Tiết Kiệm\n- Hình thức: gửi tại quầy hoặc gửi online\n"
       "- Mở sổ trong 5 phút trên ứng dụng, không cần đến quầy\n")


def test_cau_that_bi_thay_bang_cau_xin_ghi_nhan():
    cau = "Dạ em trả lời anh chị ạ, Anh/chị có thể nộp hồ sơ trực tuyến trên ứng dụng hoặc website của ngân hàng ạ."
    ra, mo_ta = chan_kenh_la(cau, THE)
    assert ra == CAU_CHUA_CO_KENH and "online" in mo_ta and "ung_dung" in mo_ta


def test_tai_lieu_co_kenh_thi_duoc_noi():
    assert kenh_duoc_phep(GUI) >= {"online", "ung_dung"}
    cau = "Dạ anh chị gửi online trên ứng dụng hoặc đến quầy đều được ạ."
    assert chan_kenh_la(cau, GUI) == (cau, "")


def test_chi_bo_cau_vi_pham_giu_phan_con_lai():
    cau = ("Dạ thẻ Classic có phí thường niên là 200.000đ/năm từ năm thứ hai ạ. "
           "Anh muốn em gửi thông tin chi tiết về loại thẻ này qua ứng dụng ngân hàng không?")
    ra, mo_ta = chan_kenh_la(cau, THE)
    assert ra == "Dạ thẻ Classic có phí thường niên là 200.000đ/năm từ năm thứ hai ạ."
    assert mo_ta


def test_cau_phu_dinh_khong_bi_bat():
    for cau in ("Hiện tại bên em chưa có số Zalo của anh ạ.",
                "Dạ em chưa có thông tin về đăng ký online cho thẻ này ạ.",
                "Lịch sử chuyển khoản qua app chưa phải là sao kê lương ạ.",
                "Dạ ngân hàng không gửi link qua tin nhắn cho anh chị ạ."):
        assert kenh_la(cau, THE) == [], cau


def test_hua_gui_bi_bat_ke_ca_khi_tai_lieu_co_kenh():
    assert "hua_gui" in kenh_la("Em sẽ gửi link đăng ký qua Zalo cho anh ngay ạ.", GUI)


def test_gui_thong_tin_va_xin_email_khong_bi_bat():
    for cau in ("Em xin phép gửi anh thông tin chi tiết về lãi suất và hạn mức nhé.",
                "Anh chị để lại số điện thoại hoặc email để chuyên viên liên hệ nhé."):
        assert kenh_la(cau, THE) == [], cau


def test_khong_co_tai_lieu_thi_khong_phan():
    cau = "Anh chị nộp hồ sơ trên ứng dụng ạ."
    assert chan_kenh_la(cau, "") == (cau, "")


def test_khong_bat_chu_nam_trong_tu_khac():
    # "app" trong "apple", "web" trong "webcam" không phải nêu kênh.
    assert kenh_la("Anh dùng apple pay hay thẻ cứng ạ?", THE) == []


def test_khong_cat_cau_o_dau_cham_thap_phan():
    from backend.pipeline.chan_kenh import tach_cau
    assert tach_cau("Dạ, lãi suất từ 7.9%/năm, phí 500.000đ ạ. Còn gì nữa không ạ?") == [
        "Dạ, lãi suất từ 7.9%/năm, phí 500.000đ ạ.", " Còn gì nữa không ạ?"]
    ra, _ = chan_kenh_la("Dạ, lãi suất từ 7.9%/năm ạ. Anh chị mở ứng dụng để nộp hồ sơ ạ.", THE)
    assert ra == "Dạ, lãi suất từ 7.9%/năm ạ."


SAN_PHAM = ["the_tin_dung", "tiet_kiem", "vay_mua_nha", "vay_tin_chap"]


def test_phu_nhan_san_pham_dang_co_tai_lieu():
    from backend.pipeline.chan_kenh import chan_phu_nhan_san_pham, san_pham_bi_phu_nhan
    cau = "Hiện tại bên em chỉ hỗ trợ vay mua nhà chứ chưa có gói vay tín chấp riêng để đặt cọc ạ."
    assert san_pham_bi_phu_nhan(cau, SAN_PHAM) == "vay_tin_chap"
    assert chan_phu_nhan_san_pham(cau, SAN_PHAM)[0] == CAU_CHUA_CO_KENH


def test_khong_bat_cau_chi_nhac_ten_san_pham():
    from backend.pipeline.chan_kenh import san_pham_bi_phu_nhan
    for cau in ("Em chưa có thông tin về vay tín chấp cho trường hợp này ạ.",
                "Dạ vay tín chấp không cần tài sản thế chấp ạ.",
                "Bên em không có phí mở thẻ tín dụng năm đầu ạ.",
                "Hiện bên em chưa có sản phẩm bảo hiểm ạ."):
        assert san_pham_bi_phu_nhan(cau, SAN_PHAM) == "", cau
