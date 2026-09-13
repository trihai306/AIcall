"""Guard against false evaluation claims and wrong channel selection."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location(
    "do_asr_call_that", Path(__file__).resolve().parents[1] / "scripts/do_asr_call_that.py")
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def test_left_customer_never_stereo_average():
    stereo = np.column_stack([np.ones(100) * 0.1, np.ones(100) * 0.9])
    assert np.allclose(M.customer_channel(stereo), 0.1)


def test_mono_channel_not_guessed():
    with pytest.raises(ValueError):
        M.customer_channel(np.ones(100))


def test_unverified_transcript_never_becomes_ground_truth():
    result = M.reference_scores({"x": "anh vay bốn trăm"}, [
        {"sample_id": "x", "text": "anh vay bốn trăm", "human_verified": False}])
    assert result["wer"] is None and result["cer"] is None


def test_diacritics_are_preserved_in_scoring():
    result = M.reference_scores({"x": "vay tin chấp"}, [
        {"sample_id": "x", "text": "vay tín chấp", "human_verified": True}])
    assert result["wer"] == pytest.approx(1 / 3)


def test_real_levenshtein_insertion_not_similarity_ratio():
    result = M.reference_scores({"x": "anh muốn vay thêm"}, [
        {"sample_id": "x", "text": "anh muốn vay", "human_verified": True}])
    assert result["wer"] == pytest.approx(1 / 3)


def test_silence_creates_no_speech_excerpts():
    result, _ = M.excerpts(np.zeros(32000, dtype=np.float32), 16000)
    assert result == []


def test_excerpt_bounds_and_preroll():
    audio = np.zeros(64000, dtype=np.float32)
    audio[16000:32000] = np.sin(np.arange(16000) * 0.2) * 0.1
    spans, _ = M.excerpts(audio, 16000)
    assert len(spans) == 1
    a, b = spans[0]
    assert 0 <= a < 16000 < 32000 < b <= len(audio)
