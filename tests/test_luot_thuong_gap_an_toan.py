"""Các lượt ngắn dễ làm LLM bịa phải có câu trả lời xác định và an toàn."""

from backend.pipeline.luot_thuong_gap import nhan_dang, tra_loi_san


def _tra(cau: str) -> str:
    ket = tra_loi_san(
        cau, bank="Ngân hàng Quân đội", agent="Lan",
        product="vay tín chấp", luot_thu=2)
    assert ket is not None
    return ket[1]


def test_hoi_nhan_vien_o_dau_khong_bia_dia_chi():
    assert nhan_dang("em ở đâu nhỉ") == "vi_tri_tu_van"
    cau = _tra("em ở đâu nhỉ")
    assert "qua điện thoại" in cau
    assert "Hà Nội" not in cau and "TP.HCM" not in cau


def test_hoi_sao_biet_ten_khong_bia_nguon_du_lieu():
    assert nhan_dang("ơ sao em biết tên anh") == "sao_biet_ten"
    cau = _tra("ơ sao em biết tên anh")
    assert "hệ thống cuộc gọi" in cau.lower()
    assert "đồng ý nhận" not in cau.lower()


def test_cau_stt_mat_chu_ten_van_khong_de_model_bia():
    assert nhan_dang("ơ sao em biết cả anh") == "sao_biet_ten"
    assert "hệ thống cuộc gọi" in _tra("ơ sao em biết cả anh").lower()


def test_cau_nghe_bi_stt_meo_van_xac_nhan_nghe_ro():
    assert nhan_dang("nghe thì anh nói không") == "nghe_ro_khong"
    assert _tra("nghe thì anh nói không") == "Dạ em nghe rõ ạ."


def test_cau_cum_khong_du_du_kien_thi_hoi_lai_thay_vi_doan():
    assert nhan_dang("tìm ra chưa") == "chua_ro_thong_tin"
    assert "thông tin nào" in _tra("tìm ra chưa").lower()

    assert nhan_dang("lâu") == "chua_ro_thoi_gian"
    assert "thời gian nào" in _tra("lâu").lower()


def test_cau_stt_meo_khong_bi_hieu_nham_la_tra_ho_so():
    cau = "em tư vấn giúp anh vẫn giúp anh còn vay bên mình"
    assert nhan_dang(cau) == "chua_ro_nhu_cau"
    dap = _tra(cau).lower()
    assert "khoản vay mới" in dap and "khoản vay hiện tại" in dap
    assert "số điện thoại" not in dap and "chuyên viên" not in dap


def test_khach_hen_tu_goi_lai_khong_hua_gui_tin_nhan():
    assert nhan_dang("được rồi mai anh gọi lại cho em nhé") == "hen_lai"
    cau = _tra("được rồi mai anh gọi lại cho em nhé")
    assert "gọi lại bên em" in cau
    assert "gửi" not in cau.lower() and "sẽ" not in cau.lower()
