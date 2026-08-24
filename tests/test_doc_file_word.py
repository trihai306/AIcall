"""Nhận thẳng file Word, khỏi bắt người dùng tự lưu thành .txt.

VÌ SAO CÓ. Tài liệu ngân hàng thật gần như luôn nằm trong Word, mà trang Tri
thức đang bắt "lưu lại thành .txt rồi tải lên" - một bước thủ công mà ai cũng
làm sai ít nhất một lần, và làm mất sạch bảng biểu.

KHÔNG dùng thư viện ngoài: .docx là file zip, `zipfile` + `ElementTree` của
Python đọc được. Máy chạy offline nên thêm phụ thuộc là thêm một thứ có thể
thiếu lúc dựng lại trên máy khác.

Bảng phải giữ được: biểu lãi suất trong Word là ca dùng chính, mà mất bảng thì
số rời khỏi tên cột và AI đọc số không biết của ai.
"""
import io
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("fastapi")

from backend.api.knowledge import _docx_sang_van_ban  # noqa: E402

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _docx(than: str) -> bytes:
    """Dựng file .docx tối thiểu - đúng thứ Word ghi ra, chỉ bỏ phần thừa."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml",
                   f'<?xml version="1.0"?><w:document {W}><w:body>{than}</w:body></w:document>')
    return buf.getvalue()


def _doan(*chu: str) -> str:
    return "".join(f"<w:p><w:r><w:t>{c}</w:t></w:r></w:p>" for c in chu)


def _o(chu: str) -> str:
    return f"<w:tc><w:p><w:r><w:t>{chu}</w:t></w:r></w:p></w:tc>"


def _hang(*o: str) -> str:
    return "<w:tr>" + "".join(_o(c) for c in o) + "</w:tr>"


def test_doc_duoc_tung_doan_van():
    ra = _docx_sang_van_ban(_docx(_doan("Vay tín chấp", "Lãi suất 7.9%/năm")))
    assert "Vay tín chấp" in ra
    assert "Lãi suất 7.9%/năm" in ra


def test_moi_doan_mot_dong():
    ra = _docx_sang_van_ban(_docx(_doan("Dòng một", "Dòng hai")))
    assert ra.splitlines()[:2] == ["Dòng một", "Dòng hai"]


def test_chu_bi_word_cat_vun_van_ghep_lai_dung():
    """Word hay tách một câu thành nhiều <w:r> (do soát chính tả, định dạng).
    Ghép sai thì chữ dính liền hoặc mất khoảng trắng."""
    than = ('<w:p><w:r><w:t>Lãi suất </w:t></w:r>'
            '<w:r><w:t>7.9%</w:t></w:r>'
            '<w:r><w:t>/năm</w:t></w:r></w:p>')
    assert _docx_sang_van_ban(_docx(than)).strip() == "Lãi suất 7.9%/năm"


def test_bang_ra_bang_markdown_co_dong_tieu_de():
    """Không có dòng `|---|` thì đó không phải bảng markdown, và RAG cắt ra là
    mất luôn tên cột."""
    than = _hang("Kỳ hạn", "Lãi suất") + _hang("12 tháng", "7.9%")
    ra = _docx_sang_van_ban(_docx("<w:tbl>" + than + "</w:tbl>"))

    dong = [d for d in ra.splitlines() if d.strip()]
    assert dong[0] == "| Kỳ hạn | Lãi suất |"
    assert set(dong[1]) <= set("|-: ")
    assert dong[2] == "| 12 tháng | 7.9% |"


def test_giu_ca_van_ban_lan_bang_dung_thu_tu():
    than = _doan("# Biểu lãi suất") + "<w:tbl>" + _hang("A", "B") + "</w:tbl>" + _doan("Ghi chú")
    dong = [d for d in _docx_sang_van_ban(_docx(than)).splitlines() if d.strip()]
    assert dong[0] == "# Biểu lãi suất"
    assert dong[-1] == "Ghi chú"


def test_file_khong_phai_docx_thi_bao_loi_ro():
    with pytest.raises(ValueError):
        _docx_sang_van_ban(b"day khong phai file zip")


def test_zip_thieu_document_xml_thi_bao_loi_ro():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("gi_do.txt", "nội dung")
    with pytest.raises(ValueError):
        _docx_sang_van_ban(buf.getvalue())


# --- nối vào đường tải lên -------------------------------------------------------

def test_tai_len_file_word_thi_luu_thanh_markdown(monkeypatch, tmp_path):
    """Người dùng kéo thẳng file Word vào, không phải tự lưu thành .txt nữa."""
    import asyncio

    from starlette.datastructures import UploadFile

    from backend.api import knowledge as kn

    monkeypatch.setattr(kn, "GOC", tmp_path)
    monkeypatch.setattr(kn, "_rag", lambda: None)

    raw = _docx(_doan("# Vay Tín Chấp", "Lãi suất 7.9%/năm"))
    tep = UploadFile(filename="bieu_lai_suat.docx", file=io.BytesIO(raw))
    d = asyncio.run(kn.upload(file=tep, nhom="products", ten="vay_tin_chap"))

    assert d.get("ok") is True
    assert "7.9%/năm" in (tmp_path / "products" / "vay_tin_chap.md").read_text(encoding="utf-8")


def test_file_word_hong_thi_bao_loi_chu_khong_luu(monkeypatch, tmp_path):
    import asyncio

    from starlette.datastructures import UploadFile

    from backend.api import knowledge as kn

    monkeypatch.setattr(kn, "GOC", tmp_path)
    monkeypatch.setattr(kn, "_rag", lambda: None)

    tep = UploadFile(filename="hong.docx", file=io.BytesIO(b"khong phai zip"))
    d = asyncio.run(kn.upload(file=tep, nhom="products", ten="hong"))

    assert "error" in d
    assert not (tmp_path / "products" / "hong.md").exists()
