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


def test_ha_nguong_thi_vung_do_phu_thap_phai_con_duoc_canh():
    """Lưới canh ràng buộc giữa hai module.

    Ngưỡng chung hạ xuống dưới 0,90 thì vùng độ phủ thấp KHÔNG còn an toàn nữa
    (bảng 0,75 ở trên: 4 đúng / 7 sai). Lúc đó `tinh_huong_dung` phải tự đòi
    điểm cao ở vùng đó. Test này hỏng nghĩa là ai đó hạ ngưỡng mà gỡ mất luật.
    """
    from backend.services.filler_situation import NGUONG_CAU_DEM
    if NGUONG_CAU_DEM >= 0.90:
        return                      # ngưỡng tự gác cửa, không cần lưới thứ hai
    id_th, _ = tinh_huong_dung((3500, "x", NGUONG_CAU_DEM), n_audio=10000)
    assert id_th is None, (
        f"ngưỡng đang {NGUONG_CAU_DEM} mà độ phủ 0,35 vẫn lọt - đo được 7 lần "
        "sai ở vùng này")


# --- Sau khi ha nguong ve 0,75 (06-09-2026, theo yeu cau nguoi dung) ----------
#
# Do lai dung bang tren o nguong 0,75 (`scripts/do_do_phu_tinh_huong.py 0.75`):
#
#     do_phu   vượt ngưỡng   ĐÚNG   SAI   ?
#       0.15         0          0     0   0
#       0.25         1          0     0   1
#       0.35         8          1     3   4
#       0.45        15          3     4   8
#       0.55        24          8     6  10
#       0.70        32         20     5   7
#       0.85        34         31     0   3
#
# ĐẢO NGƯỢC so với bảng ở 0,90: phần độ phủ dưới 0,5 từ "4 đúng / 0 sai" thành
# "4 đúng / 7 SAI". Tức lưới độ phủ là đồ thừa ở 0,90 nhưng là lưới THẬT ở 0,75.
#
# Không quay lại sàn phẳng 0,5: làm thế thì vứt luôn ca đo được trên máy thật
# (điểm 0,915, độ phủ 0,35) - chính ca người dùng vừa thấy chạy đúng. Hai bảng
# đo cùng chỉ về một luật: ĐỘ PHỦ THẤP THÌ ĐÒI ĐIỂM CAO.

def test_do_phu_thap_ma_diem_thap_thi_BO():
    """Đúng vùng 4 đúng/7 sai: độ phủ 0,35 mà điểm chỉ 0,80."""
    id_th, do_phu = tinh_huong_dung((3500, "hoi_lai_suat", 0.80), n_audio=10000)
    assert id_th is None, "vùng này đo được 7 lần sai - phải bỏ"
    assert do_phu == pytest.approx(0.35), "vẫn phải trả độ phủ để ghi metrics"


def test_do_phu_cao_thi_diem_0_75_la_du():
    """Độ phủ 0,85 đo được 31 đúng / 0 sai - không cần đòi thêm."""
    id_th, _ = tinh_huong_dung((8500, "hoi_lai_suat", 0.78), n_audio=10000)
    assert id_th == "hoi_lai_suat"
