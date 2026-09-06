"""`F5TTSService` phải cho biết worker F5 đang bận hay rảnh.

VÌ SAO CẦN: executor chỉ có ĐÚNG MỘT worker (`tts_service.py`, "F5-TTS không an
toàn đa luồng"). Việc dựng sẵn tiếng trong quãng im mà chen vào lúc worker đang
sinh tiếng cho lượt đang phát sẽ đẩy lùi mảnh kế của lượt đó - tạo quãng im
GIỮA CÂU, đúng thứ bộ gộp mảnh đang cố tránh.

Không có API nào cho biết điều này. Đừng đọc `_executor._work_queue.qsize()`:
đó là nội bộ, và nó KHÔNG đếm job đang chạy.
"""
import asyncio

from backend.services.tts_service import F5TTSService


def test_ranh_khi_khong_lam_gi():
    tts = F5TTSService.__new__(F5TTSService)
    tts._dang_ban = 0
    assert tts.dang_ban == 0


def test_dem_len_khi_dang_sinh_va_ve_0_khi_xong():
    async def kich_ban():
        tts = F5TTSService.__new__(F5TTSService)
        tts._dang_ban = 0
        thay = []

        async def viec():
            with tts._ghi_ban():
                thay.append(tts.dang_ban)
                await asyncio.sleep(0.02)

        await viec()
        return thay[0], tts.dang_ban

    trong, sau = asyncio.run(kich_ban())
    assert trong == 1, "đang sinh mà báo rảnh -> dựng sẵn sẽ chen vào"
    assert sau == 0


def test_ve_0_ca_khi_no_loi():
    tts = F5TTSService.__new__(F5TTSService)
    tts._dang_ban = 0
    try:
        with tts._ghi_ban():
            raise RuntimeError("F5 hỏng")
    except RuntimeError:
        pass
    assert tts.dang_ban == 0, "nổ lỗi mà cờ kẹt thì không bao giờ dựng sẵn nữa"
