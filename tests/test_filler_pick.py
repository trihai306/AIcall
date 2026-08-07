import random

from backend.services.filler_pick import chon

RNG = lambda: random.Random(0)   # noqa: E731 - cố định để test lặp lại được


def test_rong_thi_tra_none():
    assert chon([], min_ms=900, dem={}, rng=RNG()) is None


def test_uu_tien_cau_vua_khit_thay_vi_cau_dai_nhat():
    # Cần che 900ms. Câu 2600ms tuy "đủ dài" nhưng đẩy câu trả lời thật lùi
    # 1700ms vô ích - đúng lỗi mà luật cũ mắc.
    assert chon([("a", 900.0), ("b", 2600.0)], min_ms=900, dem={}, rng=RNG()) == "a"


def test_noi_ra_ngoai_khoang_vua_khit_khi_khong_con_gi_khac():
    assert chon([("b", 2600.0)], min_ms=900, dem={}, rng=RNG()) == "b"


def test_khong_cau_nao_du_dai_thi_lay_cau_dai_nhat():
    # Khách chắc chắn nghe một quãng lặng; việc còn lại là làm nó ngắn nhất.
    assert chon([("a", 300.0), ("b", 800.0)], min_ms=1800, dem={}, rng=RNG()) == "b"


def test_duyet_het_nhom_roi_moi_lap_lai():
    ung_vien = [(f"c{i}", 1000.0) for i in range(5)]
    dem: dict[str, int] = {}
    r = RNG()
    ra = []
    for _ in range(5):
        cid = chon(ung_vien, min_ms=900, dem=dem, rng=r)
        ra.append(cid)
        dem[cid] = dem.get(cid, 0) + 1
    assert sorted(ra) == ["c0", "c1", "c2", "c3", "c4"]


def test_nhom_hai_cau_thi_luan_phien_khong_ket():
    ung_vien = [("a", 1000.0), ("b", 1000.0)]
    dem: dict[str, int] = {}
    r = RNG()
    ra = []
    for _ in range(4):
        cid = chon(ung_vien, min_ms=900, dem=dem, rng=r)
        ra.append(cid)
        dem[cid] = dem.get(cid, 0) + 1
    assert ra.count("a") == 2 and ra.count("b") == 2


def test_it_dung_nhat_duoc_uu_tien_hon_ca_do_vua_khit():
    # "a" vừa khít nhưng đã dùng 2 lần; "b" chưa dùng -> phải ra "b".
    ra = chon([("a", 900.0), ("b", 1000.0)], min_ms=900,
              dem={"a": 2}, rng=RNG())
    assert ra == "b"
