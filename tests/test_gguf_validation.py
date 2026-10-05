from pathlib import Path

from training.llm.deploy_ollama import tim_gguf, valid_gguf


def test_partial_export_is_not_selected(tmp_path: Path):
    partial = tmp_path / "candidate.Q4_K_M.gguf"
    partial.write_bytes(b"\x00" * 128)
    assert not valid_gguf(partial)
    assert tim_gguf(tmp_path) is None


def test_header_and_sane_size_are_required(tmp_path: Path):
    candidate = tmp_path / "candidate.Q4_K_M.gguf"
    with candidate.open("wb") as stream:
        stream.write(b"GGUF")
        stream.truncate(101 * 1024 * 1024)
    assert valid_gguf(candidate)
    assert tim_gguf(tmp_path) == candidate
