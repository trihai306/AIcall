"""Khách gây tiếng động trong lúc AI nói: khi nào thì đáng dừng AI?

Luật cũ: 80ms tiếng liên tục là cắt - tiếng ho, tiếng "dạ" đế theo, tiếng AI
vọng ngược vào mic đều cắt được lời AI.
Luật mới: dừng khi khách nói CÓ NGHĨA, hoặc nói QUÁ DÀI.
"""
from backend.services.cat_loi_dieu_kien import nen_dung

NGUONG = 700.0


def test_tieng_ngan_chua_ra_chu_thi_khong_dung():
    # Tiếng ho 300ms: chưa đủ dài, chưa có phiên âm -> AI cứ nói tiếp.
    assert nen_dung(tieng_ms=300, chu_tam="", chu_ai="", nguong_ms=NGUONG) is False


def test_tieng_qua_dai_thi_dung_du_chua_co_chu():
    # Vế "quá dài": phiên âm tạm chưa về kịp (chữ về lúc 0,8-1,1s) nhưng khách
    # đã nói liên tục quá ngưỡng - đó là người đang nói thật.
    assert nen_dung(tieng_ms=800, chu_tam="", chu_ai="", nguong_ms=NGUONG) is True


def test_chu_co_nghia_thi_dung_du_tieng_con_ngan():
    # Vế "có nghĩa": khách nói "khoan" - ngắn nhưng phải dừng ngay.
    assert nen_dung(tieng_ms=400, chu_tam="khoan anh ơi", chu_ai="",
                    nguong_ms=NGUONG) is True


def test_tieng_de_thi_khong_dung_du_da_qua_nguong():
    # Lưới chặn ngược: khách "dạ vâng" đế theo trong lúc nghe, không phải cắt lời.
    assert nen_dung(tieng_ms=1200, chu_tam="dạ vâng", chu_ai="",
                    nguong_ms=NGUONG) is False


def test_chu_trung_loi_ai_dang_phat_thi_coi_la_vong():
    # Đo 05-09-2026 (scripts/do_dem_truoc.py): vọng AI 30% làm PhoWhisper chép
    # lời AI thành lời khách, CER 0,896 ở 800ms. Trùng chữ -> không phải khách.
    assert nen_dung(tieng_ms=1500,
                    chu_tam="hạn mức vay tín chấp",
                    chu_ai="dạ hạn mức vay tín chấp bên em tối đa năm trăm triệu",
                    nguong_ms=NGUONG) is False


def test_khach_noi_that_de_len_tieng_ai_van_dung():
    # Vọng chỉ tính khi chữ NẰM TRONG lời AI. Khách hỏi câu khác thì phải dừng,
    # dù AI đang nói dở.
    assert nen_dung(tieng_ms=900,
                    chu_tam="thế còn thủ tục thì sao",
                    chu_ai="dạ hạn mức vay tín chấp bên em tối đa năm trăm triệu",
                    nguong_ms=NGUONG) is True


# --- Đọc nốt phần câu cũ khách chưa nghe -------------------------------------
from backend.services.cat_loi_dieu_kien import nen_doc_not  # noqa: E402


def test_khong_con_gi_do_thi_khong_doc_not():
    assert nen_doc_not(phan_do_giay=0, cau_khach="lãi suất bao nhiêu") is False


def test_phan_do_ngan_thi_doc_not_truoc_khi_dap():
    assert nen_doc_not(phan_do_giay=2.0, cau_khach="thế còn thủ tục thì sao") is True


def test_phan_do_qua_dai_thi_bo_luon():
    # Bắt khách nghe 5 giây câu cũ trước khi được đáp là đổi một cái bực lấy
    # một cái bực khác.
    assert nen_doc_not(phan_do_giay=5.0, cau_khach="thế còn thủ tục thì sao") is False


def test_khach_phu_dinh_thi_bo_cau_cu():
    # Khách cắt lời VÌ AI đang nói lạc - đọc nốt đoạn lạc đó là phản tác dụng.
    assert nen_doc_not(phan_do_giay=2.0, cau_khach="không, ý em là vay thế chấp") is False


def test_khach_bao_khoan_thi_bo_cau_cu():
    assert nen_doc_not(phan_do_giay=2.0, cau_khach="khoan đã anh ơi") is False
