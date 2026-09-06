"""Phân loại đã vượt ngưỡng thì được DÙNG, không xét độ phủ nữa.

Luật cũ (`_TINH_HUONG_DO_PHU_MIN = 0.5`) vứt mọi phân loại mà bản đoán nghe
được dưới nửa lượt. Trong code nó tự ghi "TẠM 0.5, CHƯA ĐO".

Đo 06-09-2026 trên 102 lượt tiếng khách thật (`data/tieng_khach_that`), chấm ở
đúng ngưỡng đường thật dùng (0.90), cắt theo tỉ lệ BYTE AUDIO như `do_phu` thật:

    do_phu   vượt ngưỡng   ĐÚNG   SAI      luật cũ
      0.15         0          0     0      vứt đi
      0.25         0          0     0      vứt đi
      0.35         1          1     0      vứt đi
      0.45         3          3     0      vứt đi
      0.55         3          3     0      giữ lại
      0.70         4          4     0      giữ lại
      0.85         6          6     0      giữ lại

SAI = 0 ở MỌI mức. Phần luật cũ vứt đi là 4 đúng / 0 sai - nó không chặn được
lần sai nào, chỉ bỏ đi kết quả tốt.

Vì sao được phép bỏ: ngưỡng ĐIỂM đã làm sẵn việc đó. Chính chú thích của
`NGUONG_DIEM` viết "điểm thấp chính là dấu hiệu câu còn cụt" - tức điểm đo
thẳng thứ mà độ phủ chỉ đo gián tiếp qua độ dài. Đo lại thấy không bản cắt nào
lọt 0.90 khi độ phủ dưới 0.35.
"""
import pytest

from backend.services.filler_pick import tinh_huong_dung


def test_do_phu_thap_van_dung_khi_da_vuot_nguong():
    """Đúng ca đo được trên máy thật: điểm 0.915, bản đoán nghe 35% lượt."""
    id_th, do_phu = tinh_huong_dung((3500, "hoi_lai_suat", 0.915), n_audio=10000)
    assert id_th == "hoi_lai_suat"
    assert do_phu == pytest.approx(0.35)


def test_chua_phan_loai_duoc_thi_khong_co_gi_de_dung():
    assert tinh_huong_dung(None, n_audio=10000) == (None, None)


def test_duong_chat_khong_audio_thi_bo_qua():
    """`n_audio = 0` là đường gõ chữ - không có tiếng để tính độ phủ."""
    assert tinh_huong_dung((3500, "hoi_lai_suat", 0.915), n_audio=0) == (None, None)


def test_bo_luoi_do_phu_thi_nguong_diem_phai_con_gach_duoi_09():
    """Lưới canh: giờ CHỈ còn ngưỡng điểm gánh việc lọc câu cụt.

    Bảng số đo ở đầu tệp này đo tại 0,90. Hạ ngưỡng xuống là mở cửa cho bản cắt
    điểm thấp - đúng thứ mà độ phủ từng chặn hộ. Đo lại bảng đó trước khi hạ.
    """
    from backend.services.filler_situation import NGUONG_CAU_DEM
    assert NGUONG_CAU_DEM >= 0.90, (
        "hạ ngưỡng câu đệm mà không còn lưới độ phủ -> phải đo lại bảng "
        "do_phu/ĐÚNG/SAI ở đầu tệp này trước khi chốt")
