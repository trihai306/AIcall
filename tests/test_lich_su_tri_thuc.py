"""Lịch sử sửa tài liệu tri thức, để hoàn tác được.

VÌ SAO CÓ. Đây là chỗ duy nhất quyết định con số bot đọc cho khách, mà ghi đè
là mất trắng bản cũ - sửa nhầm lãi suất lúc gấp thì không có đường lùi.

CHỖ ĐỂ LỊCH SỬ LÀ QUYẾT ĐỊNH AN TOÀN, không phải tiện tay: `ingest_directory`
quét `rglob("*.md")`, nên để bản cũ trong `knowledge/` là RAG nạp luôn cả chúng
và bot trả lời khách bằng lãi suất đã bị thay. Vì thế lịch sử nằm NGOÀI thư mục
tri thức.
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
    return tmp_path


def _luu(noi_dung, ten="vay_tin_chap"):
    return asyncio.run(kn.luu(nhom="products", ten=ten, noi_dung=noi_dung))


def test_lan_luu_dau_tien_khong_de_lai_ban_cu(kho):
    """Tài liệu mới thì không có gì để lùi về - đừng tạo bản rỗng."""
    _luu("# Bản đầu\n\nLãi 7.9%")
    d = asyncio.run(kn.lich_su(nhom="products", ten="vay_tin_chap"))
    assert d["ban"] == []


def test_ghi_de_thi_giu_lai_ban_cu(kho):
    _luu("# Bản một\n\nLãi 7.9%")
    _luu("# Bản hai\n\nLãi 8.5%")

    d = asyncio.run(kn.lich_su(nhom="products", ten="vay_tin_chap"))
    assert len(d["ban"]) == 1

    cu = asyncio.run(kn.lich_su_noi_dung(nhom="products", ten="vay_tin_chap",
                                         moc=d["ban"][0]["moc"]))
    assert "7.9%" in cu["noi_dung"]


def test_lich_su_khong_nam_trong_thu_muc_tri_thuc(kho):
    """Nằm trong đó là `ingest_directory` nạp cả bản cũ, bot đọc lãi suất đã thay."""
    _luu("# Bản một\n\nLãi 7.9%")
    _luu("# Bản hai\n\nLãi 8.5%")

    md_trong_tri_thuc = list((kho / "knowledge").rglob("*.md"))
    assert len(md_trong_tri_thuc) == 1
    assert "7.9%" not in md_trong_tri_thuc[0].read_text(encoding="utf-8")


def test_chi_giu_so_ban_gioi_han(kho):
    for i in range(kn.SO_BAN_GIU + 5):
        _luu(f"# Bản {i}\n\nLãi {i}.5%")
    d = asyncio.run(kn.lich_su(nhom="products", ten="vay_tin_chap"))
    assert len(d["ban"]) == kn.SO_BAN_GIU


def test_ban_moi_nhat_dung_dau_danh_sach(kho):
    _luu("# Bản một\n\nLãi 7.9%")
    _luu("# Bản hai\n\nLãi 8.5%")
    _luu("# Bản ba\n\nLãi 9.5%")

    d = asyncio.run(kn.lich_su(nhom="products", ten="vay_tin_chap"))
    dau = asyncio.run(kn.lich_su_noi_dung(nhom="products", ten="vay_tin_chap",
                                          moc=d["ban"][0]["moc"]))
    assert "8.5%" in dau["noi_dung"]


def test_khoi_phuc_dua_noi_dung_ve_ban_cu(kho):
    _luu("# Bản một\n\nLãi 7.9%")
    _luu("# Bản hai\n\nLãi 8.5%")
    d = asyncio.run(kn.lich_su(nhom="products", ten="vay_tin_chap"))

    asyncio.run(kn.khoi_phuc(nhom="products", ten="vay_tin_chap", moc=d["ban"][0]["moc"]))

    hien_tai = (kho / "knowledge" / "products" / "vay_tin_chap.md").read_text(encoding="utf-8")
    assert "7.9%" in hien_tai


def test_khoi_phuc_van_giu_lai_ban_dang_co(kho):
    """Khôi phục nhầm cũng phải lùi lại được - không thì hoàn tác thành một
    chiều và người dùng mất bản mới."""
    _luu("# Bản một\n\nLãi 7.9%")
    _luu("# Bản hai\n\nLãi 8.5%")
    d = asyncio.run(kn.lich_su(nhom="products", ten="vay_tin_chap"))
    asyncio.run(kn.khoi_phuc(nhom="products", ten="vay_tin_chap", moc=d["ban"][0]["moc"]))

    sau = asyncio.run(kn.lich_su(nhom="products", ten="vay_tin_chap"))
    moi_nhat = asyncio.run(kn.lich_su_noi_dung(nhom="products", ten="vay_tin_chap",
                                               moc=sau["ban"][0]["moc"]))
    assert "8.5%" in moi_nhat["noi_dung"]


def test_xoa_tai_lieu_van_giu_ban_cuoi(kho):
    """Lỡ tay xoá vẫn lấy lại được."""
    _luu("# Bản một\n\nLãi 7.9%")
    asyncio.run(kn.xoa(nhom="products", ten="vay_tin_chap"))

    d = asyncio.run(kn.lich_su(nhom="products", ten="vay_tin_chap"))
    assert len(d["ban"]) == 1


def test_moc_khong_hop_le_thi_tu_choi(kho):
    _luu("# Bản một\n\nLãi 7.9%")
    d = asyncio.run(kn.lich_su_noi_dung(nhom="products", ten="vay_tin_chap",
                                        moc="../../../etc/passwd"))
    assert "error" in d
