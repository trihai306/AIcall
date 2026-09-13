"""Prefill câu đệm trên qwen3.5: phải gửi `think=True`, không thì model trả RỖNG.

Đo trên máy Win 13-09-2026, Ollama 0.34.0, `qwen3.5:9b`, cùng một prompt thật:

    /api/chat không prefill, think=False     -> "Dạ lãi suất ... từ 7,9%/năm ạ."
    /api/chat CÓ prefill,   think=False     -> ""            (4/4 lần, cả hai bộ stop)
    /api/chat CÓ prefill,   think=True      -> " theo thông tin bên em là từ 7.9%/năm ạ."  (2/2)

Ollama không chèn khối `<think>\\n\\n</think>` trước tin nhắn assistant cuối khi
think=False, model thấy thiếu khối đó nên dừng ngay ở token đầu. Hậu quả trên
cuộc gọi thật f441bc66: mọi lượt có câu đệm đều rơi về câu lùi "Phần này chưa có
quy định rõ trong tài liệu" dù tài liệu có đủ.

Model không hỗ trợ suy nghĩ (qwen2.5) thì Ollama TỪ CHỐI `think=True`, nên cờ
chỉ bật khi model khai năng lực "thinking".
"""
import asyncio

import pytest

from backend.services import llm_service as ls


class _KhachGia:
    """Ollama client giả: ghi lại kwargs của `chat`, trả một token."""

    def __init__(self, capabilities):
        self.goi = []
        self._caps = capabilities

    async def show(self, model):
        return {"capabilities": self._caps}

    async def chat(self, **kw):
        self.goi.append(kw)

        async def _gen():
            yield {"message": {"content": "ok"}, "done_reason": "stop"}
        return _gen()


async def _chay(svc, prefill):
    return [t async for t in svc.stream_response(
        [{"role": "user", "content": "lãi suất như nào"}], "sys", prefill=prefill)]


@pytest.mark.parametrize("caps, prefill, think", [
    (["completion", "thinking"], "Dạ về lãi suất thì,", True),
    (["completion", "thinking"], "", False),
    (["completion"], "Dạ về lãi suất thì,", False),
    (["completion"], "", False),
])
def test_think_chi_bat_khi_co_prefill_va_model_biet_suy_nghi(caps, prefill, think):
    svc = ls.LLMService()
    svc.client = _KhachGia(caps)
    asyncio.run(svc.kiem_nang_luc())
    asyncio.run(_chay(svc, prefill))
    assert svc.client.goi[-1]["think"] is think
    if prefill:
        assert svc.client.goi[-1]["messages"][-1] == {"role": "assistant", "content": prefill}


def test_chua_kiem_nang_luc_thi_doan_theo_ten_model():
    svc = ls.LLMService()
    svc.client = _KhachGia([])
    svc.model = "qwen3.5:9b"
    asyncio.run(_chay(svc, "Dạ,"))
    assert svc.client.goi[-1]["think"] is True
    svc.model = "qwen2.5:7b"
    asyncio.run(_chay(svc, "Dạ,"))
    assert svc.client.goi[-1]["think"] is False
