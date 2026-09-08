"""Sau khi bị khách cắt lời, lượt sau đọc nốt phần khách chưa kịp nghe."""
from backend.pipeline.session_manager import CallSession


def _phien(con_do: str, giay: float) -> CallSession:
    s = CallSession(customer_name="Khách")
    s.cau_ai_con_do = con_do
    s.giay_ai_con_do = giay
    return s


def test_khong_bi_cat_thi_khong_co_gi_de_doc_not():
    s = CallSession(customer_name="Khách")
    assert s.lay_cau_doc_not("lãi suất bao nhiêu") == ""


def test_doc_not_phan_do_roi_moi_dap_cau_moi():
    s = _phien("không cần thế chấp", 1.2)
    assert s.lay_cau_doc_not("thế còn thủ tục thì sao") == "không cần thế chấp"


def test_lay_mot_lan_roi_thoi():
    # Lượt sau nữa mà đọc lại là khách nghe hai lần cùng một câu.
    s = _phien("không cần thế chấp", 1.2)
    s.lay_cau_doc_not("thế còn thủ tục thì sao")
    assert s.lay_cau_doc_not("còn phí thì sao") == ""


def test_khach_phu_dinh_thi_bo_luon_phan_do():
    # Khách cắt VÌ AI nói lạc - đọc nốt đoạn lạc là phản tác dụng. Và phải XOÁ,
    # không để nó treo sang lượt sau nữa.
    s = _phien("không cần thế chấp", 1.2)
    assert s.lay_cau_doc_not("không, ý em là vay thế chấp") == ""
    assert s.cau_ai_con_do == ""


def test_phan_do_qua_dai_thi_bo():
    s = _phien("một đoạn rất dài", 5.0)
    assert s.lay_cau_doc_not("thế còn thủ tục thì sao") == ""
