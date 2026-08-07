import json
from pathlib import Path

import pytest

from backend.services.filler_store import CauDem, ChuDe, LoiKho, nap


def _ghi(tmp_path: Path, du_lieu: dict) -> Path:
    p = tmp_path / "fillers.json"
    p.write_text(json.dumps(du_lieu, ensure_ascii=False), encoding="utf-8")
    return p


HOP_LE = {
    "chu_de": [{"id": "chung", "ten": "Chung", "tu_khoa": []}],
    "cau": [
        {"id": "chung_01", "text": "Dạ", "chu_de": "chung", "hop_cau_hoi": True},
        {"id": "chung_02", "text": "Vâng ạ", "chu_de": "chung", "hop_cau_hoi": False},
    ],
}


def test_nap_kho_hop_le(tmp_path):
    kho = nap(_ghi(tmp_path, HOP_LE))
    assert kho.chu_de == (ChuDe(id="chung", ten="Chung", tu_khoa=()),)
    assert kho.cau == (
        CauDem(id="chung_01", text="Dạ", chu_de="chung", hop_cau_hoi=True),
        CauDem(id="chung_02", text="Vâng ạ", chu_de="chung", hop_cau_hoi=False),
    )


def test_id_cau_trung_thi_bao_loi(tmp_path):
    xau = json.loads(json.dumps(HOP_LE))
    xau["cau"][1]["id"] = "chung_01"
    with pytest.raises(LoiKho, match="trùng"):
        nap(_ghi(tmp_path, xau))


def test_chu_de_khong_ton_tai_thi_bao_loi(tmp_path):
    xau = json.loads(json.dumps(HOP_LE))
    xau["cau"][0]["chu_de"] = "khong_co"
    with pytest.raises(LoiKho, match="không có chủ đề"):
        nap(_ghi(tmp_path, xau))


def test_text_rong_thi_bao_loi(tmp_path):
    xau = json.loads(json.dumps(HOP_LE))
    xau["cau"][0]["text"] = "   "
    with pytest.raises(LoiKho, match="rỗng"):
        nap(_ghi(tmp_path, xau))


def test_hop_cau_hoi_mac_dinh_la_true(tmp_path):
    thieu = {
        "chu_de": [{"id": "chung", "ten": "Chung", "tu_khoa": []}],
        "cau": [{"id": "c1", "text": "Dạ", "chu_de": "chung"}],
    }
    assert nap(_ghi(tmp_path, thieu)).cau[0].hop_cau_hoi is True


def test_file_khong_ton_tai_thi_bao_loi(tmp_path):
    with pytest.raises(LoiKho, match="không đọc được"):
        nap(tmp_path / "khong_co.json")
