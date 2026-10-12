"""Bảng dữ kiện đọc từ tài liệu và việc điền con số vào câu trả lời.

Bài kiểm cốt lõi là ĐỔI TÀI LIỆU: sửa một con số trong tệp rồi câu trả lời phải
đổi theo, và câu chép cứng con số cũ phải bị lộ ra. Không có danh sách sản phẩm
hay danh sách loại số liệu nào trong mã, nên có cả một sản phẩm bịa ra để chắc
rằng thêm tài liệu mới là dùng được ngay.
"""
from decimal import Decimal

import pytest

from backend.pipeline import bang_du_kien as b

VAY = """# Vay Tín Chấp

## Thông tin sản phẩm
- Lãi suất: từ 7.9%/năm
- Hạn mức: lên đến 500 triệu đồng
- Thời hạn: 12 - 60 tháng

## Ví dụ
- Ví dụ: vay 200 triệu trong 36 tháng thì trả góp khoảng 6.8 triệu mỗi tháng

## Ưu đãi hiện tại
- Tặng voucher 500.000đ khi giải ngân thành công
"""
GUI = """# Gửi Tiết Kiệm

## Thông tin sản phẩm
- Kỳ hạn: 1 - 36 tháng

## Lãi suất theo kỳ hạn
- Không kỳ hạn: lãi suất 0.5%/năm
- Kỳ hạn 36 tháng: lãi suất 6%/năm

## Rút trước hạn
Rút trước hạn thì phần tiền rút ra chỉ được hưởng lãi suất không kỳ hạn 0.5%/năm.
"""


@pytest.fixture
def goc(tmp_path):
    thu = tmp_path / "knowledge" / "products"
    thu.mkdir(parents=True)
    (thu / "vay_tin_chap.md").write_text(VAY, encoding="utf-8")
    (thu / "tiet_kiem.md").write_text(GUI, encoding="utf-8")
    b._NHO.clear()
    return str(tmp_path)


def _sua(goc, ten, cu, moi):
    p = f"{goc}/knowledge/products/{ten}.md"
    s = open(p, encoding="utf-8").read()
    assert cu in s
    open(p, "w", encoding="utf-8").write(s.replace(cu, moi))


def test_tach_so_quy_doi_don_vi():
    so = {(s.loai, s.gia_tri) for s in b.tach_so(
        "vay 500 triệu đồng, phí 400.000đ, lãi 7,9%/năm trong 5 năm, từ 22 - 60 tuổi")}
    assert so == {("tien", Decimal(500_000_000)), ("tien", Decimal(400_000)),
                  ("phan_tram", Decimal("7.9")), ("thang", Decimal(60)),
                  ("tuoi", Decimal(22)), ("tuoi", Decimal(60))}


def test_so_tran_khong_co_loai():
    assert [s.loai for s in b.tach_so("nợ nhóm 3 tại CIC, mẫu KT3")] == [""]


def test_khoa_lay_tu_nhan_cua_tai_lieu(goc):
    bang = b.bang_cua("Vay Tín Chấp", goc)
    assert bang.tim("lai_suat").gia_tri == "từ 7.9%/năm"
    assert [s.chu for s in bang.tim("thoi_han").so] == ["12 tháng", "60 tháng"]


def test_dien_tron_gia_tri_va_tung_con_so(goc):
    cau, thieu = b.dien("lãi {vay_tin_chap.lai_suat}, vay từ {vay_tin_chap.thoi_han|1s} "
                        "đến {vay_tin_chap.thoi_han|2}", goc)
    assert (cau, thieu) == ("lãi từ 7.9%/năm, vay từ 12 đến 60 tháng", [])


def test_cho_trong_khong_co_trong_tai_lieu_thi_bao_thieu(goc):
    cau, thieu = b.dien("phí {vay_tin_chap.phi_tra_no_truoc_han}", goc)
    assert thieu == ["{vay_tin_chap.phi_tra_no_truoc_han}"]


def test_doi_tai_lieu_thi_cau_tra_loi_doi_theo(goc):
    mau, doi, khong = b.goi_y_cho_trong(
        "Dạ, lãi suất từ 7.9%/năm, hạn mức lên đến 500 triệu đồng ạ.", "vay_tin_chap", goc)
    assert (doi, khong) == (2, 0)
    _sua(goc, "vay_tin_chap", "7.9%", "8.5%")
    _sua(goc, "vay_tin_chap", "500 triệu", "700 triệu")
    cau, thieu = b.dien(mau, goc)
    assert cau == "Dạ, lãi suất từ 8.5%/năm, hạn mức lên đến 700 triệu đồng ạ."
    assert not thieu


def test_cau_chep_cung_lo_ra_sau_khi_tai_lieu_doi(goc):
    cau = "Dạ, lãi suất từ 7.9%/năm ạ."
    assert b.so_lech(cau, "vay_tin_chap", goc) == []
    _sua(goc, "vay_tin_chap", "7.9%", "8.5%")
    assert [s.chu for s in b.so_lech(cau, "vay_tin_chap", goc)] == ["7.9%"]


def test_dieu_kien_khach_chon_khong_bi_doi_thanh_cho_trong(goc):
    """36 tháng là kỳ hạn khách chọn, 6% mới là giá trị của tài liệu.

    Gán "36 tháng" vào dòng "Kỳ hạn: 1 - 36 tháng" thì hôm tài liệu nâng trần
    lên 48 tháng, câu thành "gửi 48 tháng có lãi suất 6%" - bịa.
    """
    mau, doi, khong = b.goi_y_cho_trong(
        "Dạ, gửi tiết kiệm 36 tháng có lãi suất 6% mỗi năm ạ.", "tiet_kiem", goc)
    assert mau == "Dạ, gửi tiết kiệm 36 tháng có lãi suất {tiet_kiem.ky_han_36_thang|1} mỗi năm ạ."
    _sua(goc, "tiet_kiem", "1 - 36 tháng", "1 - 48 tháng")
    _sua(goc, "tiet_kiem", "lãi suất 6%", "lãi suất 6.2%")
    assert b.dien(mau, goc)[0] == "Dạ, gửi tiết kiệm 36 tháng có lãi suất 6.2% mỗi năm ạ."


def test_tai_lieu_bo_dong_thi_cho_trong_khong_dien_duoc(goc):
    mau, _, _ = b.goi_y_cho_trong(
        "Dạ, gửi 36 tháng có lãi suất 6% mỗi năm ạ.", "tiet_kiem", goc)
    _sua(goc, "tiet_kiem", "- Kỳ hạn 36 tháng: lãi suất 6%/năm\n", "")
    assert b.dien(mau, goc)[1]


def test_con_so_thuoc_hai_dong_thi_khong_doan(goc):
    """0.5% vừa là lãi không kỳ hạn vừa là lãi rút trước hạn, câu không nói rõ."""
    _, doi, khong = b.goi_y_cho_trong("Dạ, mức đó là 0.5% ạ.", "tiet_kiem", goc)
    assert (doi, khong) == (0, 1)


def test_hoa_diem_thi_xet_chu_cua_nhan(goc):
    mau, doi, khong = b.goi_y_cho_trong(
        "Dạ, gửi không kỳ hạn thì lãi suất 0.5% ạ.", "tiet_kiem", goc)
    assert (doi, khong) == (1, 0) and "{tiet_kiem.khong_ky_han|1}" in mau


def test_so_khach_neu_khong_bi_gan_vao_dong_vi_du(goc):
    """"mức 200 triệu nằm trong hạn mức": 200 triệu là số khách nêu."""
    mau, doi, khong = b.goi_y_cho_trong(
        "Dạ anh chị vay tối đa 500 triệu, mức 200 triệu nằm trong hạn mức ạ.",
        "vay_tin_chap", goc)
    assert "vi_du" not in mau and khong == 1


def test_san_pham_moi_khong_can_sua_ma(goc):
    open(f"{goc}/knowledge/products/vay_mua_xe.md", "w", encoding="utf-8").write(
        "# Vay Mua Xe\n\n## Biểu phí\n- Phí trả nợ trước hạn: 2% số tiền trả trước\n")
    assert "vay_mua_xe" in b.cac_san_pham(goc)
    assert b.dien("phí là {vay_mua_xe.phi_tra_no_truoc_han|1}", goc) == ("phí là 2%", [])


def test_phien_ban_doi_khi_tai_lieu_doi(goc):
    truoc = b.phien_ban_chung(goc)
    _sua(goc, "vay_tin_chap", "7.9%", "8.5%")
    assert b.phien_ban_chung(goc) != truoc
