import asyncio

from backend.services.llm_service import LLMService


class _Client:
    def __init__(self, models):
        self.models = models

    async def list(self):
        return {"models": [{"model": name} for name in self.models]}


def _service(model: str, installed: list[str]) -> LLMService:
    llm = LLMService.__new__(LLMService)
    llm.model = model
    llm.client = _Client(installed)
    return llm


def test_health_check_khong_nhan_nham_cung_ho_model_khac_tag():
    llm = _service("qwen3.5:9b", ["qwen3.5:4b"])
    assert not asyncio.run(llm.health_check())


def test_health_check_nhan_dung_tag():
    llm = _service("qwen3.5:9b", ["qwen3.5:9b"])
    assert asyncio.run(llm.health_check())


def test_health_check_coi_ten_khong_tag_la_latest():
    llm = _service("tuvan-qwen", ["tuvan-qwen:latest"])
    assert asyncio.run(llm.health_check())
