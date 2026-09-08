"""Khách nói KHOẢNG ("ba bốn trăm") thì lưới chặn số phải hiểu là 300 hoặc 400.

Cuộc gọi thật 1e8bd9de (07-09-2026, 17:42). Khách hỏi một câu hoàn toàn hợp lệ và
nhận lại đúng hai chữ:

    khách: ờ anh muốn vay ba bốn trăm được không
    CHẶN TIỀN SAI: 400 triệu -> thay cả câu (không có căn cứ trong tài liệu)
    AI   : Vâng ạ.

Rồi khách phải "a lô" hai lần vì tưởng máy chết.

GỐC: `_chu_thanh_so` CỘNG DỒN các chữ số rồi mới nhân bội số:

    "ba"  -> hien = 3
    "bốn" -> hien = 3 + 4 = 7
    "trăm"-> hien = 7 * 100 = 700

Nên "ba bốn trăm" ra 700. Người Việt nói vậy là chỉ một KHOẢNG 300-400, và AI
hiểu đúng (chọn 400) - chính LƯỚI hiểu sai rồi chặn con số của chính khách.

Lưới đã có sẵn luật "khách tự nói thì không chặn" (`chan_tien_sai(khach_noi=...)`)
nhưng nó mù với cách nói này. Kiểu nói rất phổ biến: "một hai trăm", "năm sáu
chục", "ba bốn tháng".

CHỖ SỬA là `_so_tran_trong`, và chú thích sẵn có của nó nói đúng vì sao được
phép nới: hàm này CHỈ đọc lời KHÁCH, không đọc chữ AI sinh ra. Thêm cách hiểu chỉ
làm lưới rộng ra - không thể khiến nó chặn nhầm thêm.
"""
from backend.pipeline.text_normalizer import _so_tran_trong, chan_tien_sai

KHACH = "ờ anh muốn vay ba bốn trăm được không"


def test_ba_bon_tram_la_300_hoac_400():
    ra = _so_tran_trong(KHACH)
    assert 300 in ra and 400 in ra, f"đọc ra {sorted(ra)}"


def test_cac_cach_noi_khoang_khac():
    assert {100, 200} <= _so_tran_trong("anh vay một hai trăm thôi")
    assert {50, 60} <= _so_tran_trong("chừng năm sáu chục triệu")
    assert {3, 4} <= _so_tran_trong("vay trong ba bốn tháng")


def test_khong_pha_cach_doc_so_binh_thuong():
    """Số ghép thật vẫn phải đọc đúng - đây là chỗ dễ làm hỏng nhất."""
    assert 500 in _so_tran_trong("anh vay năm trăm")
    assert 24 in _so_tran_trong("trong hai mươi tư tháng")
    assert 120 in _so_tran_trong("khoảng một trăm hai mươi")
    assert 15 in _so_tran_trong("mười lăm triệu")


# Tài liệu thật của lượt đó (công cụ tra_thong_tin_san_pham trả về FAQ + sản phẩm).
# BẮT BUỘC phải có: nhánh nới theo lời khách bị khoá sau `if tran:`, mà `tran` là
# số tiền lớn nhất trong tài liệu. Truyền tai_lieu="" thì nhánh đó không chạy và
# test đo nhầm một đường khác - tôi đã mắc đúng lỗi này khi viết bản đầu.
TAI_LIEU = "## Hạn mức\n- Hạn mức: lên đến 500 triệu đồng"


def test_khong_chan_con_so_khach_vua_noi():
    """Ca thật của cuộc 1e8bd9de: AI đáp 400 triệu sau khi khách nói 'ba bốn trăm'."""
    cau = "Dạ với nhu cầu bốn trăm triệu thì bên em hỗ trợ được ạ."
    ra, ly_do = chan_tien_sai(cau, tai_lieu=TAI_LIEU, khach_noi=KHACH)
    assert ly_do is None, f"chặn nhầm số của chính khách: {ly_do}"
    assert ra == cau


def test_van_chan_so_khach_KHONG_he_noi():
    """Nới cho khoảng không được biến lưới thành vô dụng."""
    cau = "Dạ bên em cho vay tới hai tỷ đồng ạ."
    _, ly_do = chan_tien_sai(cau, tai_lieu=TAI_LIEU, khach_noi=KHACH)
    assert ly_do, "2 tỷ không ai nêu ra mà vẫn lọt"


def test_van_chan_so_LECH_voi_cai_khach_noi():
    """Khoá #1 của chỗ nới: phải ĐÚNG con số khách nêu, không được xê dịch."""
    cau = "Dạ với nhu cầu bốn trăm năm mươi triệu thì bên em hỗ trợ ạ."
    _, ly_do = chan_tien_sai(cau, tai_lieu=TAI_LIEU, khach_noi=KHACH)
    assert ly_do, "450 khách không nói mà vẫn lọt"
