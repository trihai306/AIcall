"""Điểm 0,75-0,90: phát câu đệm TRUNG TÍNH thay vì câu đúng chủ đề.

LỖI THẬT, người dùng nghe được 09-09-2026: khách hỏi "bên bạn có cho vay tín
chấp không" mà câu đệm là "điều kiện vay". Chấm lại đúng câu đó:
`hoi_dieu_kien` = 0,750 - vừa đúng bằng `NGUONG_CAU_DEM` nên nó lọt.

KHÔNG phải hồi quy. Ngưỡng từng là 0,90 và người dùng CHỌN hạ xuống 0,75 ngày
06-09 sau khi thấy giá của 0,90: 3/5 lượt không nhận ra tình huống, tức 60% lượt
khách nghe im lặng trọn quãng chờ. Cái giá chiều ngược lại cũng đã đo và ghi
trong chú thích của `NGUONG_CAU_DEM` (102 lượt tiếng khách thật):

    0,75 -> chọn 29, đúng 15, SAI 14      (một nửa nói trớt chủ đề)
    0,90 -> chọn  4, đúng  4, SAI  0

Đường thứ ba, chỉ khả thi TỪ 09-09: rổ `chung` trước đây toàn câu "chờ em một
chút" - phát nó thay câu đúng chủ đề thì còn tệ hơn. Nay rổ đó là câu DẪN trung
tính ("Dạ em thông tin ngay cho anh chị,"), nên vùng không chắc có chỗ để rơi
về mà vẫn nghe xuôi.

Luật 0,90 PHẲNG là quá thô: nó phủ định một bằng chứng đã có
(`test_do_phu_cao_thi_diem_0_75_la_du`) và vứt luôn 15/20 lần chọn ĐÚNG. Đo lại
ba chính sách trên đúng 102 lượt tiếng khách thật, mốc 1200ms:

    chính sách                       ĐÚNG  trung tính   SAI chủ đề
    hiện tại (>= 0,75 là dùng)         20           0           13
    0,90 phẳng                          5          28            0
    0,90 + miễn trừ độ phủ >= 0,85     14          18            1

Nên chốt bản có MIỄN TRỪ:
    dưới 0,75                        -> im như cũ (phân loại không ghi gì)
    0,75-0,90 mà nghe chưa trọn lượt -> câu đệm TRUNG TÍNH
    0,75-0,90 mà nghe gần trọn lượt  -> vẫn dùng đúng chủ đề (đã đo 31/0)
    từ 0,90                          -> đúng chủ đề

Trả `None` là đủ - `pick_filler` duyệt `(id_tinh_huong, MA_NHOM_CHUNG, "")` nên
None tự rơi về rổ chung. Số lượt IM LẶNG không đổi ở cả ba chính sách (69).
"""
from backend.services.filler_pick import (DIEM_CHAC_CHU_DE, DO_PHU_DU_TIN,
                                          tinh_huong_dung)

N = 100_000          # byte tiếng của lượt
PHU_DAY = N          # bản đoán nghe TRỌN lượt -> độ phủ 1,0 (được miễn trừ)
PHU_VUA = 60_000     # nghe 60% lượt -> dưới `DO_PHU_DU_TIN`, KHÔNG miễn trừ


def test_diem_cao_thi_dung_dung_tinh_huong():
    id_th, _ = tinh_huong_dung((PHU_DAY, "hoi_lai_suat", 0.95), N)
    assert id_th == "hoi_lai_suat"


def test_dung_nguong_0_90_van_dung_tinh_huong():
    """Biên là CHẶT DƯỚI: đúng 0,90 thì vẫn coi là chắc."""
    id_th, _ = tinh_huong_dung((PHU_DAY, "hoi_lai_suat", DIEM_CHAC_CHU_DE), N)
    assert id_th == "hoi_lai_suat"


def test_vung_khong_chac_thi_ve_ro_chung():
    """Đúng ca người dùng nghe được: 0,750 -> đừng nói "điều kiện vay"."""
    id_th, do_phu = tinh_huong_dung((PHU_VUA, "hoi_dieu_kien", 0.750), N)
    assert id_th is None, "vẫn dùng tình huống chấm 0,750 - sẽ nói trớt chủ đề"
    assert do_phu is not None, "bỏ tình huống thì vẫn phải giữ số đo độ phủ"


def test_van_bo_han_khi_diem_qua_thap():
    """Dưới ngưỡng câu đệm thì bộ phân loại đã không ghi gì - giữ nguyên."""
    assert tinh_huong_dung(None, N) == (None, None)


def test_duong_go_chu_khong_doi():
    """`n_audio <= 0` là đường gõ chữ - luật này không được chạm vào nó."""
    assert tinh_huong_dung((PHU_DAY, "hoi_lai_suat", 0.80), 0) == (None, None)


def test_nghe_gan_TRON_luot_thi_diem_thap_VAN_dung():
    """Miễn trừ: độ phủ cao thì 0,78 đã đo được 31 đúng / 0 sai.

    Luật 0,90 PHẲNG vứt luôn 15/20 lần chọn đúng - đo trên 102 lượt tiếng khách
    thật, xem bảng ở `DIEM_CHAC_CHU_DE`.
    """
    id_th, _ = tinh_huong_dung((int(N * DO_PHU_DU_TIN), "hoi_lai_suat", 0.78), N)
    assert id_th == "hoi_lai_suat"


def test_nguong_chac_KHONG_thap_hon_nguong_cau_dem():
    """Đặt nhầm thấp hơn là luật thành mã chết, im lặng không ai biết."""
    from backend.services.filler_situation import NGUONG_CAU_DEM
    assert DIEM_CHAC_CHU_DE >= NGUONG_CAU_DEM
