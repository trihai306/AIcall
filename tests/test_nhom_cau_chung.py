"""Nhóm câu CHUNG: những câu luôn dùng được, phát khi không nhận ra chủ đề.

Người dùng 06-09-2026: "xem phần câu đệm dựng những câu luôn cần nói cho tôi để
không bị null", và "làm ở nhóm câu chứ không phải ở cuối câu - cái cuối câu đó
bỏ đi vì khi nó nối hay vào sai".

Khác câu đuôi ở hai điểm quyết định:
  - ĐỨNG MỘT MÌNH, không ghép vào sau mẩu mở đầu -> không có chỗ nối để sai
  - RẺ: mỗi câu là một clip, trong khi câu đuôi nhân với 142 mẩu (1430 clip)
"""
import inspect

from backend.services.filler_store import MA_NHOM_CHUNG


def test_ma_nhom_chung_on_dinh():
    """Mã này đi vào tên thư mục clip trên đĩa. Đổi nó là mọi clip đã dựng thành
    mồ côi và khách nghe im lặng cho tới lần dựng lại."""
    assert MA_NHOM_CHUNG == "chung"


def test_pick_filler_roi_ve_nhom_chung_TRUOC_ro_duoi():
    """Thứ tự rơi phải là: tình huống khớp -> nhóm chung -> đuôi trần.

    Đọc mã nguồn vì `pick_filler` cần cache TTS thật để chạy. Thứ tự chính là
    thứ đang được canh - đặt nhóm chung SAU rổ đuôi thì nó không bao giờ tới
    lượt ở những máy còn câu đuôi.
    """
    from backend.services import tts_service
    src = inspect.getsource(tts_service)
    assert 'for th in (id_tinh_huong, MA_NHOM_CHUNG, ""):' in src, (
        "chuỗi rơi của pick_filler đã đổi - nhóm chung phải nằm giữa")


def _nguon_khong_nhung_nhom_chung(mod) -> bool:
    src = inspect.getsource(mod)
    return "t.id != MA_NHOM_CHUNG" in src


def test_ca_HAI_cho_nhung_deu_bo_nhom_chung():
    """Bẫy hai-nơi-làm-cùng-việc: ví dụ tình huống được nhúng ở HAI chỗ -
    lúc khởi động (`core/startup`) và lúc sửa trên giao diện (`api/fillers`).

    Sót một chỗ thì nhóm chung lọt vào bộ chấm điểm, cạnh tranh cosine với các
    tình huống thật và có thể THẮNG - khách hỏi lãi suất lại nghe câu trung
    tính thay vì "Dạ về lãi suất thì,". Và vì chỗ sót là lúc KHỞI ĐỘNG nên nó
    âm thầm quay về sau mỗi lần restart.
    """
    from backend.api import fillers
    from backend.core import startup
    thieu = [m.__name__ for m in (fillers, startup)
             if not _nguon_khong_nhung_nhom_chung(m)]
    assert not thieu, f"những chỗ này còn nhúng nhóm chung vào bộ chấm điểm: {thieu}"
