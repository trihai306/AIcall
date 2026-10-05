"""Verify the live LLM streaming entry point uses checked banking conditions."""
import asyncio

import pytest

pytest.importorskip("ollama")
from backend.services.llm_service import LLMService  # noqa: E402


def test_stream_answers_explicit_age_from_source_without_model_guessing():
    service = LLMService.__new__(LLMService)
    service.model = "qwen3.5:9b"
    system = "THÔNG TIN THAM KHẢO:\n- Công dân Việt Nam, từ 22 - 65 tuổi"
    messages = [{"role": "user", "content": "Anh 21 tuổi, riêng điều kiện tuổi vay nhà đạt chưa?"}]

    async def collect():
        return "".join([part async for part in service.stream_response(messages, system)])

    answer = asyncio.run(collect())
    assert "21 tuổi chưa đạt" in answer
    assert "22 tuổi" in answer
