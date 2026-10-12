"""Ba lưới chặn câu mô hình tự chế - các ca lấy từ bộ thử 156 lượt 12-10-2026."""

from backend.pipeline.chan_tu_che import (
    CAU_GHI_NHAN, chan_phan_theo_thu_nhap, chan_chua_co_thong_tin_sai, chan_phu_thuoc_bia, chan_tu_nhan_la_nguoi,
    chan_tu_cup_may)

TAI_LIEU = "## Lãi suất\n- Lãi suất từ 7.9%/năm\n- Hạn mức tối đa 500 triệu đồng\n"


def test_khach_than_ma_ai_tu_cup_may():
    for cau in ("Dạ vâng, Em xin lỗi đã làm phiền ạ. Em xin phép kết thúc cuộc gọi.",
                "Em xin lỗi vì đã làm anh mất thời gian ạ. Cảm ơn anh đã gọi cho bên em nhé.",
                "Chúc anh mọi điều tốt đẹp nhé.", "Em xin phép kết cuộc gọi.",
                "Em cảm ơn và xin phép kết thúc."):
        ra, sua = chan_tu_cup_may(cau, "dậy thôi hả kỳ dậy")
        assert sua and ra == ""


def test_khach_tu_choi_thi_ai_duoc_chao():
    cau = "Dạ em cảm ơn anh chị, em xin phép không làm phiền thêm ạ."
    for khach in ("thôi anh không có nhu cầu", "ừ thế nhé cảm ơn em nhé", "tạm biệt em"):
        assert chan_tu_cup_may(cau, khach) == (cau, "")


def test_chi_bo_cau_cup_may_giu_phan_con_lai():
    ra, sua = chan_tu_cup_may(
        "Dạ lãi suất bên em từ 7.9% một năm ạ. Em xin phép kết thúc cuộc gọi.",
        "lãi bao nhiêu")
    assert sua and ra == "Dạ lãi suất bên em từ 7.9% một năm ạ."


def test_phan_han_muc_theo_thu_nhap():
    ra, sua = chan_phan_theo_thu_nhap(
        "Anh chị chốt giúp em số tiền cụ thể muốn vay ạ? Với thu nhập hiện tại, "
        "anh có thể vay tối đa 500 triệu trong thời hạn từ 12 đến 60 tháng.")
    assert sua and ra == "Anh chị chốt giúp em số tiền cụ thể muốn vay ạ?"


def test_khong_bat_cau_hoi_va_cau_con_tham_dinh():
    for cau in ("Với thu nhập 10 triệu thì anh muốn vay khoảng bao nhiêu ạ?",
                "Với thu nhập này anh có thể vay, mức cụ thể còn tuỳ thẩm định hồ sơ ạ.",
                "Hạn mức vay tối đa của bên em là 500 triệu đồng ạ."):
        assert chan_phan_theo_thu_nhap(cau) == (cau, "")


def test_lai_suat_phu_thuoc_ho_so_khong_co_trong_tai_lieu():
    ra, sua = chan_phu_thuoc_bia(
        "Dạ vâng ạ, Em ghi nhận ạ. Mức lãi suất cụ thể còn phụ thuộc vào hồ sơ và thu "
        "nhập của từng khách hàng, nên con số thực tế sẽ khác nhau. Anh chị muốn vay "
        "trong bao lâu?", TAI_LIEU)
    assert sua and "phụ thuộc" not in ra and ra.endswith("Anh chị muốn vay trong bao lâu?")


def test_tai_lieu_co_noi_phu_thuoc_thi_de_nguyen():
    cau = "Dạ lãi suất còn tuỳ theo hồ sơ của anh chị ạ."
    co = TAI_LIEU + "- Lãi suất cụ thể tuỳ theo hồ sơ khách hàng\n"
    assert chan_phu_thuoc_bia(cau, co) == (cau, "")
    assert chan_phu_thuoc_bia(cau, "") == (cau, "")
    assert chan_phu_thuoc_bia(cau, TAI_LIEU) == (CAU_GHI_NHAN, chan_phu_thuoc_bia(cau, TAI_LIEU)[1])


def test_cau_binh_thuong_khong_bi_dung():
    cau = "Dạ lãi suất tiết kiệm tuỳ theo kỳ hạn, từ 3,5% đến 6% một năm ạ."
    assert chan_phu_thuoc_bia(cau, TAI_LIEU) == (cau, "")
    assert chan_tu_cup_may(cau, "lãi sao em") == (cau, "")


def test_bao_chua_co_thong_tin_trong_khi_tai_lieu_co():
    ra, sua = chan_chua_co_thong_tin_sai(
        "Anh chị chốt giúp em số tiền cụ thể muốn vay ạ? Hiện tại bên em chưa có thông tin "
        "cụ thể về mức lãi suất hay hạn mức dành riêng cho trường hợp này.", TAI_LIEU)
    assert sua and ra == "Anh chị chốt giúp em số tiền cụ thể muốn vay ạ?"
    # tài liệu không có mục đó thì câu nói thật, để nguyên
    cau = "Dạ hiện em chưa có thông tin về kỳ hạn của sản phẩm này ạ."
    assert chan_chua_co_thong_tin_sai(cau, TAI_LIEU) == (cau, "")
    cau = "Dạ em chưa có thông tin về giá vàng hôm nay ạ."
    assert chan_chua_co_thong_tin_sai(cau, TAI_LIEU) == (cau, "")


def test_chua_co_thong_tin_them_chu_de_va_ngoai_le_ho_so_khach():
    tl = TAI_LIEU + "- Thu nhập từ 5 triệu đồng/tháng\n- Giấy tờ pháp lý: sổ đỏ hoặc sổ hồng\n"
    for cau in ("Hiện tại bên em chưa có thông tin cụ thể về mức thu nhập cần thiết để duyệt khoản vay này ạ.",
                "Em xin lỗi, thông tin về việc có cần sổ đỏ hay không thì em chưa tra cứu được ạ."):
        assert chan_chua_co_thong_tin_sai(cau, tl)[1], cau
    cau = "Dạ em chưa có thông tin về thu nhập của anh nên chưa tính được ạ."
    assert chan_chua_co_thong_tin_sai(cau, tl) == (cau, "")


def test_tu_nhan_la_nguoi_that():
    ra, sua = chan_tu_nhan_la_nguoi(
        "Em xin lỗi vì anh chị hiểu lầm ạ. Em đang trò chuyện trực tiếp với Lan, nhân viên ngân hàng.")
    assert sua and "nhân viên ngân hàng" not in ra
    cau = "Dạ em là trợ lý tư vấn tự động của ngân hàng ạ."
    assert chan_tu_nhan_la_nguoi(cau) == (cau, "")


def test_muc_cu_the_phu_thuoc_ho_so_trong_mach_lai_suat():
    cau = ("Em xin lỗi, thông tin lãi suất từ 7.9%/năm là mức chung của sản phẩm ạ. Mức cụ thể còn "
           "phụ thuộc vào hồ sơ và thu nhập thực tế của anh chị nên em chưa thể so sánh ngay được.")
    ra, sua = chan_phu_thuoc_bia(cau, TAI_LIEU)
    assert sua and "phụ thuộc" not in ra and "7.9%" in ra
    # mảnh sau đứng một mình: mạch lãi suất đến từ lời khách và câu AI vừa nói
    manh = "Mức cụ thể còn phụ thuộc vào hồ sơ và thu nhập thực tế của anh chị."
    assert chan_phu_thuoc_bia(manh, TAI_LIEU, ngu_canh="cao thế bên kia lãi sáu phẩy mấy thôi")[1]
    assert chan_phu_thuoc_bia(manh, TAI_LIEU) == (manh, "")
    # mức được DUYỆT phụ thuộc hồ sơ là câu đúng
    dung = "Hạn mức tối đa là 500 triệu ạ. Mức được duyệt thực tế còn phụ thuộc hồ sơ của anh chị."
    assert chan_phu_thuoc_bia(dung, TAI_LIEU, ngu_canh="lãi bao nhiêu vay được bao nhiêu") == (dung, "")
