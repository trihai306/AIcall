"""Đọc phương án vay từ sổ dữ kiện, không để model chọn lại con số cũ."""

from pathlib import Path

import pytest

from backend.pipeline.tra_loi_khoan_vay import tra_loi


ROOT = Path(__file__).resolve().parents[1]
TIN_CHAP = (ROOT / "knowledge/products/vay_tin_chap.md").read_text(encoding="utf-8")
MUA_NHA = (ROOT / "knowledge/products/vay_mua_nha.md").read_text(encoding="utf-8")


def users(*contents: str) -> list[dict]:
    return [{"role": "user", "content": content} for content in contents]


def test_doc_lai_dung_so_tien_va_thoi_han_hien_tai_khong_tra_apr():
    history = users("Anh cần vay 450 triệu trong 36 tháng")

    code, answer = tra_loi(
        "Em đọc lại đúng số tiền và thời hạn hiện tại giúp anh chị", TIN_CHAP,
        history=history,
    )

    assert code == "nhac_lai_nhu_cau"
    assert "450 triệu đồng" in answer and "36 tháng" in answer
    assert "7.9%" not in answer and "lãi suất" not in answer


def test_phuong_an_sau_huy_va_xac_nhan_lai_khong_song_lai_so_cu():
    history = users(
        "Anh vay 450 triệu trong 24 tháng",
        "Anh không vay nữa",
        "Giờ anh chốt vay 500 triệu trong 36 tháng",
    )

    code, answer = tra_loi(
        "Nhắc lại phương án hiện tại, đừng lấy con số cũ", TIN_CHAP,
        history=history,
    )

    assert code == "nhac_lai_nhu_cau"
    assert "500 triệu đồng" in answer and "36 tháng" in answer
    assert "450 triệu" not in answer and "24 tháng" not in answer


def test_phuong_an_mua_nha_sau_sua_dung_tran_va_ky_han_cua_nguon():
    history = users(
        "Tôi muốn vay 6 tỷ trong 180 tháng",
        "Sửa lại thành 4 tỷ trong 240 tháng",
    )

    code, answer = tra_loi(
        "Đọc lại phương án mới và không dùng phương án ban đầu", MUA_NHA,
        history=history,
    )

    assert code == "nhac_lai_nhu_cau"
    assert "4 tỷ đồng" in answer and "240 tháng" in answer
    assert "6 tỷ" not in answer and "180 tháng" not in answer
    assert "nằm trong phạm vi sản phẩm" in answer
    assert "vượt hạn mức" not in answer
    assert "chưa phải kết quả phê duyệt" in answer


def test_phuong_an_ngoai_gioi_han_chi_neu_gioi_han_co_trong_nguon():
    history = users("Tôi muốn vay 700 triệu trong 72 tháng")

    code, answer = tra_loi("Nhắc lại phương án hiện tại", TIN_CHAP, history=history)

    assert code == "nhac_lai_nhu_cau"
    assert "700 triệu đồng" in answer and "72 tháng" in answer
    assert "vượt hạn mức tối đa 500 triệu đồng" in answer
    assert "ngoài khung 12 đến 60 tháng" in answer
    assert "được duyệt" not in answer


def test_phuong_an_da_huy_khong_doc_lai_so_truoc_do():
    history = users("Tôi vay 300 triệu trong 24 tháng", "Thôi không vay nữa")

    code, answer = tra_loi("Nhắc lại phương án hiện tại", TIN_CHAP, history=history)

    assert code == "nhac_lai_nhu_cau_chua_co"
    assert "đã được rút lại" in answer
    assert "300 triệu" not in answer and "24 tháng" not in answer


@pytest.mark.parametrize(
    "history, missing",
    [
        ([], ("số tiền muốn vay", "thời hạn vay")),
        (users("Tôi vay 300 triệu trong 24 tháng", "Tôi chưa chốt số tiền"),
         ("số tiền",)),
    ],
)
def test_phuong_an_chua_ro_hoi_dung_phan_thieu_khong_goi_so_cu(history, missing):
    code, answer = tra_loi("Đọc lại phương án hiện tại", TIN_CHAP, history=history)

    assert code in ("nhac_lai_nhu_cau", "nhac_lai_nhu_cau_chua_ro")
    assert all(field in answer for field in missing)
    if history:
        assert "300 triệu" not in answer


@pytest.mark.parametrize(
    "question, expected_code",
    [
        ("Nhắc lại lãi suất giúp tôi", "lai_suat_san_pham"),
        ("Nhắc lại phí giúp tôi", "xac_nhan_loai_phi"),
    ],
)
def test_nhac_lai_lai_suat_hoac_phi_khong_bi_coi_la_doc_phuong_an(
        question, expected_code):
    history = users("Tôi vay 100 triệu trong 24 tháng")

    code, answer = tra_loi(question, TIN_CHAP, history=history)

    assert code == expected_code
    assert "100 triệu" not in answer and "24 tháng" not in answer
    assert "số tiền muốn vay" not in answer and "thời hạn vay" not in answer


def test_so_khoan_vay_voi_dung_thu_nhap_rieng_da_noi():
    history = users(
        "Thu nhập của tôi là 12 triệu một tháng",
        "Tôi vay 100 triệu trong 24 tháng",
    )

    code, answer = tra_loi(
        "So khoản vay với đúng thu nhập của tôi xem có quá sức không", TIN_CHAP,
        history=history,
    )

    assert code == "can_nhac_kha_nang_tra"
    assert "tháng đầu khoảng 4,8 triệu đồng" in answer
    assert "thấp hơn mức thu nhập 12 triệu đồng" in answer
    assert "mức thu nhập 5 triệu đồng" not in answer
    assert "chưa đủ để kết luận" in answer and "được duyệt" in answer


def test_so_voi_thu_nhap_cua_toi_khong_dung_thu_nhap_chung_ho_gia_dinh():
    history = users(
        "Thu nhập hai vợ chồng tôi là 30 triệu một tháng",
        "Tôi vay 100 triệu trong 24 tháng",
    )

    code, answer = tra_loi(
        "Đối chiếu khoản vay với thu nhập của tôi", TIN_CHAP, history=history)

    assert code == "can_nhac_kha_nang_tra"
    assert "thu nhập chung của hộ gia đình" in answer
    assert "thu nhập mỗi tháng của chính người trả khoản vay" in answer
    assert "tháng đầu khoảng" not in answer


def test_so_nguoi_khac_trong_cau_doc_lai_khong_thanh_phuong_an_moi():
    history = users("Tôi vay 450 triệu trong 36 tháng")

    code, answer = tra_loi(
        "Nhắc lại phương án hiện tại, không phải 200 triệu 12 tháng của bạn tôi",
        TIN_CHAP,
        history=history,
    )

    assert code == "nhac_lai_nhu_cau"
    assert "450 triệu đồng" in answer and "36 tháng" in answer
    assert "200 triệu" not in answer and "12 tháng" not in answer


def test_thu_nhap_nguoi_khac_khong_ghi_de_thu_nhap_rieng_khi_so_sanh():
    history = users(
        "Thu nhập của tôi là 12 triệu một tháng",
        "Bạn tôi lương 30 triệu một tháng",
        "Tôi vay 100 triệu trong 24 tháng",
    )

    code, answer = tra_loi(
        "So khoản vay với đúng thu nhập của tôi", TIN_CHAP, history=history)

    assert code == "can_nhac_kha_nang_tra"
    assert "12 triệu đồng" in answer and "30 triệu đồng" not in answer
