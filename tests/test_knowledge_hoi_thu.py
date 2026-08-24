"""Hỏi thử tài liệu ngay tại trang Tri thức, và xem tài liệu bị cắt thành mảnh nào.

VÌ SAO CÓ. Trang Tri thức cho sửa tài liệu nhưng không cho THỬ: sửa xong muốn
biết AI có lấy đúng tài liệu không thì phải mở tab Chat gọi hẳn một lượt. Mà
`retrieve_chi_tiet` đã giữ sẵn điểm khớp, tên nguồn và cờ "mảnh bị lưới lọc bỏ"
- chỉ thiếu một đường từ giao diện gọi tới.

Xem mảnh thì lấy từ kho vector chứ KHÔNG cắt lại từ file trên đĩa: cắt lại luôn
ra kết quả đẹp kể cả khi kho còn giữ bản cũ, đúng cái bẫy mà cột "AI đã đọc"
sinh ra để cảnh báo.
"""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("fastapi")

from backend.api import knowledge as kn  # noqa: E402

VAY_TIN_CHAP = "knowledge/products/vay_tin_chap.md"
VAY_MUA_NHA = "knowledge/products/vay_mua_nha.md"


class _RagGia:
    """Chỉ dựng đúng phần trang Tri thức gọi tới, không nạp ChromaDB thật."""

    def __init__(self, chi_tiet=None, theo_nguon=None):
        self._chi_tiet = chi_tiet or []
        self._theo_nguon = theo_nguon or {}
        self.da_hoi = []

    async def retrieve_chi_tiet(self, query, top_k=3, san_pham=""):
        self.da_hoi.append((query, top_k, san_pham))
        giu = [c for c in self._chi_tiet if not c["bi_loc"]]
        return "\n---\n".join(c["doan"] for c in giu), self._chi_tiet

    def lay_theo_nguon(self, source):
        return self._theo_nguon.get(source, [])

    def dem_theo_nguon(self, source):
        return len(self._theo_nguon.get(source, []))


def _gan_rag(monkeypatch, rag):
    monkeypatch.setattr(kn, "_rag", lambda: rag)
    return rag


# --- hỏi thử -------------------------------------------------------------------

def test_hoi_thu_tra_ve_diem_khop_va_ten_tai_lieu(monkeypatch):
    """Người vận hành cần thấy AI lấy mảnh từ ĐÂU và khớp bao nhiêu."""
    _gan_rag(monkeypatch, _RagGia(chi_tiet=[
        {"doan": "Lãi suất từ 7.9%/năm", "diem": 0.82, "nguon": "vay_tin_chap.md", "bi_loc": False},
    ]))
    d = asyncio.run(kn.hoi_thu(cau_hoi="lãi suất bao nhiêu"))

    assert d["manh"][0]["nguon"] == "vay_tin_chap.md"
    assert d["manh"][0]["diem"] == 0.82
    assert d["manh"][0]["doan"] == "Lãi suất từ 7.9%/năm"


def test_hoi_thu_dem_rieng_manh_bi_luoi_loc_bo(monkeypatch):
    """Mảnh lạc sản phẩm bị loại phải đếm RIÊNG.

    Thấy mảnh vay_mua_nha bị loại khi đang tư vấn vay tín chấp thì biết lưới lọc
    đang ăn; thấy nó KHÔNG bị loại thì biết lưới đang hở và bot sắp đọc lãi suất
    sản phẩm khác cho khách.
    """
    _gan_rag(monkeypatch, _RagGia(chi_tiet=[
        {"doan": "tín chấp 7.9%", "diem": 0.8, "nguon": "vay_tin_chap.md", "bi_loc": False},
        {"doan": "mua nhà 6.5%", "diem": 0.7, "nguon": "vay_mua_nha.md", "bi_loc": True},
    ]))
    d = asyncio.run(kn.hoi_thu(cau_hoi="lãi suất", san_pham="vay tín chấp"))

    assert d["so_lay"] == 1
    assert d["so_bi_loc"] == 1


def test_hoi_thu_chuyen_tiep_san_pham_xuong_rag(monkeypatch):
    """Không chuyển sản phẩm xuống thì lưới lọc không bao giờ chạy - thử vô nghĩa."""
    rag = _gan_rag(monkeypatch, _RagGia(chi_tiet=[]))
    asyncio.run(kn.hoi_thu(cau_hoi="lãi suất", san_pham="vay tín chấp"))

    assert rag.da_hoi[0][2] == "vay tín chấp"


def test_hoi_thu_cau_rong_bao_loi_va_khong_goi_rag(monkeypatch):
    rag = _gan_rag(monkeypatch, _RagGia(chi_tiet=[]))
    d = asyncio.run(kn.hoi_thu(cau_hoi="   "))

    assert "error" in d
    assert rag.da_hoi == []


def test_hoi_thu_khong_co_rag_thi_bao_ro(monkeypatch):
    """RAG chưa nạp xong mà trả mảnh rỗng thì người dùng tưởng tài liệu sai."""
    monkeypatch.setattr(kn, "_rag", lambda: None)
    d = asyncio.run(kn.hoi_thu(cau_hoi="lãi suất"))

    assert "error" in d


# --- xem mảnh ------------------------------------------------------------------

def _rag_co_manh(monkeypatch, manh):
    """Gắn RAG giả trả `manh` cho MỌI dạng chuỗi nguồn của cùng một file."""
    p = kn._duong_dan("products", "vay_tin_chap")
    return _gan_rag(monkeypatch, _RagGia(
        theo_nguon={dang: manh for dang in kn._cac_dang_nguon(p)}))


def test_xem_manh_tra_ve_dung_thu_tu_manh(monkeypatch):
    _rag_co_manh(monkeypatch, ["mảnh một", "mảnh hai", "mảnh ba"])
    d = asyncio.run(kn.xem_manh(nhom="products", ten="vay_tin_chap"))

    assert [m["stt"] for m in d["manh"]] == [1, 2, 3]
    assert d["manh"][1]["doan"] == "mảnh hai"


def test_xem_manh_bao_chua_nap_khi_kho_trong(monkeypatch):
    """0 mảnh nghĩa là file có trên đĩa nhưng AI CHƯA đọc - phải nói thẳng."""
    _rag_co_manh(monkeypatch, [])
    d = asyncio.run(kn.xem_manh(nhom="products", ten="vay_tin_chap"))

    assert d["chua_nap"] is True


def test_xem_manh_danh_dau_manh_cat_ngang_bang(monkeypatch):
    """Bảng lãi suất bị chặt mất dòng tiêu đề là bot đọc thiếu cột."""
    _rag_co_manh(monkeypatch, [
        "| Kỳ hạn | Lãi suất |\n|---|---|\n| 12 tháng | 7.9% |",
        "| 24 tháng | 8.4% |\n| 36 tháng | 8.9% |",
    ])
    d = asyncio.run(kn.xem_manh(nhom="products", ten="vay_tin_chap"))

    assert d["manh"][0]["cat_ngang_bang"] is False
    assert d["manh"][1]["cat_ngang_bang"] is True


def test_xem_manh_danh_dau_manh_bat_dau_giua_cau(monkeypatch):
    _rag_co_manh(monkeypatch, [
        "## Điều kiện vay\n- Từ 22 tuổi",
        "tháng trở lên và không có nợ xấu tại CIC",
    ])
    d = asyncio.run(kn.xem_manh(nhom="products", ten="vay_tin_chap"))

    assert d["manh"][0]["bat_dau_giua_cau"] is False
    assert d["manh"][1]["bat_dau_giua_cau"] is True


def test_manh_mo_dau_bang_so_giua_cau_van_bi_danh_dau(monkeypatch):
    """Bắt được trên máy thật: vay_tin_chap.md cắt ngay giữa "sao kê lương 3
    tháng gần nhất", nửa sau mở đầu bằng "3 tháng gần nhất" mà không bị báo.

    Số đứng đầu KHÔNG mặc nhiên là đầu ý - chỉ khi nó là số thứ tự danh sách
    ("3." hay "3)") mới là đầu ý.
    """
    _rag_co_manh(monkeypatch, [
        "3 tháng gần nhất\n- Hợp đồng lao động",
        "3. Điều kiện vay\n- Từ 22 tuổi",
    ])
    d = asyncio.run(kn.xem_manh(nhom="products", ten="vay_tin_chap"))

    assert d["manh"][0]["bat_dau_giua_cau"] is True
    assert d["manh"][1]["bat_dau_giua_cau"] is False


def test_xem_manh_ten_khong_hop_le_thi_tu_choi(monkeypatch):
    _rag_co_manh(monkeypatch, ["gì đó"])
    d = asyncio.run(kn.xem_manh(nhom="../../etc", ten="passwd"))

    assert "error" in d


# --- soi tài liệu + mẫu ---------------------------------------------------------

def test_soi_tra_ve_ca_ket_qua_soi_lan_manh_cat_thu():
    d = asyncio.run(kn.soi(
        noi_dung="# Vay Tín Chấp\n\n- Lãi suất: từ 7.9%/năm\n- Trả 3.4 triệu",
        nhom="products", ten="vay_tin_chap"))

    assert [m["ma"] for m in d["loi"]] == ["nhieu_so_thap_phan"]
    assert "so_mo_ho" in [m["ma"] for m in d["canh_bao"]]
    assert d["so_manh"] == 1


def test_soi_chay_duoc_ca_khi_rag_chua_san_sang(monkeypatch):
    """Người vận hành soạn tài liệu ngay lúc backend đang nạp model. Soi là việc
    thuần văn bản, không được đòi kho vector."""
    monkeypatch.setattr(kn, "_rag", lambda: None)
    d = asyncio.run(kn.soi(noi_dung="# Thử\n\nNội dung", nhom="faq", ten="thu"))

    assert "error" not in d


def test_mau_tra_ve_noi_dung_cho_tung_nhom():
    d = asyncio.run(kn.lay_mau(nhom="products"))
    assert d["noi_dung"].startswith("# ")


def test_mau_nhom_khong_hop_le_thi_bao_loi():
    d = asyncio.run(kn.lay_mau(nhom="linh_tinh"))
    assert "error" in d


def test_danh_sach_kem_so_loi_cua_tung_tai_lieu(monkeypatch, tmp_path):
    """Mở trang là biết tài liệu nào đang có vấn đề, kể cả tài liệu cũ chưa ai mở."""
    (tmp_path / "products").mkdir()
    (tmp_path / "products" / "vay_tin_chap.md").write_text(
        "# Vay Tín Chấp\n\n- Lãi suất: 7.9%/năm\n- Trả 3.4 triệu", encoding="utf-8")
    monkeypatch.setattr(kn, "GOC", tmp_path)
    monkeypatch.setattr(kn, "_rag", lambda: None)

    d = asyncio.run(kn.danh_sach())
    assert d["tai_lieu"][0]["so_loi"] == 1
