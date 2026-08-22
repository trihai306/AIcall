"""Bộ đếm "đói khung" chỉ được đếm TRONG một lượt đang đẻ tiếng.

Lỗi đếm nhầm, bắt được trên cuộc gọi thật 14-08-2026 (phiên 532d6dc2, 54,4 giây,
6 lượt):

    ĐÓI KHUNG 6 lần, tổng 26213ms, lâu nhất 10630ms
    Đệm mồi đang 250ms (settings.phone_dem_mo_ms).

Sáu lượt, sáu lần báo - trùng khít. Và lần 10630ms rơi ngay sau dòng "bỏ đoạn
120ms - ngắn hơn MIN_TURN_MS": khách nói hụt, AI không có gì để đáp, im 10 giây
rồi khách nói tiếp. Đó là khoảng nghỉ tự nhiên giữa hai lượt chứ không phải đứt
giữa câu.

Cơ chế: `dang_giua_cau` chỉ xét `next_at + RESET_GAP`, mà mốc đó vẫn đúng ngay
sau khung CUỐI của một lượt - nên trọn khoảng chờ tới lượt sau bị tính vào.

Con số sai kiểu này đắt hơn là không có số: log tự đổ lỗi cho `phone_dem_mo_ms`
và chỉ người ta đi chỉnh đệm mồi - một chỗ không hỏng.
"""
import inspect

from backend.services import phone_call_service as pcs


def test_co_dieu_kien_luot_dang_chay_trong_vong_phat():
    """Vòng phát phải xét `_luot_dang_chay` khi quyết định 'đang giữa câu'."""
    nguon = inspect.getsource(pcs.PhoneCallBridge)
    i = nguon.find("dang_giua_cau =")
    assert i != -1, "không tìm thấy chỗ tính `dang_giua_cau`"
    assert "_luot_dang_chay" in nguon[i:i + 260], (
        "`dang_giua_cau` không xét `_luot_dang_chay` - khoảng nghỉ giữa hai "
        "lượt sẽ lại bị đếm thành đói khung")


def test_co_mac_dinh_TAT():
    """Chưa có lượt nào thì không được đếm - kể cả lời chào phát thẳng.

    Soi mã nguồn chứ không dựng thể: `__init__` cần pipeline + session thật.
    """
    nguon = inspect.getsource(pcs.PhoneCallBridge.__init__)
    assert "self._luot_dang_chay = False" in nguon


def test_mo_cua_so_khi_co_tieng_va_dong_khi_turn_complete():
    """Cửa sổ đếm: mở ở mảnh tiếng đầu, đóng ở `turn_complete`."""
    nguon = inspect.getsource(pcs)
    i_audio = nguon.find('if kind == "audio"')
    i_turn = nguon.find('elif kind == "turn_complete"')
    assert i_audio != -1 and i_turn != -1
    assert "_luot_dang_chay = True" in nguon[i_audio:i_audio + 700], (
        "nhánh 'audio' không mở cửa sổ đếm")
    assert "_luot_dang_chay = False" in nguon[i_turn:i_turn + 700], (
        "nhánh 'turn_complete' không đóng cửa sổ đếm")
