"""Khách nghe tới đâu rồi? Sổ ghi từng mảnh tiếng AI đã xếp vào hàng đợi.

Cần cho việc "đọc nốt phần dở": lúc cắt lời, `drop_pending_audio()` biết nó bỏ
bao nhiêu KHUNG, nhưng không biết bấy nhiêu khung đó là những CHỮ nào.
"""
from backend.services.so_manh_phat import SoManhPhat


def test_khong_bo_khung_nao_thi_khong_con_gi_do():
    so = SoManhPhat()
    so.them("Dạ hạn mức bên em", 50)
    assert so.con_do(so_khung_bo=0) == ""


def test_bo_tron_manh_cuoi_thi_manh_do_la_phan_chua_nghe():
    so = SoManhPhat()
    so.them("Dạ hạn mức bên em", 50)
    so.them("tối đa năm trăm triệu", 40)
    assert so.con_do(so_khung_bo=40) == "tối đa năm trăm triệu"


def test_bo_nhieu_manh_thi_ghep_theo_dung_thu_tu():
    so = SoManhPhat()
    so.them("Dạ hạn mức bên em", 50)
    so.them("tối đa năm trăm triệu", 40)
    so.them("không cần thế chấp", 30)
    assert so.con_do(so_khung_bo=70) == "tối đa năm trăm triệu không cần thế chấp"


def test_bo_sot_vai_khung_cuoi_thi_coi_nhu_da_nghe_tron():
    # Bỏ 5/40 khung cuối = khách đã nghe 87% mảnh đó. Đọc lại cả mảnh là bắt
    # khách nghe lại thứ họ vừa nghe.
    so = SoManhPhat()
    so.them("Dạ hạn mức bên em", 50)
    so.them("tối đa năm trăm triệu", 40)
    assert so.con_do(so_khung_bo=5) == ""


def test_bo_qua_nua_manh_thi_doc_lai_ca_manh():
    # Nghe được "tối đa năm" rồi đứt: ý chưa trọn, phải đọc lại từ đầu mảnh.
    so = SoManhPhat()
    so.them("tối đa năm trăm triệu", 40)
    assert so.con_do(so_khung_bo=25) == "tối đa năm trăm triệu"


def test_do_dai_phan_chua_nghe_tinh_ra_giay():
    # Luật chặn đọc-nốt cần con số này để so với trần 3 giây.
    so = SoManhPhat()
    so.them("tối đa năm trăm triệu", 40)      # 40 khung x 20ms = 0,8s
    assert so.giay_con_do(so_khung_bo=40) == 0.8


def test_luot_moi_thi_so_sach_lai():
    so = SoManhPhat()
    so.them("câu của lượt trước", 50)
    so.xoa()
    assert so.con_do(so_khung_bo=50) == ""


def test_hai_manh_trung_chu_van_tinh_dung_do_dai():
    # "dạ vâng" xuất hiện hai lần trong một lượt: tra ngược theo chữ thì cộng
    # nhầm cả mảnh đã nghe rồi.
    so = SoManhPhat()
    so.them("dạ vâng", 30)
    so.them("hạn mức bên em", 50)
    so.them("dạ vâng", 30)
    assert so.giay_con_do(so_khung_bo=30) == 0.6


def test_ghep_duoc_toan_bo_loi_ai_da_xep_de_so_vong():
    # Lưới chặn vọng cần biết AI đang nói gì để đối chiếu với chữ nghe được.
    so = SoManhPhat()
    so.them("Dạ hạn mức bên em", 50)
    so.them("tối đa năm trăm triệu", 40)
    assert so.chu_da_xep() == "Dạ hạn mức bên em tối đa năm trăm triệu"
