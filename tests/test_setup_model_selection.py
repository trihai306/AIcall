import asyncio

from backend.api import setup
from backend.config import settings


def test_setup_llm_khong_nhan_nham_tag_cung_ho(monkeypatch):
    async def _models():
        return ["qwen3.5:4b"]

    monkeypatch.setattr(setup, "_ollama_models", _models)
    monkeypatch.setattr(settings, "ollama_model", "qwen3.5:9b")
    result = asyncio.run(setup._check_llm())
    assert result["installed"] is False


def test_setup_llm_nhan_ten_khong_tag_la_latest(monkeypatch):
    async def _models():
        return ["tuvan-qwen:latest"]

    monkeypatch.setattr(setup, "_ollama_models", _models)
    monkeypatch.setattr(settings, "ollama_model", "tuvan-qwen")
    result = asyncio.run(setup._check_llm())
    assert result["installed"] is True


def test_setup_gipformer_kiem_dung_bo_file(monkeypatch, tmp_path):
    model_dir = tmp_path / "models" / "stt" / "gip"
    model_dir.mkdir(parents=True)
    for name in ("encoder.onnx", "decoder.onnx", "joiner.onnx", "tokens.txt"):
        (model_dir / name).write_bytes(b"x")

    monkeypatch.setattr(setup, "PROJECT_DIR", tmp_path)
    monkeypatch.setattr(settings, "stt_engine", "gipformer")
    monkeypatch.setattr(settings, "gipformer_model_path", "models/stt/gip")
    result = asyncio.run(setup._check_stt())
    assert result["installed"] is True
    assert "models" in result["detail"]


def test_setup_gipformer_bao_thieu_file(monkeypatch, tmp_path):
    model_dir = tmp_path / "models" / "stt" / "gip"
    model_dir.mkdir(parents=True)
    (model_dir / "tokens.txt").write_text("x", encoding="utf-8")

    monkeypatch.setattr(setup, "PROJECT_DIR", tmp_path)
    monkeypatch.setattr(settings, "stt_engine", "gipformer")
    monkeypatch.setattr(settings, "gipformer_model_path", "models/stt/gip")
    result = asyncio.run(setup._check_stt())
    assert result["installed"] is False
    assert "encoder.onnx" in result["detail"]
