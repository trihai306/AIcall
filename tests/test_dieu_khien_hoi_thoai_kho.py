"""Biên khó của quyền dừng/hoãn cuộc gọi và minh bạch danh tính."""

import pytest

from backend.pipeline.luot_thuong_gap import (
    nhan_dang,
    tra_loi_san,
    y_dinh_dung_tu_van,
)


@pytest.mark.parametrize("cau", [
    "Thôi không trêu nữa, anh chưa có nhu cầu. Em đừng mời vay tiếp.",
    "Anh vừa nói chưa có nhu cầu rồi mà. Đừng đọc hạn mức nữa, dừng cuộc gọi giúp anh.",
    "anh khong co nhu cau nua em dung tu van tiep nhe",
    "đừng gọi nữa",
    "Không thích nữa, đừng gọi cho anh nhé.",
    "Thôi thôi cảm ơn, anh chưa cần mở.",
])
def test_tu_choi_dai_ngan_co_dau_ascii_deu_uu_tien_dung(cau):
    assert y_dinh_dung_tu_van(cau) == "tu_choi"
    assert nhan_dang(cau) == "tu_choi"
    ma, dap = tra_loi_san(
        cau, bank="Ngân hàng thử nghiệm", agent="Linh",
        product="vay tín chấp", luot_thu=4,
    )
    assert ma == "tu_choi"
    assert "không làm phiền thêm" in dap.lower()
    assert "hạn mức" not in dap.lower() and "vay tối đa" not in dap.lower()


@pytest.mark.parametrize("cau", [
    "thoi de chi tinh lai",
    "để anh hỏi vợ đã",
    "để cô hỏi con gái đã, đừng hỏi nữa",
    "Anh phải hỏi vợ, để hôm khác.",
    "đừng gọi sau5giờ vì giờ đó bận, gọi lúc3giờ",
])
def test_tri_hoan_khong_bi_hieu_thanh_tinh_toan_hoac_tu_choi(cau):
    assert y_dinh_dung_tu_van(cau) == "hen_lai"
    assert nhan_dang(cau) == "hen_lai"


@pytest.mark.parametrize("cau", [
    "anh đang lái xe",
    "chi dang ban hop khong tien nghe",
    "cô đang đi đường cháu ơi",
])
def test_ban_hoac_lai_xe_hoi_thoi_gian_tien(cau):
    assert y_dinh_dung_tu_van(cau) == "dang_ban"
    ket = tra_loi_san(cau, bank="B", agent="Linh", product="vay", luot_thu=2)
    assert ket and ket[0] == "dang_ban"
    assert "mấy giờ thì tiện" in ket[1].lower()


@pytest.mark.parametrize("cau", [
    "không có CCCD thì vay được không",
    "không muốn vay200 mà cần300",
    "không có nhu cầu vay nhưng muốn làm thẻ",
    "không phải anh không có nhu cầu",
    "anh đâu có nói là không có nhu cầu",
    "anh chưa bao giờ nói là không có nhu cầu",
    "anh không nói rằng anh không có nhu cầu",
    "vợ anh không có nhu cầu vay",
    "anh nói câu không có nhu cầu nghĩa là gì",
    "bạn anh không quan tâm nhưng anh muốn hỏi lãi suất",
    "đừng hỏi lãi suất nữa mà cho anh biết hạn mức",
])
def test_khong_nuot_cau_dieu_kien_doi_y_phu_dinh_trich_dan_nguoi_thu_ba(cau):
    assert y_dinh_dung_tu_van(cau) is None
    assert nhan_dang(cau) not in {"tu_choi", "hen_lai", "dang_ban"}


def test_y_dinh_truc_tiep_sau_cung_cua_khach_thang_theo_thu_tu_noi():
    assert y_dinh_dung_tu_van("đừng gọi nữa nhưng anh vẫn muốn biết hạn mức") is None
    assert y_dinh_dung_tu_van("anh vẫn muốn biết hạn mức nhưng dừng cuộc gọi") == "tu_choi"
    assert y_dinh_dung_tu_van("anh đang lái xe nhưng muốn hỏi lãi suất") == "dang_ban"


@pytest.mark.parametrize("cau", [
    "Vợ tôi bảo gọi lại sau, nhưng tôi muốn vay200triệu",
    "Vợ tôi bảo dừng cuộc gọi, nhưng tôi vẫn muốn vay200triệu",
    "Tôi muốn vay200triệu nhưng vợ tôi bảo dừng cuộc gọi",
    "Không phải tôi đang bận, tư vấn tiếp đi",
    "Không phải tôi chưa quyết định, tôi chốt vay200triệu",
    "Tôi không bảo em đừng hỏi nữa, cứ nói tiếp đi",
    "Tôi chỉ nhắc lại câu đừng hỏi nữa, em cứ tư vấn tiếp đi",
    "Anh đang bận, nhưng cứ tư vấn tiếp đi",
])
def test_y_dinh_nguoi_thu_ba_phu_dinh_trich_dan_va_ve_tiep_tuc_khong_dung(cau):
    assert y_dinh_dung_tu_van(cau) is None
    assert nhan_dang(cau) not in {"tu_choi", "hen_lai", "dang_ban"}


@pytest.mark.parametrize(("cau", "mong_doi"), [
    ("Cứ tư vấn tiếp đi, nhưng giờ anh đang bận", "dang_ban"),
    ("Anh muốn vay200triệu, nhưng thôi dừng cuộc gọi", "tu_choi"),
    ("Em đừng hỏi nữa", "tu_choi"),
    ("Từ giờ đừng gọi nữa", "tu_choi"),
    ("Xin lỗi, đừng gọi cho anh nữa", "tu_choi"),
    ("Anh chưa quyết định, gọi lại sau nhé", "hen_lai"),
])
def test_lenh_dieu_khien_that_sau_cung_van_duoc_ton_trong(cau, mong_doi):
    assert y_dinh_dung_tu_van(cau) == mong_doi


@pytest.mark.parametrize(("cau", "mong_doi"), [
    ("Không phải vợ tôi đang lái xe, tôi đang lái xe", "dang_ban"),
    ("Không phải vợ tôi đang bận, tôi đang bận", "dang_ban"),
    ("Vợ tôi không bận, tôi đang bận", "dang_ban"),
    ("Tôi đang bận, nhưng giờ tôi không bận nữa", None),
    ("Vợ tôi đang lái xe, tôi không lái xe", None),
    ("Không phải vợ tôi đang bận nhưng tôi đang bận", "dang_ban"),
])
def test_ranh_gioi_ve_khong_lam_ro_ri_phu_dinh_va_chu_the(cau, mong_doi):
    assert y_dinh_dung_tu_van(cau) == mong_doi


@pytest.mark.parametrize(("cau", "mong_doi"), [
    ("Đừng gọi nữa, tôi không bận nữa", "tu_choi"),
    ("Gọi lại sau nhé, giờ tôi không bận nữa", "hen_lai"),
    ("Tôi chưa có nhu cầu, giờ tôi không bận nữa", "tu_choi"),
])
def test_huy_trang_thai_ban_khong_huy_lenh_dung_hoac_hen(cau, mong_doi):
    assert y_dinh_dung_tu_van(cau) == mong_doi
    assert nhan_dang(cau) == mong_doi


@pytest.mark.parametrize("cau", [
    "Không phải tôi đang bận",
    "Vợ tôi đang bận",
    "Tôi không cần gọi lại sau",
])
def test_helper_la_nguon_duy_nhat_khong_de_bang_cu_bat_lai(cau):
    assert y_dinh_dung_tu_van(cau) is None
    assert nhan_dang(cau) is None


def test_hoi_ai_duoc_cong_khai_va_em_la_ai_van_xung_danh_nhan_vien():
    for cau in ("em là AI hay người", "em có phải robot không", "em là máy à"):
        ma, dap = tra_loi_san(cau, bank="B", agent="Linh", product="vay", luot_thu=2)
        assert ma == "danh_tinh_tu_dong"
        assert "AI" in dap and "VoiceBankAI" in dap and "tự động" in dap

    ma, dap = tra_loi_san("em là ai", bank="B", agent="Linh", product="vay", luot_thu=2)
    assert ma == "ai_day"
    assert "Linh" in dap


def test_hoi_nguon_so_khong_bia_danh_sach_va_cau_ghep_tra_du_hai_y():
    ma, dap = tra_loi_san(
        "em là máy hay người, sao em có số anh?",
        bank="B", agent="Linh", product="vay", luot_thu=2,
    )
    assert ma == "danh_tinh_va_nguon"
    assert "VoiceBankAI" in dap
    assert "không có thông tin đã được xác minh" in dap.lower()

    ma, dap = tra_loi_san(
        "Anh hỏi hai chuyện: em có phải AI không, và số anh lấy từ đâu?",
        bank="B", agent="Linh", product="vay", luot_thu=3,
    )
    assert ma == "danh_tinh_va_nguon"
    assert "VoiceBankAI" in dap and "không có thông tin đã được xác minh" in dap.lower()
    assert "danh sách" not in dap.lower() and "đồng ý nhận" not in dap.lower()

    ma, dap = tra_loi_san(
        "số anh ở đâu ra vậy", bank="B", agent="Linh", product="vay", luot_thu=2,
    )
    assert ma == "sao_co_so"
    assert "không có thông tin đã được xác minh" in dap.lower()


def _dan_dat(cau_khach: str):
    from backend.pipeline.dan_dat import cau_hoi_tiep
    from backend.pipeline.du_kien_khoan_vay import resolve

    lich_su = [{"role": "user", "content": cau_khach}]
    return cau_hoi_tiep(
        ma_san_pham="vay_tin_chap",
        trang_thai=resolve(lich_su),
        loi_khach_ca_cuoc=cau_khach,
        loi_khach_luot_nay=cau_khach,
        cau_tra_loi="Dạ em ghi nhận ạ.",
        da_hoi=set(),
    )


@pytest.mark.parametrize("cau", [
    "Anh vừa nói chưa có nhu cầu rồi mà, đừng đọc hạn mức nữa và dừng cuộc gọi giúp anh.",
    "thoi de chi tinh lai",
    "để cô hỏi con gái đã, đừng hỏi nữa",
    "anh dang lai xe chua noi chuyen duoc",
])
def test_dung_hoan_ban_khong_bi_noi_cau_hoi_dan_dat(cau):
    assert _dan_dat(cau) is None


def test_sau_cau_khong_phai_dieu_khien_dan_dat_van_hoat_dong():
    assert _dan_dat("lãi suất vay bao nhiêu") == (
        "so_tien", "Anh chị dự định vay khoảng bao nhiêu ạ?",
    )


@pytest.mark.parametrize("cau", [
    "Vợ tôi bảo gọi lại sau, nhưng tôi muốn vay200triệu",
    "Không phải tôi đang bận, tư vấn tiếp đi",
    "Không phải tôi chưa quyết định, tôi chốt vay200triệu",
])
def test_dan_dat_khong_chan_y_dinh_nguoi_thu_ba_hoac_bi_phu_dinh(cau):
    assert _dan_dat(cau) is not None


def test_danh_tinh_va_nguon_so_khong_bi_noi_cau_hoi_tai_chinh():
    from backend.pipeline.dan_dat import cau_hoi_tiep
    from backend.pipeline.du_kien_khoan_vay import resolve

    cau = "Em có phải AI không, và số anh lấy từ đâu?"
    lich_su = [{"role": "user", "content": cau}]
    assert cau_hoi_tiep(
        ma_san_pham="vay_tin_chap", trang_thai=resolve(lich_su),
        loi_khach_ca_cuoc=cau, loi_khach_luot_nay=cau,
        cau_tra_loi="Dạ em là trợ lý AI của VoiceBankAI ạ.", da_hoi=set(),
        y_dinh_thuong_gap="danh_tinh_va_nguon",
    ) is None
