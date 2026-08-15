"""Vòng theo dõi cuộc gọi - dùng chung cho gọi tự động và gọi tay.

Tới 2026-08-12 vòng này là phương thức riêng của bộ quay số tự động, còn nút
"Gọi" ở trang Danh bạ quay số xong là trả về luôn. Khách tắt máy thì không có
gì phát hiện: trạng thái số kẹt ở "đang gọi", phiên không được chốt, và cầu
tiếng vẫn mở nên máy đó không gọi được số tiếp theo.

Bộ test này giữ hai thứ: bảng quyết định của vòng lặp (đường tự động đang dựa
vào, không được làm hỏng khi tách hàm), và khả năng chạy KHÔNG có chiến dịch
(`campaign=None`) - thứ chỉ đường gọi tay cần.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from backend.services import campaign_runner as cr


class GiaPhien:
    def __init__(self, hop_thu=False):
        self.phone = "0900000000"
        self.la_hop_thu_thoai = hop_thu


MAY_ADB = {"kind": "adb", "address": "emulator-5554", "device_id": "d1"}


@pytest.fixture(autouse=True)
def _khong_chuyen_tiep(monkeypatch):
    """Mặc định không có lý do nối máy cho chuyên viên."""
    monkeypatch.setattr(cr.transfer_service, "can_chuyen_tiep", lambda s: None)


@pytest.fixture(autouse=True)
def _tham_nhanh(monkeypatch):
    """Bỏ nhịp thăm dò thật, không thì mỗi test mất vài giây."""
    monkeypatch.setattr(cr, "_NHIP_THAM", 0.0)


def _gia_trang_thai(monkeypatch, day: list[int]):
    """Trả lần lượt từng mã trong `day`; hết thì giữ mã cuối."""
    from backend.services import adb_service
    con = list(day)

    async def _doc(serial):
        ma = con.pop(0) if len(con) > 1 else con[0]
        return ma, f"mã {ma}"

    monkeypatch.setattr(adb_service, "precise_call_state", _doc)


def _chay(device, session, campaign):
    return asyncio.run(cr.cho_ket_qua(device, session, campaign, asyncio.Event()))


# --- bảng quyết định -----------------------------------------------------

def test_bat_may_roi_tat_may_la_done(monkeypatch):
    """Đúng thứ người dùng báo: khách nghe rồi cúp - phải kết thúc, không treo."""
    _gia_trang_thai(monkeypatch, [1, 1, 0])
    assert _chay(MAY_ADB, GiaPhien(), {}) == "done"


def test_chua_kip_LEN_thi_khong_duoc_ket_luan_busy(monkeypatch):
    """Máy báo "rảnh" ngay sau khi bấm số KHÔNG có nghĩa là bận.

    ĐÂY LÀ BẢN VÁ 14-08-2026, và test cũ khoá đúng cái hành vi HỎNG. Trước đó
    vòng theo dõi chạy ngay sau khi quay số, lúc tổng đài máy vẫn báo 0 (rảnh)
    vì chưa kịp chuyển trạng thái. Lần đọc ĐẦU TIÊN rơi vào nhánh "rảnh mà chưa
    tới 8 giây -> busy", hàm trả 'busy' và nơi gọi TỰ CÚP MÁY - đúng một giây
    sau khi bấm gọi:

        08:42:12  ADB dialled 0396130621
        08:42:13  đã đóng cầu tiếng (0 lượt)
        08:42:13  cuộc gọi tay kết thúc: busy

    Người dùng thấy triệu chứng "bấm gọi được mà không nghe thấy gì". Luật đúng:
    chỉ được đọc "rảnh" thành ĐÃ NGẮT sau khi đã thấy cuộc gọi LÊN.

    Quá `_CHO_LEN_S` mà vẫn chưa lên thì là quay số hỏng thật -> no_answer,
    KHÔNG phải busy.
    """
    monkeypatch.setattr(cr, "_CHO_LEN_S", 0.05)
    _gia_trang_thai(monkeypatch, [0])
    assert _chay(MAY_ADB, GiaPhien(), {}) == "no_answer"


def test_do_chuong_roi_ngat_som_moi_la_busy(monkeypatch):
    """Đã LÊN rồi mới ngắt, dưới 8 giây - đây mới đúng là máy bận."""
    _gia_trang_thai(monkeypatch, [3, 0])
    assert _chay(MAY_ADB, GiaPhien(), {}) == "busy"


def test_do_chuong_mai_khong_ai_nghe_la_no_answer(monkeypatch):
    monkeypatch.setattr(cr, "_CHO_BAT_MAY_S", 0.0)
    _gia_trang_thai(monkeypatch, [2])       # đổ chuông, không bao giờ sang 1
    assert _chay(MAY_ADB, GiaPhien(), {}) == "no_answer"


def test_qua_tran_thoi_gian_thi_dung_lai(monkeypatch):
    """Không có trần thì một cuộc bị bỏ quên giữ máy đó vô hạn."""
    monkeypatch.setattr(cr, "_TRAN_CUOC_GOI_S", 0.0)
    _gia_trang_thai(monkeypatch, [1])       # nói mãi không dứt
    assert _chay(MAY_ADB, GiaPhien(), {}) == "done"


def test_hop_thu_thoai_thi_cup_may(monkeypatch):
    _gia_trang_thai(monkeypatch, [1])
    assert _chay(MAY_ADB, GiaPhien(hop_thu=True), {"on_voicemail": "hangup"}) == "voicemail"


def test_lenh_dung_lam_thoat_vong(monkeypatch):
    """Dừng chiến dịch phải tỉnh ngay, không đợi hết trần.

    Bật cờ trước khi vào vòng thì vòng không chạy lần nào, nên hàm chưa từng
    thấy khách bắt máy - trả `no_answer` là đúng, không phải `done`. Điều test
    này giữ là nó THOÁT chứ không treo tới hết `_TRAN_CUOC_GOI_S`.
    """
    monkeypatch.setattr(cr, "_TRAN_CUOC_GOI_S", 9999.0)
    _gia_trang_thai(monkeypatch, [1])
    dung = asyncio.Event()
    dung.set()
    ra = asyncio.run(cr.cho_ket_qua(MAY_ADB, GiaPhien(), {}, dung))
    assert ra == "no_answer"


# --- gọi tay: không có chiến dịch nào -----------------------------------

def test_chay_duoc_khi_khong_co_chien_dich(monkeypatch):
    """Gọi tay ngoài chiến dịch thì `campaign` là None.

    Bản cũ đọc thẳng `campaign.get("on_voicemail")` nên None là vỡ ngay giữa
    cuộc gọi - mà vỡ trong task nền thì không ai thấy, cuộc gọi lại treo y như
    lúc chưa có vòng theo dõi.
    """
    _gia_trang_thai(monkeypatch, [1, 1, 0])
    assert _chay(MAY_ADB, GiaPhien(), None) == "done"


def test_hop_thu_thoai_khong_co_chien_dich_van_cup_may(monkeypatch):
    """Không có chiến dịch thì lấy mặc định 'hangup', không được ném lỗi."""
    _gia_trang_thai(monkeypatch, [1])
    assert _chay(MAY_ADB, GiaPhien(hop_thu=True), None) == "voicemail"


# --- thiết bị không đọc được trạng thái ---------------------------------

def test_may_khong_phai_adb_thi_cho_het_gio(monkeypatch):
    monkeypatch.setattr(cr, "_TRAN_CUOC_GOI_S", 0.0)
    assert _chay({"kind": "http", "device_id": "d2"}, GiaPhien(), None) == "done"
