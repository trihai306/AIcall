"""Tự đặt nhóm tài liệu, và tìm được trong NỘI DUNG chứ không chỉ tên file.

VÌ SAO CÓ.
- Nhóm đang cứng ba loại trong mã nguồn. Ngân hàng nào cũng có loại tài liệu
  riêng (biểu phí, quy trình, mẫu biểu) mà muốn thêm thì phải sửa code.
- Ô tìm chỉ lọc theo TÊN FILE. Người vận hành nhớ "cái tài liệu nói về CIC" chứ
  không nhớ nó tên gì, nên tìm theo tên là tìm trượt.

`products` giữ nguyên ý nghĩa đặc biệt: `RAGService._mat_na_loc` chỉ lọc mảnh
nằm trong thư mục đó. Thêm nhóm mới KHÔNG được đụng tới điều này.
"""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("fastapi")

from backend.api import knowledge as kn  # noqa: E402


@pytest.fixture()
def kho(monkeypatch, tmp_path):
    monkeypatch.setattr(kn, "GOC", tmp_path / "knowledge")
    monkeypatch.setattr(kn, "GOC_LICH_SU", tmp_path / "lich_su")
    monkeypatch.setattr(kn, "_rag", lambda: None)
    (tmp_path / "knowledge" / "products").mkdir(parents=True)
    return tmp_path / "knowledge"


# --- nhóm tự đặt ----------------------------------------------------------------

def test_them_nhom_moi(kho):
    d = asyncio.run(kn.them_nhom(ten="bieu_phi"))
    assert d["ok"] is True
    assert (kho / "bieu_phi").is_dir()


def test_nhom_moi_hien_trong_danh_sach(kho):
    asyncio.run(kn.them_nhom(ten="Biểu phí dịch vụ"))
    d = asyncio.run(kn.danh_sach())
    assert "bieu_phi_dich_vu" in d["nhom"]


def test_luu_duoc_tai_lieu_vao_nhom_moi(kho):
    asyncio.run(kn.them_nhom(ten="bieu_phi"))
    d = asyncio.run(kn.luu(nhom="bieu_phi", ten="phi_chuyen_tien",
                           noi_dung="# Phí chuyển tiền\n\nMiễn phí nội bộ"))
    assert d.get("ok") is True
    assert (kho / "bieu_phi" / "phi_chuyen_tien.md").exists()


def test_ba_nhom_goc_luon_con(kho):
    """Xoá mất `products` là lưới lọc sản phẩm hết chỗ bám."""
    d = asyncio.run(kn.danh_sach())
    for goc in ("products", "faq", "chinh_sach"):
        assert goc in d["nhom"]


def test_ten_nhom_bay_bi_tu_choi(kho):
    d = asyncio.run(kn.them_nhom(ten="../../etc"))
    assert "error" in d
    assert not (kho.parent / "etc").exists()


def test_them_nhom_da_co_thi_bao(kho):
    d = asyncio.run(kn.them_nhom(ten="products"))
    assert "error" in d


def test_thu_muc_an_khong_thanh_nhom(kho):
    """Thư mục ẩn là chỗ hệ thống dùng, không phải nhóm tài liệu."""
    (kho / ".tam").mkdir()
    d = asyncio.run(kn.danh_sach())
    assert ".tam" not in d["nhom"]


def test_ten_co_dau_thanh_chu_khong_dau_chu_khong_bi_bam(kho):
    """"Biểu phí dịch vụ" phải ra "bieu_phi_dich_vu", không phải "bi_u_ph_d_ch_v".

    Băm mất chữ thì tên file vô nghĩa, và với nhóm `products` thì lưới lọc sản
    phẩm neo theo tên file cũng hỏng theo.
    """
    assert kn._ten_an_toan("Vay Tín Chấp") == "Vay_Tin_Chap"
    assert kn._ten_an_toan("biểu phí dịch vụ") == "bieu_phi_dich_vu"


def test_ten_giu_nguyen_khi_von_da_khong_dau(kho):
    assert kn._ten_an_toan("vay_tin_chap.md") == "vay_tin_chap"


# --- tìm trong nội dung ----------------------------------------------------------

def _dung_kho(kho):
    (kho / "faq").mkdir(exist_ok=True)
    (kho / "products" / "vay_tin_chap.md").write_text(
        "# Vay Tín Chấp\n\nKhông có nợ xấu tại CIC\nLãi suất 7.9%", encoding="utf-8")
    (kho / "faq" / "hoi_dap.md").write_text(
        "# Hỏi đáp\n\nThẻ tín dụng miễn lãi 55 ngày", encoding="utf-8")


def test_tim_thay_theo_noi_dung(kho):
    _dung_kho(kho)
    d = asyncio.run(kn.tim(q="CIC"))
    assert [t["ten"] for t in d["ket_qua"]] == ["vay_tin_chap"]


def test_ket_qua_kem_doan_trich_de_biet_khop_o_dau(kho):
    _dung_kho(kho)
    d = asyncio.run(kn.tim(q="miễn lãi"))
    assert "miễn lãi" in d["ket_qua"][0]["trich"]


def test_go_khong_dau_thi_trich_van_dung_cho_khop(kho):
    """Tìm ra tài liệu mà đoạn trích lại là đầu file thì vẫn phải mở ra dò tay.

    Bắt được trên máy thật: gõ "no xau" ra đúng tài liệu, nhưng trích hiện
    "# Vay Mua Nhà - Mua Bất Động Sản ## Thông tin..." vì vị trí khớp tính trên
    chuỗi đã bỏ dấu không ánh xạ được về chuỗi gốc.
    """
    # Tài liệu phải ĐỦ DÀI và từ khoá nằm cuối: tài liệu ngắn thì trích từ đầu
    # cũng trùm cả từ khoá, và test pass kể cả khi code sai.
    (kho / "products" / "dai.md").write_text(
        "# Vay Tín Chấp\n\n" + "Điều kiện chung áp dụng cho mọi khách hàng. " * 12
        + "\n\nKhách không được có nợ xấu tại CIC.", encoding="utf-8")

    d = asyncio.run(kn.tim(q="no xau"))
    trich = next(k["trich"] for k in d["ket_qua"] if k["ten"] == "dai")
    assert "nợ xấu" in trich


def test_go_khong_dau_van_tim_ra(kho):
    """Người vận hành gõ nhanh thì không bỏ dấu - tìm trượt là bỏ cuộc luôn."""
    _dung_kho(kho)
    d = asyncio.run(kn.tim(q="no xau"))
    assert [t["ten"] for t in d["ket_qua"]] == ["vay_tin_chap"]


def test_tim_ca_theo_ten_file(kho):
    _dung_kho(kho)
    d = asyncio.run(kn.tim(q="hoi_dap"))
    assert [t["ten"] for t in d["ket_qua"]] == ["hoi_dap"]


def test_tu_khoa_rong_thi_khong_tra_gi(kho):
    _dung_kho(kho)
    assert asyncio.run(kn.tim(q="  "))["ket_qua"] == []
