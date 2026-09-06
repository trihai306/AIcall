"""Khách im sau khi AI trả lời xong thì phải NHẮC, đừng để hai bên cùng im.

VÌ SAO CÓ FILE NÀY. Cuộc gọi thật `99ee5360` (05-09-2026). Đo mức từng giây trên
bản ghi, 6 giây cuối:

    giây   40    41    42    43    44    45
    khách 334    35    11    24    21    16     (chỉ còn nền)
    AI      0     0     0     0     0     0     (im tuyệt đối)

Rồi khách cúp - `dumpsys telecom` báo REMOTE/NORMAL, tức chính khách bấm cúp.
AI trả lời xong là im hẳn, không mời khách nói tiếp, nên nghe như cuộc gọi đã
đứt. Đây là lỗi THIẾT KẾ HỘI THOẠI, không phải lỗi đường tiếng.

Luật nhắc tách riêng thành hàm thuần để test được: vòng chạy thật nằm trong một
task nền của `PhoneCallBridge`, không dựng lại được trong test đơn vị.
"""
import pytest

from backend.services.nhac_im_lang import (CAU_NHAC, chon_cau_nhac,
                                            co_nen_nhac, nguong_cho_lan)

NGUONG = 4.0
TOI_DA = 2


def _hoi(im, so_lan=0, ai_noi=False, con_tieng=False):
    return co_nen_nhac(im_giay=im, so_lan_da_nhac=so_lan, ai_dang_noi=ai_noi,
                       con_tieng_cho_phat=con_tieng,
                       nguong_giay=NGUONG, toi_da=TOI_DA)


# --- Nhắc đúng lúc --------------------------------------------------------

def test_im_qua_nguong_thi_nhac():
    assert _hoi(4.0) is True
    assert _hoi(6.0) is True


def test_chua_du_nguong_thi_chua_nhac():
    assert _hoi(3.9) is False
    assert _hoi(0.0) is False


# --- Không được chen vào lúc đang có tiếng --------------------------------

def test_ai_dang_noi_thi_khong_nhac():
    """Cắt ngang chính mình là hỏng cả lượt."""
    assert _hoi(30.0, ai_noi=True) is False


def test_con_tieng_trong_hang_doi_thi_khong_nhac():
    """Lượt đã sinh xong nhưng tiếng còn đang phát - khách vẫn đang nghe."""
    assert _hoi(30.0, con_tieng=True) is False


# --- Không nhắc mãi -------------------------------------------------------

def test_nhac_toi_da_hai_lan():
    assert _hoi(30.0, so_lan=1) is True
    assert _hoi(30.0, so_lan=2) is False
    assert _hoi(60.0, so_lan=5) is False


# --- Ngưỡng phải NỚI DẦN, không dùng chung một số -------------------------

def test_lan_hai_phai_cho_lau_hon_han_lan_dau():
    """Cuộc gọi thật `f2f61c42`: ngưỡng phẳng 4s bắn 6 câu nhắc trong 47 giây,
    có chỗ vừa hỏi 'còn nghe em không' xong 4 giây đã nói 'xin phép gọi lại'."""
    assert nguong_cho_lan(1, NGUONG) > nguong_cho_lan(0, NGUONG) * 2


def test_vua_qua_nguong_lan_dau_thi_chua_nhac_lan_hai():
    assert _hoi(NGUONG + 0.1, so_lan=1) is False


# --- Khách đang nói thì tuyệt đối không chen ------------------------------

def test_khach_dang_noi_thi_khong_nhac():
    """Vòng gọi truyền `ai_dang_noi = _luot_dang_chay OR _khach_dang_noi`.
    Thiếu vế sau thì câu nhắc chen vào giữa lượt - đã xảy ra thật."""
    assert _hoi(60.0, ai_noi=True) is False


# --- Câu nhắc -------------------------------------------------------------

def test_hai_lan_nhac_noi_hai_cau_khac_nhau():
    a, b = chon_cau_nhac(0), chon_cau_nhac(1)
    assert a != b
    assert a.strip() and b.strip()


def test_cau_nhac_khong_chua_so():
    """Câu nhắc đi thẳng xuống TTS, không qua RAG - có số là không tra được."""
    import re
    for c in CAU_NHAC:
        assert not re.search(r"\d", c), f"câu nhắc không được chứa số: {c!r}"


def test_lan_thu_hai_la_loi_xin_phep_gac_may():
    """Nhắc lần hai mà vẫn im thì phải mở đường kết thúc, đừng hỏi lại y hệt."""
    assert "gọi lại" in chon_cau_nhac(1).lower()


def test_chon_cau_nhac_khong_vo_khi_qua_so_luong():
    assert chon_cau_nhac(99) in CAU_NHAC


# --- Đếm im lặng phải bắt đầu từ lúc PHÁT XONG ----------------------------
#
# Cuộc gọi thật `55069e44` (06-09-2026): cả 3 câu trả lời đều bị một câu nhắc
# bám ngay sau, khách phàn nàn "AI cứ gọi liên tục". Nguyên nhân: mốc đặt tại
# `turn_complete` (mô hình sinh xong chữ) trong khi tiếng còn phát tiếp 5-8 giây.

def test_con_tieng_thi_moc_bi_doi_len_hien_tai():
    from backend.services.nhac_im_lang import moc_dem_im
    assert moc_dem_im(100.0, True, 137.0) == 137.0


def test_het_tieng_thi_giu_nguyen_moc():
    from backend.services.nhac_im_lang import moc_dem_im
    assert moc_dem_im(137.0, False, 140.0) == 137.0


def test_chua_co_luot_nao_xong_thi_van_la_none():
    from backend.services.nhac_im_lang import moc_dem_im
    assert moc_dem_im(None, False, 10.0) is None
    assert moc_dem_im(None, True, 10.0) is None


def test_dong_ho_khong_chay_trong_luc_con_phat():
    """Câu trả lời dài 8 giây thì sau khi phát xong, đồng hồ im lặng phải bằng 0,
    chứ không phải đã chạy sẵn 8 giây."""
    from backend.services.nhac_im_lang import moc_dem_im
    moc = 100.0                      # turn_complete lúc t=100
    for t in range(101, 109):        # 8 giây còn đang phát
        moc = moc_dem_im(moc, True, float(t))
    assert moc == 108.0
    assert 108.5 - moc < 1.0, "đồng hồ phải bắt đầu từ lúc phát xong"


# --- Ba vế của "lượt đang được xử lý" -------------------------------------
#
# Thiếu vế nào cũng để lọt một quãng cho câu nhắc chen vào giữa lượt.

def test_dang_xu_ly_bat_du_ba_ve():
    from backend.services.nhac_im_lang import dang_xu_ly_luot
    assert dang_xu_ly_luot(khach_dang_noi=True, luot_dang_chay=False,
                           luot_task_con_chay=False) is True
    assert dang_xu_ly_luot(khach_dang_noi=False, luot_dang_chay=True,
                           luot_task_con_chay=False) is True
    # Quãng STT+LLM: khách nói xong, mảnh tiếng đầu chưa về -> hai cờ kia TẮT.
    assert dang_xu_ly_luot(khach_dang_noi=False, luot_dang_chay=False,
                           luot_task_con_chay=True) is True


def test_ranh_that_thi_moi_duoc_nhac():
    from backend.services.nhac_im_lang import dang_xu_ly_luot
    assert dang_xu_ly_luot(khach_dang_noi=False, luot_dang_chay=False,
                           luot_task_con_chay=False) is False
