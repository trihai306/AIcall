import random

import pytest

from backend.services.filler_pick import BIEN_AN_TOAN, chon

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


# --- can_che_ms: cần che bao nhiêu mili giây ------------------------------

from backend.services.filler_pick import BIEN_AN_TOAN, can_che_ms  # noqa: E402


def _luot(ttfa, la_thoai=True, cau_san=False):
    m = {"ttfa_ms": ttfa, "la_thoai": la_thoai}
    if cau_san:
        m["luot_thuong_gap"] = "chào hỏi"
    return m


def test_lich_su_rong_thi_lay_mac_dinh():
    assert can_che_ms([], la_thoai=True, mac_dinh=1800.0) == 1800.0


def test_bo_qua_luot_tra_loi_bang_cau_san():
    # Lượt trúng bảng câu sẵn KHÔNG gọi LLM nên nhanh có cấu trúc. Dùng nó để
    # đoán cho lượt phải gọi LLM là đoán trượt - đo thật 08-08: hai lượt câu sẵn
    # 450/458ms khiến lượt 3 bị bỏ câu đệm, rồi lượt 3 mất 3399ms -> khách nghe
    # im 3,4 giây.
    su = [_luot(450, cau_san=True), _luot(458, cau_san=True)]
    assert can_che_ms(su, la_thoai=True, mac_dinh=1800.0) == 1800.0


def test_chi_tinh_luot_that_khi_co_ca_hai_loai():
    su = [_luot(450, cau_san=True), _luot(2000), _luot(1500)]
    assert can_che_ms(su, la_thoai=True, mac_dinh=0.0) == pytest.approx(2000.0 * BIEN_AN_TOAN)


def test_loc_dung_duong_thoai_hay_chat():
    su = [_luot(3000, la_thoai=False), _luot(1200, la_thoai=True)]
    assert can_che_ms(su, la_thoai=True, mac_dinh=0.0) == pytest.approx(1200.0 * BIEN_AN_TOAN)
    assert can_che_ms(su, la_thoai=False, mac_dinh=0.0) == pytest.approx(3000.0 * BIEN_AN_TOAN)


def test_lay_max_cua_sau_luot_gan_nhat():
    """Cửa sổ 3 -> 6 lượt (08-10).

    Với cửa sổ 3, vài lượt nhanh liên tiếp kéo ước lượng xuống thấp rồi một lượt
    chậm đột ngột là hụt. Đo được: lịch sử toàn 678ms, lượt sau 1056ms.
    """
    su = [_luot(5000), _luot(1000), _luot(1100), _luot(1200)]
    assert can_che_ms(su, la_thoai=True, mac_dinh=0.0) == pytest.approx(5000.0 * BIEN_AN_TOAN)


def test_mac_dinh_la_SAN_chu_khong_chi_la_gia_tri_lui():
    """Lịch sử thấp cũng không được xuống dưới sàn."""
    su = [_luot(400), _luot(500)]
    assert can_che_ms(su, la_thoai=True, mac_dinh=2000.0) == 2000.0


def test_lich_su_cao_thi_vuot_san():
    su = [_luot(3000)]
    assert can_che_ms(su, la_thoai=True, mac_dinh=2000.0) == pytest.approx(3000.0 * BIEN_AN_TOAN)


def test_bo_qua_luot_thieu_ttfa():
    su = [_luot(None), _luot(0), _luot(1300)]
    assert can_che_ms(su, la_thoai=True, mac_dinh=0.0) == pytest.approx(1300.0 * BIEN_AN_TOAN)


def test_suy_ra_duong_tu_stt_ms_khi_ban_ghi_cu_khong_co_la_thoai():
    # Bản ghi cũ trong DB không có khoá `la_thoai`. Suy từ stt_ms như bản trước.
    cu = [{"ttfa_ms": 1400, "stt_ms": 300}]
    assert can_che_ms(cu, la_thoai=True, mac_dinh=0.0) == pytest.approx(1400.0 * BIEN_AN_TOAN)
