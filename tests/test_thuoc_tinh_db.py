"""Bảng thuộc tính: sửa được trên trang quản lý, gieo mặc định từ code."""
import sqlite3

from backend.models.db import _SCHEMA
from backend.models.luat_kiem_db import doc_bang_sync, gieo_mac_dinh_sync
from backend.pipeline.thuoc_tinh import THUOC_TINH_MAC_DINH


def _conn():
    c = sqlite3.connect(":memory:")
    c.executescript(_SCHEMA)
    return c


def test_gieo_roi_doc_lai_ra_dung_bang_mac_dinh():
    c = _conn()
    gieo_mac_dinh_sync(c)
    assert doc_bang_sync(c) == THUOC_TINH_MAC_DINH


def test_gieo_hai_lan_khong_nhan_doi():
    c = _conn()
    gieo_mac_dinh_sync(c)
    gieo_mac_dinh_sync(c)
    assert len(doc_bang_sync(c)) == len(THUOC_TINH_MAC_DINH)


def test_gieo_lai_KHONG_ghi_de_ban_nguoi_dung_da_sua():
    """Sửa trên UI rồi thì lần khởi động sau không được xoá công của họ."""
    c = _conn()
    gieo_mac_dinh_sync(c)
    c.execute("UPDATE thuoc_tinh_kiem SET don_vi='[\"%\"]' WHERE ten='hạn mức'")
    gieo_mac_dinh_sync(c)
    assert doc_bang_sync(c)["hạn mức"]["dvi"] == ("%",)


def test_tat_mot_thuoc_tinh_thi_khong_doc_ra_nua():
    c = _conn()
    gieo_mac_dinh_sync(c)
    c.execute("UPDATE thuoc_tinh_kiem SET bat=0 WHERE ten='tuổi'")
    assert "tuổi" not in doc_bang_sync(c)
