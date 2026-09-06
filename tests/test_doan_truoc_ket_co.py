"""Cờ `spec_running` phải hạ khi bản đoán bị dọn giữa chừng.

Vì sao có tệp này: `clear_speculation()` đặt `spec_task = None`, còn `finally`
của bản đoán chỉ hạ cờ khi `spec_task is current_task()`. Hai điều đó gặp nhau
thì cờ KẸT True vĩnh viễn, và từ đó mọi lần `speculate(ngay=False)` đều thoát
sớm ngay ở dòng đầu - tức đoán trước GIỮA CHỪNG chết hẳn tới cuối cuộc gọi.

Hậu quả đo trên cuộc gọi thật 06-09-2026: 4/5 lượt ghi "KHÔNG phân loại được -
chưa có spec_stt", nên câu đệm luôn rơi về rổ chung dù khách hỏi thẳng lãi suất.
"""
import asyncio

from backend.pipeline.session_manager import CallSession


def test_don_ban_doan_giua_chung_thi_ha_co():
    """Dọn lúc bản đoán CÒN ĐANG CHẠY - đây là đường làm kẹt cờ."""
    async def kich_ban():
        s = CallSession()

        async def _chay():
            try:
                await asyncio.sleep(0.2)      # thay cho STT 375-830ms
            finally:
                # sao y `finally` của speculate._run()
                if s.spec_task is asyncio.current_task():
                    s.spec_running = False

        s.spec_running = True
        s.spec_task = asyncio.create_task(_chay())
        await asyncio.sleep(0)                # cho task khởi động
        s.clear_speculation()                 # khách mở miệng -> dọn
        await asyncio.sleep(0.05)             # để `finally` của task cũ chạy
        return s.spec_running

    assert asyncio.run(kich_ban()) is False, (
        "cờ còn treo -> mọi lần đoán trước sau đó thoát sớm, "
        "câu đệm mất hẳn đường lấy chữ để chấm tình huống")


def test_don_khi_khong_co_ban_nao_chay_van_ha_co():
    """Cờ sót lại từ lượt trước cũng phải sạch sau khi dọn."""
    s = CallSession()
    s.spec_running = True
    s.clear_speculation()
    assert s.spec_running is False
