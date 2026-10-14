from backend.pipeline.luot_theo_ngu_canh import rut_gon_neu_lap, tra_loi_theo_ngu_canh
from backend.pipeline.luot_thuong_gap import nhan_dang


def _h(ai: str) -> list[dict]:
    return [{"role": "user", "content": "bao lâu"}, {"role": "assistant", "content": ai}]


def test_u_sau_cau_tra_loi_la_gat_dau():
    assert tra_loi_theo_ngu_canh("ừ", _h("Dạ anh chị có thể vay từ 12 đến 60 tháng ạ.")) \
        == ("gat_dau", "Dạ vâng ạ.")
    # sau một CÂU HỎI thì "ừ" là câu trả lời, để đường cũ lo
    assert tra_loi_theo_ngu_canh("ừ", _h("Anh chị muốn vay 12 tháng được không ạ?")) is None
    assert tra_loi_theo_ngu_canh("ừ thế lãi bao nhiêu", _h("Dạ được ạ.")) is None
    assert tra_loi_theo_ngu_canh("ừ", []) is None


def test_noi_nhanh_qua_thi_nhac_lai_noi_dung():
    ma, cau = tra_loi_theo_ngu_canh(
        "em nói nhanh quá anh không nghe kịp",
        _h("Dạ em trả lời anh chị ạ, lãi suất vay tín chấp bên em từ 7.9%/năm ạ. "
           "Anh chị dự định vay khoảng bao nhiêu ạ?"))
    assert ma == "noi_cham_lai" and "7.9%/năm" in cau and "dự định vay" not in cau
    assert cau.startswith("Dạ em xin lỗi ạ, em xin nói lại chậm hơn ạ. Lãi suất")


def test_ba_y_dinh_moi_cua_luot_thuong_gap():
    assert nhan_dang("thế em gửi zalo cho anh đi") == "xin_gui_qua_kenh"
    assert nhan_dang("làm luôn qua điện thoại được không") == "lam_qua_dien_thoai"
    assert nhan_dang("chờ anh tí con ơi đừng nghịch ừ em nói đi") == "moi_noi_tiep"
    assert nhan_dang("zalo bên em có lừa đảo không") != "xin_gui_qua_kenh"


def test_ha_va_noi_lai_thi_nhac_dung_cau_vua_noi():
    ai = "Dạ, mức lãi suất vay tín chấp của chúng em từ 7.9%/năm ạ. Anh chị dự định vay khoảng bao nhiêu ạ?"
    for khach in ("hả", "gì cơ em nói lại xem nào", "em nói lại đi"):
        ma, cau = tra_loi_theo_ngu_canh(khach, _h(ai))
        assert ma == "nhac_lai" and "7.9%/năm" in cau and "dự định vay" not in cau, khach
    # xin nhắc lại MỘT dữ kiện cụ thể là việc của luật khoản vay
    assert tra_loi_theo_ngu_canh("em nhắc lại lãi suất đi", _h(ai)) is None
    # nhắc lại hai lần liền không lồng lời dẫn
    lan1 = tra_loi_theo_ngu_canh("hả", _h(ai))[1]
    assert tra_loi_theo_ngu_canh("hả", _h(lan1))[1] == lan1


def test_xin_noi_cham_ngay_luot_dau():
    ma, cau = tra_loi_theo_ngu_canh("cháu ơi bác già rồi không rành cháu nói chậm thôi nhé", [])
    assert ma == "noi_cham_lai" and cau.endswith("cần em tư vấn phần nào ạ?")


def test_cau_luat_lap_nguyen_van_thi_rut_gon():
    cau = ("Dạ em tạm tính theo lãi suất từ 7,9% một năm, trên dư nợ giảm dần ạ. Nếu được duyệt "
           "200 triệu đồng trong 3 năm thì tháng đầu trả khoảng 6,9 triệu đồng, các tháng sau "
           "giảm dần. Đây là số ước tính, chưa phải lịch trả nợ chính thức.")
    ra = rut_gon_neu_lap(cau, _h(cau))
    assert ra.startswith("Dạ như em vừa tính ạ. Nếu được duyệt 200 triệu") and "7,9%" not in ra
    assert rut_gon_neu_lap(cau, _h("Dạ vay 3 năm thì được ạ.")) == cau


def test_mot_thang_hay_mot_nam_la_hoi_don_vi_lai():
    h = _h("Dạ vâng, Đúng rồi ạ, lãi suất là bảy phẩy chín phần trăm một năm. Anh chị muốn vay trong bao lâu?")
    assert tra_loi_theo_ngu_canh("một tháng hay một năm", h) == ("don_vi_lai", "Dạ mức lãi suất đó tính theo năm ạ.")
    assert tra_loi_theo_ngu_canh("một tháng hay một năm", _h("Anh chị muốn vay trong bao lâu ạ?")) is None


def test_u_sau_cau_hoi_mo_thi_hoi_lai_dung_cau_do():
    h = _h("Dạ anh chị có thể vay từ 12 đến 60 tháng ạ. Thu nhập hàng tháng của anh chị khoảng bao nhiêu ạ?")
    assert tra_loi_theo_ngu_canh("ừ", h) == (
        "gat_dau_hoi_lai", "Dạ vâng ạ. Thu nhập hàng tháng của anh chị khoảng bao nhiêu ạ?")
    co_khong = _h("Anh chị có muốn em ghi nhận để chuyên viên hỗ trợ làm hồ sơ không ạ?")
    assert tra_loi_theo_ngu_canh("ừ", co_khong) is None


def test_ket_qua_moi_khong_bi_goi_la_nhu_em_vua_tinh():
    from backend.pipeline.luot_theo_ngu_canh import rut_gon_neu_lap
    dau = "Dạ em tạm tính theo lãi suất từ 7,9% một năm, trên dư nợ giảm dần ạ. "
    duoi = " Đây là số ước tính, chưa phải lịch trả nợ chính thức."
    cu = dau + "Nếu được duyệt 150 triệu đồng trong 2 năm thì tháng đầu trả khoảng 7,2 triệu đồng, các tháng sau giảm dần." + duoi
    moi = dau + "Nếu được duyệt 150 triệu đồng trong 3 năm thì tháng đầu trả khoảng 5,2 triệu đồng, các tháng sau giảm dần." + duoi
    h = [{"role": "assistant", "content": cu}]
    ra = rut_gon_neu_lap(moi, h)
    assert "như em vừa tính" not in ra and "3 năm" in ra and "5,2 triệu" in ra and ra.startswith("Dạ nếu")
    assert rut_gon_neu_lap(cu, h).startswith("Dạ như em vừa tính ạ.")       # trùng thật thì vẫn rút gọn như cũ
