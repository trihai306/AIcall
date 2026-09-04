"""Đếm xem việc gộp mảnh THẬT SỰ ăn bao nhiêu trên cuộc gọi.

VÌ SAO. Gộp mảnh là thứ bên A đã nghe 100 câu rồi chọn - nó xoá chỗ "chữ ngân"
ở giữa câu. Nhưng trên cuộc gọi, gộp chỉ xảy ra khi còn đủ thời gian
(`cho_gom_ms`), nên có lượt gộp được, có lượt không. Sổ tay ghi 25-36% từ một
lần đo tay; sau đó không có gì trong log cho biết nó còn ăn hay đã tắt ngóm.

Bản XUẤT FILE thì gộp gần 100% - nghe bản xuất rồi duyệt là duyệt nhầm.
"""
from backend.pipeline.text_chunker import ty_le_gop


def test_mot_manh_thi_khong_co_cho_noi_nao():
    # Không có chỗ nối thì không có gì để gộp - trả None chứ không phải 0%,
    # vì 0% nghĩa là "có cơ hội mà trượt", khác hẳn "không có cơ hội".
    assert ty_le_gop(1, 1) is None


def test_gop_tron_cum_thi_an_het_cho_noi():
    assert ty_le_gop(4, 1) == 1.0


def test_khong_gop_gi_thi_bang_khong():
    assert ty_le_gop(4, 4) == 0.0


def test_gop_mot_phan():
    # 4 mảnh, sinh 2 lần -> bỏ được 2 trong 3 chỗ nối.
    assert abs(ty_le_gop(4, 2) - 2 / 3) < 1e-9


def test_khong_manh_nao_thi_tra_none():
    assert ty_le_gop(0, 0) is None


def test_so_lan_sinh_vo_ly_thi_khong_bao_qua_100_phan_tram():
    # Đường lùi khi gộp hỏng có thể sinh nhiều hơn số mảnh. Thà kẹp còn hơn
    # in ra "gộp 150%" rồi người đọc log mất niềm tin vào cả bảng số.
    assert ty_le_gop(3, 9) == 0.0
