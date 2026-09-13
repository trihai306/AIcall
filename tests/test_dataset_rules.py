from backend.core.dataset_rules import dem_cau, kiem_tra_tra_loi


def test_so_thap_phan_khong_bi_dem_thanh_hai_cau():
    assert dem_cau("Dạ lãi suất hiện là 7.9%/năm ạ. Em tư vấn tiếp cho anh ạ.") == 2


def test_dataset_duoc_giu_chu_so_giong_prompt_production():
    loi, _ = kiem_tra_tra_loi("Dạ em ghi nhận anh muốn vay 100 triệu trong 36 tháng ạ.")
    assert not loi


def test_dataset_cho_toi_da_35_tu():
    cau = "Dạ " + "em " * 32 + "ạ."
    loi, _ = kiem_tra_tra_loi(cau)
    assert not any("từ (tối đa" in x for x in loi)


def test_dataset_chan_tren_35_tu():
    cau = "Dạ " + "em " * 35 + "ạ."
    loi, _ = kiem_tra_tra_loi(cau)
    assert any("từ (tối đa 35)" in x for x in loi)
