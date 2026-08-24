"""Nút "Sinh mẫu train từ tài liệu" trên trang Training LLM.

Chạy qua JobRunner như mọi job khác, để có sẵn log dòng-theo-dòng, huỷ giữa
chừng và timeout - sinh vài trăm mẫu bằng model 7B mất nhiều phút, chạy thẳng
trong request là treo trình duyệt rồi đứt.
"""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("fastapi")

from backend.api import training as tr  # noqa: E402


class _RunnerGia:
    def __init__(self, ban=False):
        self._ban = ban
        self.da_chay = None

    def is_busy(self):
        return self._ban

    @property
    def running_job_id(self):
        return "job_cu" if self._ban else None

    def start(self, component, steps, label):
        self.da_chay = (component, steps, label)

        class _Job:
            def to_dict(self_inner):
                return {"id": "job_moi", "component": component, "label": label}
        return _Job()


def _co_tai_lieu(monkeypatch, tmp_path, co=True):
    if co:
        (tmp_path / "products").mkdir()
        (tmp_path / "products" / "vay.md").write_text("# Vay\n\nLãi 7.9%", encoding="utf-8")
    monkeypatch.setattr(tr, "THU_MUC_TRI_THUC", tmp_path)


def test_tra_ve_job_khi_may_dang_ranh(monkeypatch, tmp_path):
    _co_tai_lieu(monkeypatch, tmp_path)
    r = _RunnerGia()
    monkeypatch.setattr(tr, "runner", r)

    d = asyncio.run(tr.sinh_tu_tri_thuc(so_cap=15))

    assert d["id"] == "job_moi"
    assert "--so-cap" in r.da_chay[1][0].command
    assert "15" in r.da_chay[1][0].command


def test_chuyen_nhom_xuong_script(monkeypatch, tmp_path):
    _co_tai_lieu(monkeypatch, tmp_path)
    r = _RunnerGia()
    monkeypatch.setattr(tr, "runner", r)

    asyncio.run(tr.sinh_tu_tri_thuc(nhom="products"))

    lenh = r.da_chay[1][0].command
    assert "--nhom" in lenh and "products" in lenh


def test_khong_chay_khi_dang_co_job_khac(monkeypatch, tmp_path):
    """Một job một lúc: sinh mẫu và fine-tune cùng giành GPU thì cả hai cùng hỏng."""
    _co_tai_lieu(monkeypatch, tmp_path)
    monkeypatch.setattr(tr, "runner", _RunnerGia(ban=True))

    d = asyncio.run(tr.sinh_tu_tri_thuc())

    assert "error" in d and d["job_id"] == "job_cu"


def test_bao_loi_khi_chua_co_tai_lieu_nao(monkeypatch, tmp_path):
    _co_tai_lieu(monkeypatch, tmp_path, co=False)
    monkeypatch.setattr(tr, "runner", _RunnerGia())

    d = asyncio.run(tr.sinh_tu_tri_thuc())

    assert "error" in d


def test_so_cap_bi_kep_trong_khoang_hop_ly(monkeypatch, tmp_path):
    """Xin 500 cặp một mảnh là model bịa ra hàng loạt câu trùng nhau."""
    _co_tai_lieu(monkeypatch, tmp_path)
    r = _RunnerGia()
    monkeypatch.setattr(tr, "runner", r)

    asyncio.run(tr.sinh_tu_tri_thuc(so_cap=999))

    lenh = r.da_chay[1][0].command
    assert "999" not in lenh
