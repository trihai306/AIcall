"""Lấy tình huống NGAY khi nó có, đừng chờ cả tác vụ đoán trước xong.

Tác vụ `speculate._run()` làm năm việc nối nhau:

    STT -> ghi spec_stt -> CHẤM TÌNH HUỐNG -> RAG -> LLM soạn sẵn

Thứ câu đệm cần xong ở việc thứ ba. Nhưng `_send_filler` chờ bằng
`asyncio.wait({spec_task})`, tức chờ tới khi CẢ tác vụ xong - kể cả RAG và LLM,
hai thứ nó không dùng. Nên nó đốt trọn ngân sách chờ.

Đo trên cuộc gọi thật 0396130621 (10:59, phiên e2e7034c): ngân sách 650ms, và
"AI bắt đầu nói sau 754ms" ở lượt 1, "745ms" ở lượt 2 - tức lần nào cũng chờ
hết giờ. Trong khi phiên âm cuối câu chỉ mất 297-365ms.
"""
import asyncio
import time

from backend.services.filler_pick import cho_den_khi


def test_ve_ngay_khi_dieu_kien_dung():
    """Điều kiện đúng ở 60ms thì phải về ở ~60ms, không phải 600ms."""
    async def kich_ban():
        xong = []
        async def _dat_som():
            await asyncio.sleep(0.06)
            xong.append(1)
        asyncio.create_task(_dat_som())
        t = time.perf_counter()
        cho = await cho_den_khi(lambda: bool(xong), tran_ms=600)
        return (time.perf_counter() - t) * 1000, cho

    that, bao = asyncio.run(kich_ban())
    assert that < 200, f"chờ {that:.0f}ms trong khi điều kiện đúng từ 60ms"
    assert bao < 200


def test_dieu_kien_khong_bao_gio_dung_thi_dung_o_tran():
    async def kich_ban():
        t = time.perf_counter()
        cho = await cho_den_khi(lambda: False, tran_ms=120)
        return (time.perf_counter() - t) * 1000, cho

    that, bao = asyncio.run(kich_ban())
    assert 100 <= that < 400, f"trần 120ms mà chờ {that:.0f}ms"
    assert bao >= 100


def test_dung_ngay_khong_cho_neu_da_dung_san():
    async def kich_ban():
        return await cho_den_khi(lambda: True, tran_ms=600)
    assert asyncio.run(kich_ban()) < 30
