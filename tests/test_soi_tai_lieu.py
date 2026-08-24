"""Soi tài liệu tri thức trước khi lưu.

VÌ SAO CÓ. Tài liệu ở đây quyết định mọi con số bot đọc cho khách, nhưng viết
sai cách thì KHÔNG có gì báo: bot vẫn trả lời trôi chảy, chỉ là trả lời bằng số
của sản phẩm khác hoặc số không ai kiểm được. Dataset train đã có `dataset_rules`
soi theo luật; tri thức thì chưa có gì.

Luật nặng nhất là số thập phân: `chan_so_sai` - hàng rào cuối cùng chặn mô hình
đọc sai số - CHỈ chạy khi tài liệu có đúng MỘT số thập phân. Đo ngày 24/08/2026:
cả bốn tài liệu đang chạy đều có 0, 3 hoặc 5 số, nên hàng rào đó đang tắt hoàn
toàn mà không ai biết.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("chromadb")

from backend.core.knowledge_rules import soi_manh, soi_tai_lieu  # noqa: E402

TIEU_DE = "# Vay Tín Chấp Cá Nhân\n\n"


def _ma(muc):
    return [m["ma"] for m in muc]


def _soi(than, ten="vay_tin_chap", nhom="products"):
    return soi_tai_lieu(TIEU_DE + than, nhom=nhom, ten=ten)


# --- số thập phân: hàng rào chan_so_sai ----------------------------------------

def test_nhieu_so_thap_phan_la_loi():
    d = _soi("- Lãi suất: 7.9%/năm\n- Vay 100 triệu: trả 3.4 triệu mỗi tháng")
    assert "nhieu_so_thap_phan" in _ma(d["loi"])


def test_dung_mot_so_thap_phan_thi_khong_bao():
    """Đúng một số là hàng rào chạy được - đây là trạng thái nên hướng tới."""
    d = _soi("- Lãi suất: 7.9%/năm\n- Hạn mức: 500 triệu đồng")
    assert "nhieu_so_thap_phan" not in _ma(d["loi"])


def test_phan_cach_nghin_khong_bi_dem_nham_la_thap_phan():
    """`500.000` là phân cách nghìn. Đếm nhầm thì báo lỗi ma và người dùng mất
    tin vào bộ soi - phải dùng chính hàm mà lưới chặn số đang dùng."""
    d = _soi("- Lãi suất: 7.9%/năm\n- Tặng voucher 500.000đ")
    assert "nhieu_so_thap_phan" not in _ma(d["loi"])


def test_bao_ro_nhung_so_nao_gay_ra_loi():
    """Chỉ nói 'có nhiều số' thì người dùng không biết bỏ số nào."""
    d = _soi("- Lãi suất: 7.9%/năm\n- Trả 3.4 triệu")
    chu = next(m["chu"] for m in d["loi"] if m["ma"] == "nhieu_so_thap_phan")
    assert "7.9" in chu and "3.4" in chu


# --- dữ liệu mẫu ----------------------------------------------------------------

def test_con_ten_ngan_hang_mau_la_loi():
    d = _soi("Ngân hàng ABC xin trân trọng thông báo lãi suất 7.9%")
    assert "du_lieu_mau" in _ma(d["loi"])


# --- cấu trúc -------------------------------------------------------------------

def test_thieu_tieu_de_dau_file_bi_canh_bao():
    """Mảnh đầu không mang tên sản phẩm thì AI đọc số mà không biết của ai."""
    d = soi_tai_lieu("- Lãi suất: 7.9%/năm", nhom="products", ten="vay_tin_chap")
    assert "thieu_tieu_de" in _ma(d["canh_bao"])


def test_ten_file_khong_khop_tieu_de_bi_canh_bao():
    """Lưới lọc sản phẩm neo theo TÊN FILE (`_ma_san_pham`), đặt tên linh tinh
    là lọc không bao giờ ăn."""
    d = soi_tai_lieu("# Vay Tín Chấp Cá Nhân\n\n- Lãi suất: 7.9%/năm",
                     nhom="products", ten="sanpham1")
    assert "ten_khong_khop" in _ma(d["canh_bao"])


def test_ten_file_khop_tieu_de_co_dau_thi_khong_bao():
    d = _soi("- Lãi suất: 7.9%/năm")
    assert "ten_khong_khop" not in _ma(d["canh_bao"])


def test_chi_soi_ten_voi_nhom_san_pham():
    """FAQ và chính sách không bị lưới lọc sản phẩm đụng tới."""
    d = soi_tai_lieu("# Câu hỏi thường gặp\n\nNội dung", nhom="faq", ten="hoi_dap_chung")
    assert "ten_khong_khop" not in _ma(d["canh_bao"])


def test_so_mo_ho_bi_canh_bao():
    d = _soi("- Lãi suất: từ 7.9%/năm")
    assert "so_mo_ho" in _ma(d["canh_bao"])


def test_so_ro_rang_thi_khong_bao():
    d = _soi("- Lãi suất: 7.9%/năm cố định")
    assert "so_mo_ho" not in _ma(d["canh_bao"])


def test_moi_muc_deu_co_goi_y_sua():
    """Báo lỗi mà không nói sửa thế nào thì người dùng đứng im."""
    d = _soi("- Lãi suất: từ 7.9%/năm\n- Trả 3.4 triệu")
    for m in d["loi"] + d["canh_bao"]:
        assert m.get("goi_y"), f"thiếu gợi ý: {m['ma']}"


# --- cắt thử --------------------------------------------------------------------

def test_soi_manh_bao_bang_mat_tieu_de():
    """Bảng dài bị cắt: nửa sau mất tên cột, AI đọc số mà không biết cột nào."""
    dong = ["| Kỳ hạn | Lãi suất |", "|---|---|"]
    dong += [f"| {i} tháng | {6 + i * 0.1:.1f}% |" for i in range(1, 40)]
    manh = soi_manh("# Biểu lãi suất\n\n" + "\n".join(dong))

    assert len(manh) > 1
    assert manh[0]["cat_ngang_bang"] is False
    assert any(m["cat_ngang_bang"] for m in manh[1:])


def test_soi_manh_tai_lieu_ngan_chi_ra_mot_manh():
    manh = soi_manh("# Ngắn\n\nMột dòng thôi.")
    assert len(manh) == 1
    assert manh[0]["stt"] == 1


# --- mẫu cấu trúc ---------------------------------------------------------------

def test_moi_nhom_deu_co_mau():
    from backend.core.knowledge_rules import MAU
    assert set(MAU) == {"products", "faq", "chinh_sach"}


def test_mau_tu_no_phai_sach_loi():
    """Mẫu vi phạm chính luật mình dạy thì người dùng chép về là mắc lỗi ngay.

    Ràng buộc thật: mẫu sản phẩm chỉ được mang MỘT số thập phân, vì đó chính là
    điều kiện để hàng rào `chan_so_sai` chạy.
    """
    from backend.core.knowledge_rules import MAU
    for nhom, noi_dung in MAU.items():
        d = soi_tai_lieu(noi_dung, nhom=nhom, ten="mau_thu")
        assert not d["loi"], f"mẫu {nhom} có lỗi: {d['loi']}"


def test_mau_san_pham_khong_bi_cat_manh_hong():
    """Mẫu dài quá mức cắt là dạy người dùng viết tài liệu sẽ bị chặt giữa ý."""
    from backend.core.knowledge_rules import MAU
    manh = soi_manh(MAU["products"])
    assert not any(m["cat_ngang_bang"] or m["bat_dau_giua_cau"] for m in manh)
