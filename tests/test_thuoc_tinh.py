"""Trích cặp (thuộc tính, giá trị) - nền của lưới chặn số sai chủ thể.

Vì sao không dùng embedding: đo 08-09-2026 trên 20 câu đối chứng, cosine cho câu
ĐÚNG 0,02-0,46 và câu BỊA 0,03-0,33 - hai dải chồng lấn, không ngưỡng nào tách
được. Embedding đo CÙNG CHỦ ĐỀ chứ không đo ĐÚNG/SAI: với nó "lãi suất 5%" và
"lãi suất 7.9%" gần như đồng nghĩa.
"""
from backend.pipeline.thuoc_tinh import THUOC_TINH_MAC_DINH, cap_trong, chuan_so


def test_chuan_so_khong_an_so_khong_cua_hang_tram():
    """`"500".rstrip("0")` cho `"5"` - đã mắc, làm tài liệu đọc ra 'hạn mức 5 triệu'."""
    assert chuan_so("500") == "500"
    assert chuan_so("7,9") == "7.9"
    assert chuan_so("7.90") == "7.9"


def test_trich_duoc_lai_suat():
    assert cap_trong("Lãi suất từ 7.9% một năm", THUOC_TINH_MAC_DINH) == [("lãi suất", "7.9", "%")]


def test_so_thap_phan_bi_tach_van_trich_dung():
    """Bản ghi lời AI có "từ 7. 9%" - không dán lại thì trích ra 9% và chặn oan."""
    assert cap_trong("Lãi suất từ 7. 9% một năm", THUOC_TINH_MAC_DINH) == [("lãi suất", "7.9", "%")]


def test_tu_khoa_nam_sau_so_van_nhan_ra():
    """"trên 70 tuổi" - từ khoá đứng SAU số."""
    assert cap_trong("Khách trên 70 tuổi vẫn vay được", THUOC_TINH_MAC_DINH) == [("tuổi", "70", "tuổi")]


def test_khong_co_tu_khoa_thi_khong_trich():
    assert cap_trong("Anh chờ em 5 phút nhé", THUOC_TINH_MAC_DINH) == []
