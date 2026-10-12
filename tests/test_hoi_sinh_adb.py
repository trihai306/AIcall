"""Máy rớt xuống `offline` giữa cuộc gọi phải được kéo lên lại, không nằm chờ."""
import asyncio

from backend.services import adb_service


def _gia_run(trang_thai: list[str], lenh: list[tuple]):
    async def _run(*args, timeout=None):
        lenh.append(args)
        if args[0] == "reconnect":
            return 0, "reconnecting", ""
        if "get-state" in args:
            tt = trang_thai.pop(0) if len(trang_thai) > 1 else trang_thai[0]
            return (0, "device\n", "") if tt == "device" else (1, "", "error: device offline")
        return 0, "", ""
    return _run


def test_dang_song_thi_khong_reconnect(monkeypatch):
    lenh = []
    monkeypatch.setattr(adb_service, "_run", _gia_run(["device"], lenh))
    assert asyncio.run(adb_service.hoi_sinh_adb("may_a")) is True
    assert not any(a[0] == "reconnect" for a in lenh)


def test_offline_thi_reconnect_roi_cho_len(monkeypatch):
    lenh = []
    adb_service._LAN_HOI_SINH.pop("may_b", None)
    monkeypatch.setattr(adb_service, "_run", _gia_run(["offline", "offline", "device"], lenh))
    assert asyncio.run(adb_service.hoi_sinh_adb("may_b", cho_toi_da=3.0)) is True
    assert sum(a[0] == "reconnect" for a in lenh) == 1


def test_khong_len_thi_bao_that_va_khong_reconnect_don_dap(monkeypatch):
    lenh = []
    adb_service._LAN_HOI_SINH.pop("may_c", None)
    monkeypatch.setattr(adb_service, "_run", _gia_run(["offline"], lenh))
    assert asyncio.run(adb_service.hoi_sinh_adb("may_c", cho_toi_da=0.9)) is False
    assert asyncio.run(adb_service.hoi_sinh_adb("may_c", cho_toi_da=0.5)) is False
    assert sum(a[0] == "reconnect" for a in lenh) == 1      # lần hai còn trong quãng giãn cách
