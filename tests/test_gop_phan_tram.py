"""Hai mốc phần trăm nối bằng "đến" thì chỉ đọc đơn vị MỘT lần.

Bên A báo *"đọc sai 'phần trăm'"* (bộ kiểm Lần 9, câu 5). Cho máy nhận dạng nghe
lại đúng chỗ đó:

    kịch bản   "...tối đa khoảng 70% đến 75% giá trị tài sản..."
    máy nghe   "...bảy mươi phần trăm đến bảy mươi lăm phần TRÁ TRỊ..."

Tức lần thứ hai, "trăm" và "giá" dính vào nhau thành "trá" - mất luôn cả hai
chữ. Chuẩn hoá chữ vốn ĐÚNG ("70%" -> "bảy mươi phần trăm"), lỗi ở khâu phát âm:
"phần trăm giá trị" có ba âm tiết liền nhau cùng phụ âm đầu /tr/-/gi/ nên F5
trượt.

Cách chữa cũng chính là cách người Việt nói: đọc đơn vị một lần ở cuối -
"bảy mươi đến bảy mươi lăm phần trăm". Vừa bớt một chỗ trượt, vừa tự nhiên hơn.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.pipeline.text_normalizer import normalize_for_tts


def test_khoang_phan_tram_doc_don_vi_MOT_lan():
    ra = normalize_for_tts("cho vay tối đa khoảng 70% đến 75% giá trị tài sản")
    assert ra.count("phần trăm") == 1, f"vẫn đọc hai lần: {ra}"
    assert "bảy mươi đến bảy mươi lăm phần trăm" in ra, ra


def test_giu_nguyen_khi_chi_co_MOT_moc():
    ra = normalize_for_tts("lãi suất 7.9% một năm")
    assert ra.count("phần trăm") == 1
    assert "bảy phẩy chín phần trăm" in ra, ra


def test_nhan_ca_dau_gach_va_chu_toi():
    for noi in ("đến", "tới", "-", "–"):
        ra = normalize_for_tts(f"khoảng 70% {noi} 75% giá trị")
        assert ra.count("phần trăm") == 1, f"với {noi!r}: {ra}"


def test_so_thap_phan_trong_khoang():
    ra = normalize_for_tts("từ 7.5% đến 9.9% một năm")
    assert ra.count("phần trăm") == 1, ra
    assert "bảy phẩy năm đến chín phẩy chín phần trăm" in ra, ra


def test_hai_khoang_RIENG_BIET_thi_moi_khoang_mot_lan():
    ra = normalize_for_tts("gói A 70% đến 75%, gói B 80% đến 85%")
    assert ra.count("phần trăm") == 2, ra


def test_khong_dinh_vao_so_khong_co_dau_phan_tram():
    ra = normalize_for_tts("vay 500 đến 700 triệu")
    assert "phần trăm" not in ra, ra
