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
    """Lượt trả bằng bảng câu sẵn bị BỎ. Còn lại max(2000, 1500) = 2000,
    nhân biên 1.25 -> 2500."""
    su = [
        {"ttfa_ms": 450, "la_thoai": True, "luot_thuong_gap": "chào hỏi"},
        {"ttfa_ms": 2000, "la_thoai": True},
        {"ttfa_ms": 1500, "la_thoai": True},
    ]
    assert can_che_ms(su, la_thoai=True, mac_dinh=1800.0) == 2500.0


def test_loc_dung_duong_thoai_hay_chat():
    """Chỉ lượt thoại được tính: 1200 * 1.25 = 1500, nhưng `mac_dinh` là SÀN
    nên kết quả là 1800."""
    su = [{"ttfa_ms": 3000, "la_thoai": False}, {"ttfa_ms": 1200, "la_thoai": True}]
    assert can_che_ms(su, la_thoai=True, mac_dinh=1800.0) == 1800.0


def test_lay_max_cua_sau_luot_gan_nhat():
    """Cửa sổ là SÁU lượt (`lich_su[-6:]`), không phải ba. Cả 4 lượt đều nằm
    trong cửa sổ nên max là 5000, nhân biên -> 6250."""
    su = [{"ttfa_ms": v, "la_thoai": True} for v in (5000, 1000, 1100, 1200)]
    assert can_che_ms(su, la_thoai=True, mac_dinh=1800.0) == 6250.0


def test_mac_dinh_la_SAN_chu_khong_chi_la_gia_tri_lui():
    """Lịch sử thấp cũng không được xuống dưới sàn."""
    su = [_luot(400), _luot(500)]
    assert can_che_ms(su, la_thoai=True, mac_dinh=2000.0) == 2000.0


def test_lich_su_cao_thi_vuot_san():
    su = [_luot(3000)]
    assert can_che_ms(su, la_thoai=True, mac_dinh=2000.0) == pytest.approx(3000.0 * BIEN_AN_TOAN)


def test_bo_qua_luot_thieu_ttfa():
    """None và 0 đều bị bỏ. Còn 1300 * 1.25 = 1625, dưới sàn -> 1800."""
    su = [
        {"ttfa_ms": None, "la_thoai": True},
        {"ttfa_ms": 0, "la_thoai": True},
        {"ttfa_ms": 1300, "la_thoai": True},
    ]
    assert can_che_ms(su, la_thoai=True, mac_dinh=1800.0) == 1800.0


def test_suy_ra_duong_tu_stt_ms_khi_ban_ghi_cu_khong_co_la_thoai():
    """Bản ghi cũ thiếu khoá `la_thoai` thì suy từ `stt_ms`. 1400 * 1.25 = 1750,
    dưới sàn -> 1800."""
    cu = [{"ttfa_ms": 1400, "stt_ms": 300}]
    assert can_che_ms(cu, la_thoai=True, mac_dinh=1800.0) == 1800.0


def test_bien_an_toan_duoc_ap_dung():
    """Biên 1.25 phải ăn khi kết quả vượt sàn."""
    su = [{"ttfa_ms": 4000, "la_thoai": True}]
    assert can_che_ms(su, la_thoai=True, mac_dinh=1800.0) == 5000.0


def test_mac_dinh_la_san_khong_phai_chi_gia_tri_lui():
    """Lịch sử toàn lượt nhanh vẫn không được xuống dưới sàn - vài lượt nhanh
    liên tiếp rồi một lượt chậm đột ngột là khách nghe hụt."""
    su = [{"ttfa_ms": 200, "la_thoai": True} for _ in range(6)]
    assert can_che_ms(su, la_thoai=True, mac_dinh=1800.0) == 1800.0


# --- ghep + du_phu -----------------------------------------------------------

from backend.services.filler_pick import du_phu, ghep  # noqa: E402


def test_ghep_dung_mot_khoang_trang():
    assert ghep("Dạ về lãi suất thì,", "anh chị chờ em ạ.") == \
        "Dạ về lãi suất thì, anh chị chờ em ạ."


def test_ghep_khong_mo_dau_thi_tra_duoi_nguyen_ven():
    """Mở đầu rỗng là trường hợp suy biến - đúng hành vi hôm nay."""
    assert ghep("", "anh chị chờ em ạ.") == "anh chị chờ em ạ."


def test_ghep_khong_de_hai_dau_cach():
    assert ghep("Dạ vâng,  ", "  em nghe ạ.") == "Dạ vâng, em nghe ạ."


def test_du_phu_khong_ho():
    """Cac moc rai deu 300ms mot thi khong ho khoang nao."""
    assert du_phu([700, 1000, 1300, 1600, 1900, 2200, 2500]) == []


def test_du_phu_bao_dung_khoang_ho():
    """Chi co cau 700ms va 2400ms -> ho dung dai 1000-2200, gop thanh MOT khoang.

    Kiem gia tri chinh xac chu khong chi 'co ho': buoc 300ms nen cac moc la
    700/1000/1300/1600/1900/2200/2500. 700 lap moc dau, 2400 lap moc 2200,
    con lai ho lien mot dai tu 1000 toi 2200.
    """
    assert du_phu([700, 2400]) == [(1000.0, 2200.0)]


def test_du_phu_hai_khoang_ho_roi_nhau_giu_roi():
    """Hai khoang ho KHONG lien nhau thi phai giu rieng, khong gop bua.

    700 lap moc dau, 1300 lap moc giua, 2400 lap moc cuoi -> ho hai cho roi:
    1000-1300 va 1600-2200.
    """
    assert du_phu([700, 1300, 2400]) == [(1000.0, 1300.0), (1600.0, 2200.0)]


def test_du_phu_ro_rong_thi_ho_toan_dai():
    assert du_phu([]) == [(700.0, 2500.0)]
