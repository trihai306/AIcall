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


from backend.services.filler_store import van_tay

_GOC = dict(text="Dạ", giong="fosd_1", nfe=16, speed=1.0, ref_text="xin chào")


def test_van_tay_on_dinh_giua_hai_lan_goi():
    assert van_tay(**_GOC) == van_tay(**_GOC)


def test_van_tay_an_toan_lam_ten_file():
    vt = van_tay(**_GOC)
    assert len(vt) == 12
    assert all(k in "0123456789abcdef" for k in vt)


@pytest.mark.parametrize("truong,gia_tri_moi", [
    ("text", "Vâng ạ"),
    ("giong", "giong_khac"),
    ("nfe", 12),
    ("speed", 1.2),
    ("ref_text", "câu mẫu khác"),
])
def test_van_tay_doi_khi_bat_ky_tham_so_nao_doi(truong, gia_tri_moi):
    khac = {**_GOC, truong: gia_tri_moi}
    assert van_tay(**khac) != van_tay(**_GOC)


def test_van_tay_khong_nham_ranh_gioi_truong():
    # "A\x00B" + "C" va "A" + "B\x00C" tao ra cung chuoi neu dung \x00 lam ngan
    vt1 = van_tay(text="A\x00B", giong="C", nfe=16, speed=1.0, ref_text="ref")
    vt2 = van_tay(text="A", giong="B\x00C", nfe=16, speed=1.0, ref_text="ref")
    assert vt1 != vt2
