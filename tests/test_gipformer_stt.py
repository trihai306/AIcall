"""Routing and acoustic gate tests; real model tests live in the smoke script."""
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.services.gipformer_stt import GipformerSTT
from backend.services.stt_service import STTService
from backend.config import settings


@pytest.mark.parametrize("audio", [np.zeros(0, dtype=np.float32),
    np.zeros(16000, dtype=np.float32), np.full(16000, 1e-6, dtype=np.float32),
    np.array([np.nan], dtype=np.float32)])
def test_digital_silence_or_invalid_is_not_speech(audio):
    assert not GipformerSTT._has_speech(audio)


def test_missing_model_fails_readiness(tmp_path):
    with pytest.raises(FileNotFoundError):
        GipformerSTT(tmp_path).load()


def test_gate_keeps_whole_clip_and_true_short_reply(monkeypatch, tmp_path):
    import io
    import soundfile as sf
    samples = np.sin(np.arange(16000, dtype=np.float32) * .12) * .1
    buf = io.BytesIO()
    sf.write(buf, samples, 16000, format="WAV", subtype="FLOAT")
    accepted = []
    stream = SimpleNamespace(result=SimpleNamespace(text="Ừ"),
                             accept_waveform=lambda sr, audio: accepted.append((sr, audio)))
    decoder = GipformerSTT(tmp_path)
    decoder.recognizer = SimpleNamespace(create_stream=lambda: stream,
                                         decode_streams=lambda streams: None)
    monkeypatch.setattr(decoder, "_has_speech", lambda audio: True)
    assert decoder.transcribe(buf.getvalue()) == "ừ"
    assert accepted[0][0] == 16000
    assert np.array_equal(accepted[0][1], samples)


def test_non_speech_never_reaches_decoder(monkeypatch, tmp_path):
    import io
    import soundfile as sf
    buf = io.BytesIO()
    sf.write(buf, np.zeros(8000), 8000, format="WAV")
    decoder = GipformerSTT(tmp_path)
    def forbidden():
        raise AssertionError("decoder was invoked for silence")
    decoder.recognizer = SimpleNamespace(create_stream=forbidden)
    assert decoder.transcribe(buf.getvalue()) == ""


def test_stereo_is_rejected_instead_of_mixing_bot_into_customer(tmp_path):
    import io
    import soundfile as sf
    buf = io.BytesIO()
    sf.write(buf, np.zeros((8000, 2)), 8000, format="WAV")
    with pytest.raises(ValueError, match="mono"):
        GipformerSTT(tmp_path).transcribe(buf.getvalue())


def test_live_gipformer_does_not_use_whisper_prompt_or_text_repairs(monkeypatch):
    monkeypatch.setattr(settings, "stt_engine", "gipformer")

    async def run():
        service = STTService()
        received = []
        def decode(wav):
            received.append(wav)
            return "ừ"  # A genuine short reply is not blacklisted by its text.
        service._gipformer = SimpleNamespace(transcribe=decode)
        service._goi_whisper = AsyncMock(side_effect=AssertionError("wrong engine"))
        try:
            assert await service.transcribe(b"\x00\x00" * 800, 8000) == "ừ"
            assert received[0].startswith(b"RIFF")
            service._goi_whisper.assert_not_called()
        finally:
            await service.close()
    asyncio.run(run())


def test_gipformer_empty_result_does_not_retry_or_invent_words(monkeypatch):
    monkeypatch.setattr(settings, "stt_engine", "gipformer")
    async def run():
        service = STTService()
        seen = []
        def decode(wav):
            seen.append(wav)
            return ""
        service._gipformer = SimpleNamespace(transcribe=decode)
        try:
            assert await service.transcribe(b"\0\0" * 1600) == ""
            assert len(seen) == 1
        finally:
            await service.close()
    asyncio.run(run())


def test_word_timestamps_still_use_phowhisper(monkeypatch):
    monkeypatch.setattr(settings, "stt_engine", "gipformer")
    async def run():
        service = STTService()
        expected = [{"words": [{"word": "vay", "start": 0.1, "end": 0.4}]}]
        import httpx
        response = httpx.Response(200, json={"segments": expected},
                                  request=httpx.Request("POST", "http://localhost/inference"))
        service.client.post = AsyncMock(return_value=response)
        try:
            assert await service.moc_tung_chu(b"RIFF") == expected
            assert service.client.post.call_args.args[0] == service.base_url + "/inference"
        finally:
            await service.close()
    asyncio.run(run())


def test_gipformer_health_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "stt_engine", "gipformer")
    async def run():
        service = STTService()
        def unavailable():
            raise FileNotFoundError("model unavailable")
        service._gipformer = SimpleNamespace(load=unavailable)
        try:
            assert not await service.health_check()
        finally:
            await service.close()
    asyncio.run(run())
