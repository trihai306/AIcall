"""Đáp NGẮN chỉ đúng khi câu đệm ĐÃ hứa kiểm tra - không phải cứ có câu đệm.

Cuộc gọi thật 1e8bd9de (07-09-2026, 17:42):

    khách    : ờ anh muốn vay ba bốn trăm được không
    câu đệm  : "Dạ em xin phép TRÌNH BÀY CỤ THỂ để anh chị nắm rõ hơn nhé,"
    lưới chặn: CHẶN TIỀN SAI -> đổi câu
    AI       : "Vâng ạ."

Khách hỏi một câu có/không rồi nghe đúng hai chữ "Vâng ạ." và AI im. Ngay sau đó
khách phải "a lô" hai lần vì tưởng máy chết.

Luật rút ngắn (`CAU_NGAN_SAU_DEM`) vốn ĐÚNG, và có lý do đo được: người dùng
06-09 nghe cuộc gọi thật rồi bảo *"cái câu em xin phép kiểm tra lại rồi báo anh
chị nó dài, chỉ cần dạ vâng là đủ"*. Nhưng nó đúng trong ĐÚNG MỘT hoàn cảnh: câu
đệm vừa hứa "em kiểm tra lại rồi báo lại", nên nhắc lại trọn lời hứa là thừa.

Bản cũ chỉ hỏi "CÓ câu đệm không" chứ không hỏi "câu đệm nói GÌ". Kho câu đệm có
38 tình huống, phần lớn KHÔNG hứa kiểm tra - chúng hứa trình bày, giới thiệu,
nói rõ hơn. Sau những câu đó, "Vâng ạ." là câu trả lời rỗng.
"""
from backend.pipeline.cau_chan_lap import CAU_NGAN_SAU_DEM, cau_chan, hua_kiem_tra
from backend.pipeline.text_normalizer import CAU_KIEM_TRA_LAI

DEM_HUA_KIEM_TRA = "Vâng, em kiểm tra lại thông tin rồi trả lời anh chị cho chính xác nhé"
DEM_HUA_TRINH_BAY = "Dạ em xin phép trình bày cụ thể để anh chị nắm rõ hơn nhé,"


def test_nhan_ra_cau_dem_co_hua_kiem_tra():
    assert hua_kiem_tra(DEM_HUA_KIEM_TRA)
    assert hua_kiem_tra("Dạ để em xem lại cho chính xác rồi em trả lời anh chị ngay đây ạ")
    assert hua_kiem_tra("Dạ em tra lại rồi báo mình sau ạ")


def test_cau_dem_hua_thu_KHAC_thi_khong_tinh():
    assert not hua_kiem_tra(DEM_HUA_TRINH_BAY)
    assert not hua_kiem_tra("Dạ lãi suất bên em thì,")
    assert not hua_kiem_tra("Dạ vâng em xin phép giới thiệu,")
    assert not hua_kiem_tra("")


def test_dem_da_hua_kiem_tra_thi_dap_NGAN():
    """Giữ nguyên hành vi người dùng đã chọn 06-09."""
    assert cau_chan(1, cau_dem=DEM_HUA_KIEM_TRA) == CAU_NGAN_SAU_DEM


def test_dem_hua_TRINH_BAY_thi_phai_noi_du_cau():
    """Ca hỏng của cuộc 1e8bd9de - đây là chỗ 'Vâng ạ.' lọt ra."""
    ra = cau_chan(1, cau_dem=DEM_HUA_TRINH_BAY)
    assert ra != CAU_NGAN_SAU_DEM, "câu đệm hứa trình bày mà đáp 'Vâng ạ.' là bỏ lửng"
    assert ra == CAU_KIEM_TRA_LAI


def test_khong_co_cau_dem_thi_van_nhu_cu():
    assert cau_chan(1, cau_dem="") == CAU_KIEM_TRA_LAI
    assert cau_chan(1) == CAU_KIEM_TRA_LAI


def test_lan_chan_thu_hai_van_hoi_lai_con_so():
    """Đã lặp thì phải HỎI LẠI, bất kể câu đệm nói gì."""
    assert "nhắc lại" in cau_chan(2, cau_dem=DEM_HUA_KIEM_TRA)
    assert "nhắc lại" in cau_chan(2, cau_dem=DEM_HUA_TRINH_BAY)
