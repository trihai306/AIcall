"""Hồi quy cho hai cửa ưu tiên khi khởi tạo tiếng cuộc gọi."""

import asyncio
from types import SimpleNamespace

import pytest

from backend.core import service_priority
from backend.pipeline.session_manager import CallSession
from backend.services import adb_service
from backend.services import dung_san_manh_so as dung_san
from backend.services import phone_call_service as phone
from backend.services import tieng_san


class _TTSChao:
    def __init__(self):
        self.da_sinh = []

    async def synthesize(self, text, voice=None):
        self.da_sinh.append((text, voice))
        return b"wav-da-sinh"

    def co_filler(self, _voice):
        return True


class _LLMChao:
    async def stream_response(self, *_args, **_kwargs):
        yield "ok"


def test_tu_choi_noi_cau_sau_khi_bat_may_dong_sach_phien(monkeypatch):
    """Nối TCP trễ hỏng thì không được giữ phiên giả hay xếp lời chào vô chủ."""

    async def scenario():
        tts = _TTSChao()
        pipeline = SimpleNamespace(tts=tts, llm=_LLMChao())
        session = CallSession(
            product="vay tín chấp",
            voice_name="thu",
            scenario={"opening_line": "Dạ em chào anh ạ."},
        )
        bridge = phone.PhoneCallBridge(pipeline, session, serial="may-thu")
        bridge.running = True
        bridge._da_mo_o_cam = False

        async def refuse_connection():
            raise ConnectionRefusedError("voice bridge chưa nhận kết nối")

        async def must_not_play(_wav):
            raise AssertionError("không có socket mà vẫn phát lời chào")

        bridge._mo_o_cam = refuse_connection
        bridge.play = must_not_play
        manager = phone.PhoneCallManager()
        manager._calls["may-thu"] = bridge

        class _VoKhongMoDuoc:
            def __init__(self, _serial):
                pass

            async def mo(self):
                return False

        da_dung_bridge = []
        lan_dat_duong_tiem = []

        async def precise_state(_serial):
            return 1, "đã nhấc máy"

        async def set_injection(_serial, enabled, **_kwargs):
            lan_dat_duong_tiem.append(enabled)
            return True, f"injection={enabled}"

        async def stop_bridge(serial, port):
            da_dung_bridge.append((serial, port))

        monkeypatch.setattr(adb_service, "VoRootSan", _VoKhongMoDuoc)
        monkeypatch.setattr(adb_service, "precise_call_state", precise_state)
        monkeypatch.setattr(adb_service, "set_uplink_injection", set_injection)
        monkeypatch.setattr(adb_service, "stop_bridge", stop_bridge)
        monkeypatch.setattr(phone.settings, "phone_do_noi_may_tai_cho", False)
        monkeypatch.setattr(phone.settings, "phone_tat_mic_khi_do_chuong", False)
        monkeypatch.setattr(phone.settings, "phone_doc_lai_duong_tiem", False)
        # Nếu bỏ qua False từ `mo_duong_tieng`, nhánh cũ sẽ xếp đúng 5 khung
        # im trước lời chào vào hàng không có writer.
        monkeypatch.setattr(phone.settings, "phone_dem_im_truoc_chao_ms", 100)
        monkeypatch.setattr(phone.settings, "phone_cho_alo_ms", 0)
        monkeypatch.setattr(phone.settings, "ngu_canh_tron_tai_lieu", True)

        await manager.chao_khi_bat_may("may-thu", cho_toi_da=0.1)

        assert manager.get("may-thu") is None
        assert bridge.running is False
        assert bridge.writer is None and bridge._tasks == []
        assert bridge._out.qsize() == 0
        assert lan_dat_duong_tiem == [True, False]
        assert da_dung_bridge == [("may-thu", bridge.port)]
        assert len(tts.da_sinh) == 1, "lời chào vẫn được dựng sẵn lúc đổ chuông"

    asyncio.run(scenario())


def test_dung_san_manh_so_kiem_tra_lai_luot_khach_sau_khi_lay_khoa_gpu(monkeypatch):
    """Lượt khách đặt chỗ trong lúc worker chờ GPU phải chặn lần sinh kế tiếp."""

    async def scenario():
        da_sinh = []

        class _TTS:
            _is_loaded = True

            def _giong_thuc(self, _voice):
                return "thu"

        async def dung_manh(_tts, text, voice):
            da_sinh.append((text, voice))
            return b"wav"

        monkeypatch.setattr(dung_san, "cac_manh_can_dung", lambda: ["mảnh một"])
        monkeypatch.setattr(tieng_san.kho_tieng_san, "lay_manh",
                            lambda *_args: None)
        monkeypatch.setattr(tieng_san.kho_tieng_san, "dung_manh", dung_manh)
        monkeypatch.setattr(phone.phone_calls, "status", lambda: [])
        monkeypatch.setattr(service_priority, "CUSTOMER_COOLDOWN_S", 0.0)

        gate = service_priority.background_gpu_lock()
        token = object()
        await gate.acquire()
        task = asyncio.create_task(dung_san.dung_san(SimpleNamespace(tts=_TTS()), 0))
        try:
            # Worker đã qua cửa đầu nhưng đang chờ cổng GPU.
            await asyncio.sleep(0.05)
            assert not task.done() and not da_sinh
            service_priority.reserve_customer_turn(token)
            gate.release()
            # Worker lấy được khóa rồi phải kiểm tra lại, thấy lượt khách và
            # nhường; hàm native dựng mảnh tuyệt đối chưa được gọi.
            await asyncio.sleep(0.05)
            assert not da_sinh
            assert not task.done()
        finally:
            service_priority.release_customer_turn(token)
            if gate.locked():
                gate.release()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())
