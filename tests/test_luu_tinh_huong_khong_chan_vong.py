"""Lưu tình huống KHÔNG được chặn vòng lặp sự kiện.

CUỘC GỌI THẬT 06-09-2026 (phiên 78913468). Người dùng: "đang nói mà tự nhiên
ngắt nói luôn dù chưa có ai gọi hay gì". Log:

    16:21:11  Đã nhúng lại ví dụ của 34 tình huống    <- bấm Lưu trên giao diện
    16:21:11  TTS: 8763ms                             <- thường 300-500ms
    16:21:11  khách cắt lời — bỏ 328 khung tiếng AI   <- 6,5 giây tiếng bị vứt

`_nhung_lai_vi_du()` gọi `rag.embed()` 34 lần ĐỒNG BỘ, mà nó chạy thẳng trong
`async def luu_tinh_huong`. Suốt lúc đó vòng lặp sự kiện đứng im: bộ đẩy tiếng
xuống điện thoại không chạy được, `await` của TTS không nối lại được. Khách nghe
im lặng, tưởng rớt máy nên "a lô" - và chính tiếng đó cắt lời, vứt nốt phần
tiếng đang xếp hàng.

GIẢ THUYẾT ĐÃ BÁC BỎ: ban đầu tôi đổ cho việc dựng kho câu đệm 5754 clip tranh
GPU. Số đo bác bỏ - log ghi "5754 đọc từ đĩa, 0 dựng mới", tức nó không sinh
tiếng lần nào.
"""
import asyncio
import time


def test_luu_tinh_huong_khong_lam_dung_vong_lap(monkeypatch):
    from backend.api import fillers

    def ap_dung_cham(*_a, **_kw):
        # thay cho: nap_lai() + `rag.embed()` trên GPU
        time.sleep(0.30)

    monkeypatch.setattr(fillers, "_ap_dung", ap_dung_cham)

    async def kich_ban():
        nhip = 0

        async def dem():
            nonlocal nhip
            while True:
                await asyncio.sleep(0.01)
                nhip += 1

        t = asyncio.create_task(dem())
        await fillers._ap_dung_nen()
        t.cancel()
        return nhip

    nhip = asyncio.run(kich_ban())
    assert nhip >= 10, (
        f"vòng lặp sự kiện đứng im trong lúc nhúng lại (chỉ {nhip} nhịp/0,3s) "
        "-> tiếng xuống điện thoại tắc, khách nghe AI ngắt giữa chừng")
