from backend.pipeline.loi_dan_luot import LOI_DAN, loi_dan_luot_ngan


def test_chi_dan_luot_ngan():
    assert loi_dan_luot_ngan("cũng như nào") == LOI_DAN
    assert loi_dan_luot_ngan("sâu giờ bấy nhiêu") == LOI_DAN
    assert loi_dan_luot_ngan("anh muốn vay hai trăm triệu trong ba năm") == ""
    assert loi_dan_luot_ngan("") == ""
