import pytest

from backend.pipeline.sua_nghe_sai import sua_nghe_sai


@pytest.mark.parametrize("vao,ra", [
    ("xuất bao nhiêu", "lãi suất bao nhiêu"),
    ("lãi", "lãi suất bao nhiêu"),
    ("thế lãi sao em", "lãi suất bao nhiêu"),
    ("ờ cho anh thông tin về khoảng tay bên mình", "ờ cho anh thông tin về khoản vay bên mình"),
    ("phí thường liên thế nào", "phí thường niên thế nào"),
    ("vay tín chóp thì cần những giấy tờ gì", "vay tín chấp thì cần những giấy tờ gì"),
    ("chị muốn hỏi vay mua nhà thì nãi xuất thế lào", "chị muốn hỏi vay mua nhà thì lãi suất thế nào"),
    ("ừ tư vấn với anh về sản phẩm thẻ tính dụng", "ừ tư vấn với anh về sản phẩm thẻ tín dụng"),
    ("hạng mức tối đa là bao nhiêu", "hạn mức tối đa là bao nhiêu"),
    ("miễn lải bao nhiêu ngày", "miễn lãi bao nhiêu ngày"),
    ("hồ sơ", "cần giấy tờ gì"),
    ("tối đa", "hạn mức tối đa bao nhiêu"),
    ("thế có cần xổ đỏ không em", "thế có cần sổ đỏ không em"),
    ("chả trong hai mươi lăm thì mỗi tháng chả bao nhiêu", "trả trong hai mươi lăm thì mỗi tháng trả bao nhiêu"),
    ("em ơi o muốn gửi tiết kiệm thì lãi răng em", "em ơi o muốn gửi tiết kiệm thì lãi suất thế nào em"),
])
def test_sua(vao, ra):
    moi, mo_ta = sua_nghe_sai(vao)
    assert moi == ra and mo_ta


@pytest.mark.parametrize("cau", [
    "lãi suất vay tín chấp bao nhiêu",
    "anh muốn vay khoảng hai trăm triệu",
    "lãi nhập gốc không em",
    "phí phạt trả trước là bao nhiêu",
    "anh tính dùng thẻ để mua hàng",
    "ừ",
    "bao lâu",
    "em nói lại xem",
    "lãi cao thế",
    "lỗi đó lại xuất hiện rồi",
    "anh chả biết nữa",
    "chả cần đâu em",
    "lãi sao kê là gì",
    "nhiêu",
])
def test_khong_dung_cau_binh_thuong(cau):
    assert sua_nghe_sai(cau) == (cau, "")


def test_nhieu_noi_tiep_luot_truoc():
    assert sua_nghe_sai("nhiêu", "lãi")[0] == "lãi suất bao nhiêu"
    assert sua_nghe_sai("bao nhiêu em", "hạn mức")[0] == "hạn mức bao nhiêu"
    assert sua_nghe_sai("nhiêu", "anh muốn vay hai trăm triệu trong ba năm để sửa nhà") == ("nhiêu", "")


def test_ghep_luot_bi_cat_doi():
    assert sua_nghe_sai("ba năm", "trả trong ờ")[0] == "trả trong ba năm"
    assert sua_nghe_sai("hai trăm triệu", "anh muốn vay khoảng ờ ờ")[0] == "anh muốn vay khoảng hai trăm triệu"
    # lượt trước đã trọn câu thì không ghép
    assert sua_nghe_sai("ba năm", "anh muốn vay hai trăm triệu") == ("ba năm", "")
    assert sua_nghe_sai("thế cần giấy tờ gì", "trả trong ờ") == ("thế cần giấy tờ gì", "")


def test_hai_lam_cua_nguoi_lan_l_n_la_hai_nam():
    ngong = ["em ơi cho anh hỏi nãi suất vay bên em nà bao nhiêu"]
    assert sua_nghe_sai("vay trong hai lăm được không", lich_su_khach=ngong)[0] \
        == "vay trong hai năm được không"
    # khách không lẫn l/n thì "hai lăm" vẫn là 25
    assert sua_nghe_sai("vay trong hai lăm được không", lich_su_khach=["lãi suất bao nhiêu"]) \
        == ("vay trong hai lăm được không", "")
    # có đơn vị theo sau thì là con số thật
    for cau in ("anh ba lăm tuổi", "vay hai lăm triệu", "một trăm lăm mươi triệu"):
        assert sua_nghe_sai(cau, lich_su_khach=ngong) == (cau, "")
