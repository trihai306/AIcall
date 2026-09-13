"""LLM trả stream rỗng thì cuộc gọi vẫn phải có câu trả lời."""

from pathlib import Path

from backend.pipeline.hoi_lai import CAU_LLM_RONG


def test_cau_lui_co_noi_dung_va_khong_hua_suong():
    assert CAU_LLM_RONG.strip()
    assert "chưa thể khẳng định" in CAU_LLM_RONG
    assert "báo lại" not in CAU_LLM_RONG


def test_pipeline_that_dung_cau_lui_khi_stream_rong():
    src = (Path(__file__).resolve().parents[1]
           / "backend" / "pipeline" / "streaming_pipeline.py").read_text(
               encoding="utf-8")
    assert 'text_buffer = CAU_LLM_RONG' in src
    assert 'metrics["llm_rong"] = True' in src
