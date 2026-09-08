"""Câu lệnh bật cầu tiếng: tham số `usage` quyết định tiếng ra loa nào.

`BridgeService.java` nhận `--ei usage`: 1 = VOICE_COMMUNICATION (loa áp tai,
đường thật tiêm vào cuộc gọi), 2 = MEDIA (loa ngoài). Chính chú thích trong đó
ghi "loa áp tai quá nhỏ để chính micro của máy nghe lại, không đo được vòng âm
học" - và đó đúng là thứ đã xảy ra: đo vòng trong máy ngày 07-09 ra 8/8 lần
không thấy chirp vọng về, dải chirp trong mic còn GIẢM (0,069 -> 0,042).

Mặc định phải giữ nguyên là KHÔNG truyền gì, để đường gọi thật không đổi hành vi.
"""
from backend.services.adb_service import _lenh_bridge


def test_mac_dinh_khong_truyen_usage():
    lenh = _lenh_bridge("SERIAL", port=8123, src=3)
    assert "usage" not in lenh


def test_usage_loa_ngoai_duoc_truyen_dung():
    lenh = _lenh_bridge("SERIAL", port=8123, src=1, usage=2)
    i = lenh.index("usage")
    assert lenh[i - 1] == "--ei" and lenh[i + 1] == "2"


def test_van_giu_nguyen_serial_src_port():
    lenh = _lenh_bridge("ABC123", port=9000, src=4, usage=2)
    assert "ABC123" in lenh
    assert lenh[lenh.index("src") + 1] == "4"
    assert lenh[lenh.index("port") + 1] == "9000"


# --- đệm AudioTrack trên máy ----------------------------------------------
# `BridgeService.demXuongMs` mặc định 500ms. Nó là KÍCH THƯỚC đệm, chưa chắc là
# độ trễ nó gây ra - MODE_STREAM phát ngay khi có dữ liệu chứ không chờ đầy.
# Muốn biết nó đóng góp bao nhiêu vào 700ms thì phải hạ được nó xuống mà đo.

def test_khong_truyen_dem_xuong_thi_may_giu_mac_dinh():
    assert "dem_xuong" not in _lenh_bridge("S", port=8123, src=3)


def test_dem_xuong_duoc_truyen_dung():
    lenh = _lenh_bridge("S", port=8123, src=1, dem_xuong=100)
    i = lenh.index("dem_xuong")
    assert lenh[i - 1] == "--ei" and lenh[i + 1] == "100"


def test_dem_xuong_va_usage_dung_duoc_cung_luc():
    lenh = _lenh_bridge("S", port=8123, src=1, usage=2, dem_xuong=0)
    assert lenh[lenh.index("usage") + 1] == "2"
    assert lenh[lenh.index("dem_xuong") + 1] == "0"
