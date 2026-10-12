"""Tài liệu đổi con số -> đáp án trong kho tự viết lại, không tắt cả bộ.

Dựng một kho nhỏ trong SQLite tạm cùng một thư mục tài liệu tạm, rồi sửa tài
liệu như người vận hành sẽ sửa ở trang Tri thức AI.
"""
import sqlite3

import pytest

from backend.pipeline import bang_du_kien as b
from backend.services import kho_theo_tai_lieu as k

TAI_LIEU = """# Vay Tín Chấp

## Thông tin sản phẩm
- Lãi suất: từ 7.9%/năm
- Hạn mức: lên đến 500 triệu đồng
- Giải ngân: trong vòng 24 giờ sau khi phê duyệt

## Ưu đãi hiện tại
- Mức ưu đãi cho khách trả lương qua ngân hàng: 7.9%/năm
"""
REL = "products/vay_tin_chap.md"
KHO = {
    "co_mau": "Dạ, lãi suất từ 7.9%/năm, hạn mức lên đến 500 triệu đồng ạ.",
    "khong_so": "Dạ, hồ sơ gồm CMND/CCCD và xác nhận thu nhập ạ.",
    # 7.9% nằm ở hai dòng của tài liệu và câu không nói rõ dòng nào -> không
    # lập mẫu, dòng này ở lại dạng chép cứng.
    "mo_ho": "Dạ, con số đó là 7.9% ạ.",
}


@pytest.fixture
def moi_truong(tmp_path):
    thu = tmp_path / "knowledge" / "products"
    thu.mkdir(parents=True)
    (thu / "vay_tin_chap.md").write_text(TAI_LIEU, encoding="utf-8")
    b._NHO.clear()
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE hoi_dap (id TEXT PRIMARY KEY, cau_dem TEXT, cau_hoi TEXT NOT NULL,
            tra_loi TEXT NOT NULL, san_pham TEXT, bat INTEGER NOT NULL DEFAULT 1,
            created_at REAL, updated_at REAL);
        CREATE TABLE answer_bank_entries (hoi_dap_id TEXT PRIMARY KEY, source_path TEXT,
            source_hash TEXT, voice_ready INTEGER NOT NULL DEFAULT 0);
    """)
    for ma, cau in KHO.items():
        conn.execute("INSERT INTO hoi_dap (id, cau_hoi, tra_loi, san_pham) VALUES (?,?,?,?)",
                     (ma, "[]", cau, "vay_tin_chap"))
        conn.execute("INSERT INTO answer_bank_entries VALUES (?,?,?,1)", (ma, REL, "cu"))
    conn.commit()
    return conn, str(tmp_path), thu / "vay_tin_chap.md"


def _cau(conn, ma):
    return conn.execute("SELECT tra_loi, bat FROM hoi_dap WHERE id=?", (ma,)).fetchone()


def test_lap_mau_khong_sua_kho(moi_truong):
    conn, goc, _ = moi_truong
    kq = k.lap_mau(conn, goc)
    assert kq["co_mau"] == 1 and kq["khong_co_so"] == 1
    assert {ma: _cau(conn, ma)[0] for ma in KHO} == KHO
    assert conn.execute("SELECT mau FROM hoi_dap_mau WHERE id='co_mau'").fetchone()[0] == (
        "Dạ, lãi suất từ {vay_tin_chap.lai_suat|1}/năm, hạn mức lên đến "
        "{vay_tin_chap.han_muc|1} ạ.")


def test_chi_doi_so_nhan_ra_dung_loai_thay_doi(moi_truong):
    conn, goc, tep = moi_truong
    k.lap_mau(conn, goc)
    assert k.chi_doi_so(conn, REL, TAI_LIEU.replace("7.9%", "8.5%"))
    assert not k.chi_doi_so(conn, REL, TAI_LIEU + "- Phí trả nợ trước hạn: 2%\n")
    assert not k.chi_doi_so(conn, "faq/faq_banking.md", TAI_LIEU)


def test_doi_lai_suat_thi_dap_an_viet_lai_va_cho_dung_tieng(moi_truong):
    conn, goc, tep = moi_truong
    k.lap_mau(conn, goc)
    tep.write_text(TAI_LIEU.replace("7.9%", "8.5%"), encoding="utf-8")
    with conn:
        kq = k.ap_dung_doi_so(conn, REL, "moi", goc)
    assert _cau(conn, "co_mau") == (
        "Dạ, lãi suất từ 8.5%/năm, hạn mức lên đến 500 triệu đồng ạ.", 1)
    assert _cau(conn, "khong_so") == (KHO["khong_so"], 1)
    # Câu chép cứng "7.9%" không có mẫu: nay lệch tài liệu nên phải tắt riêng nó.
    assert _cau(conn, "mo_ho")[1] == 0
    assert (kq["viet_lai"], kq["giu_nguyen"], kq["tat"]) == (1, 1, 1)
    assert dict(conn.execute("SELECT hoi_dap_id, voice_ready FROM answer_bank_entries")) == {
        "co_mau": 0, "khong_so": 1, "mo_ho": 1}
    assert dict(conn.execute(
        "SELECT hoi_dap_id, source_hash FROM answer_bank_entries")) == {
        "co_mau": "moi", "khong_so": "moi", "mo_ho": "cu"}


def test_khong_con_cau_nao_noi_so_cu_sau_khi_doi(moi_truong):
    conn, goc, tep = moi_truong
    k.lap_mau(conn, goc)
    tep.write_text(TAI_LIEU.replace("500 triệu", "700 triệu").replace("24 giờ", "48 giờ"),
                   encoding="utf-8")
    with conn:
        k.ap_dung_doi_so(conn, REL, "moi", goc)
    con_bat = [r[0] for r in conn.execute("SELECT tra_loi FROM hoi_dap WHERE bat=1")]
    assert con_bat and not any("500 triệu" in c for c in con_bat)
    assert all(not b.so_lech(c, "vay_tin_chap", goc) for c in con_bat)


def test_doi_hai_lan_lien_tiep(moi_truong):
    conn, goc, tep = moi_truong
    k.lap_mau(conn, goc)
    for lai in ("8.5%", "9.1%"):
        moi = TAI_LIEU.replace("7.9%", lai)
        assert k.chi_doi_so(conn, REL, moi)
        tep.write_text(moi, encoding="utf-8")
        with conn:
            k.ap_dung_doi_so(conn, REL, lai, goc)
        assert f"từ {lai}/năm" in _cau(conn, "co_mau")[0]


def test_qua_duong_that_cua_thu_vien_tu_dong(monkeypatch, tmp_path):
    """Đi trọn `prepare_sources`: đổi con số thì đáp án được giữ và viết lại.

    Đối chứng với `test_first_scan_quarantines_legacy_but_preserves_manual` bên
    test_answer_bank_learning: cùng thao tác sửa 10 -> 12 triệu, ở đó (chưa lập
    mẫu) đáp án bị cách ly; ở đây (đã lập mẫu) nó sống tiếp với con số mới.
    """
    from backend.models import db
    from backend.services import answer_bank_learning as learning

    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.execute(
        "CREATE TABLE hoi_dap (id TEXT PRIMARY KEY,cau_dem TEXT,cau_hoi TEXT NOT NULL,"
        "tra_loi TEXT NOT NULL,san_pham TEXT,bat INTEGER NOT NULL DEFAULT 1,"
        "created_at REAL,updated_at REAL)")
    monkeypatch.setattr(db, "connection", lambda: conn)
    learning._prepared_conn = None
    learning._conn()
    root = tmp_path / "knowledge"
    (root / "products").mkdir(parents=True)
    monkeypatch.setattr(learning, "_knowledge_root", lambda: root.resolve())
    b._NHO.clear()
    tep = root / "products" / "vay.md"
    tep.write_text("# Vay\n\n- Thu nhập tối thiểu: 10 triệu đồng\n", encoding="utf-8")

    docs, _ = learning.prepare_sources()
    ids = learning._replace_document(docs[0], [{
        "cau_hoi": ["Cần thu nhập bao nhiêu?"],
        "tra_loi": "Dạ thu nhập tối thiểu là 10 triệu đồng ạ.",
        "evidence": "Thu nhập tối thiểu: 10 triệu đồng"}], [])
    conn.execute("UPDATE hoi_dap SET san_pham='vay'")
    conn.execute("UPDATE answer_bank_sources SET status='done'")
    conn.commit()
    assert learning.row_is_current(ids[0]) is True
    assert k.lap_mau(conn, str(tmp_path))["co_mau"] == 1

    tep.write_text("# Vay\n\n- Thu nhập tối thiểu: 12 triệu đồng\n", encoding="utf-8")
    learning.prepare_sources()

    assert conn.execute("SELECT tra_loi, bat FROM hoi_dap WHERE id=?", (ids[0],)).fetchone() == (
        "Dạ thu nhập tối thiểu là 12 triệu đồng ạ.", 1)
    assert learning.row_is_current(ids[0]) is True

    # Đổi cả câu chữ thì vẫn đi đường cũ: cách ly, chờ soạn lại.
    tep.write_text("# Vay\n\n- Thu nhập tối thiểu: 12 triệu đồng\n- Phí hồ sơ: 1%\n",
                   encoding="utf-8")
    learning.prepare_sources()
    assert learning.row_is_current(ids[0]) is False
