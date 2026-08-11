"""Kiểm kho câu thật trong data/fillers.json - bắt lỗi lúc soạn câu."""
import sqlite3
from backend.services.filler_store import DUONG_DAN_MAC_DINH, do_json_vao_db, nap_tu_db

_DDL = """
CREATE TABLE tinh_huong (
  id TEXT PRIMARY KEY, ten TEXT NOT NULL, vi_du TEXT NOT NULL,
  tu_khoa TEXT, mo_dau TEXT, speed REAL,
  bat INTEGER NOT NULL DEFAULT 1, created_at REAL, updated_at REAL);
CREATE TABLE cau_duoi (
  id TEXT PRIMARY KEY, text TEXT NOT NULL,
  hop_cau_hoi INTEGER NOT NULL DEFAULT 1,
  bat INTEGER NOT NULL DEFAULT 1, created_at REAL, updated_at REAL);
"""


def _kho():
    c = sqlite3.connect(":memory:")
    c.executescript(_DDL)
    do_json_vao_db(c, DUONG_DAN_MAC_DINH)
    return nap_tu_db(c)


def test_kho_that_nap_duoc():
    kho = _kho()
    assert len(kho.duoi) >= 28


def test_du_cau_ngan_va_cau_dai():
    # Xấp xỉ theo số ký tự, KHÔNG phải bảo đảm về mili giây: độ dài thật đo
    # lúc dựng tiếng và khác nhau theo giọng. Kiểm ba khoảng ký tự để bắt lỗi
    # soạn thiếu nguyên một rổ. Số ms thật kiểm bằng scripts/do_cau_dem.py.
    cau = _kho().duoi
    assert sum(1 for c in cau if len(c.text) <= 20) >= 8
    assert sum(1 for c in cau if 20 < len(c.text) < 55) >= 8
    assert sum(1 for c in cau if len(c.text) >= 55) >= 10
