"""Exercise the real response consumer, with observable TTS/cache test doubles.

These tests verify routing and audio metadata, not pronunciation or voice quality.
Every fake waveform carries a distinct sample value identifying its input text.
"""
import asyncio
import base64
import io
import re
import struct
import time
import wave
from types import SimpleNamespace

import pytest

from backend.pipeline import streaming_pipeline as sp
from backend.pipeline.session_manager import CallSession


ANSWER = (
    "Dạ nếu được duyệt 275 triệu đồng trong 24 tháng, "
    "thì phương án vẫn cần thẩm định theo hồ sơ ạ. "
    "Đây chưa phải lịch trả nợ chính thức ạ."
)
FILLER = "Dạ em thông tin ngay cho anh chị,"


def normalize(text):
    return re.sub(r"\s+([.,!?;:])", r"\1", " ".join(text.split()))


@pytest.mark.parametrize("route", ["financial", "profile", "smalltalk", "approved"])
@pytest.mark.parametrize("cached", [False, True])
@pytest.mark.parametrize("with_filler", [False, True])
def test_fixed_answer_audio_text_and_history_agree(monkeypatch, route, cached, with_filler):
    expected = ANSWER[3:] if with_filler else ANSWER
    wave_text, synthesis_calls, lookups, warmed = {}, [], [], []

    def make_audio(text):
        marker = len(wave_text) + 1
        wave_text[marker] = text
        data = io.BytesIO()
        with wave.open(data, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(struct.pack("<h", marker) * 2400)
        return data.getvalue()

    def lookup(tts, code, text, voice):
        lookups.append((code, text))
        assert text == expected
        assert code.endswith("_noi_dem") == with_filler
        return make_audio(text) if cached else None

    async def warm(tts, code, text, voice):
        warmed.append((code, text))

    async def synthesize(text, **kwargs):
        synthesis_calls.append(text)
        await asyncio.sleep(0)
        return make_audio(text)

    async def no_tool(*args, **kwargs):
        return ""

    class Sink:
        def __init__(self):
            self.events = []

        async def send_json(self, event):
            self.events.append(event)
            await asyncio.sleep(0)

    monkeypatch.setattr(sp, "_schedule_persist", lambda session: None)
    monkeypatch.setattr(sp, "_toan_van_tai_lieu", lambda product: "Tài liệu thử nghiệm.")
    monkeypatch.setattr(sp, "tra_loi_san", lambda *a, **k: ("fixture", ANSWER) if route == "smalltalk" else None)
    monkeypatch.setattr(sp, "tra_loi_khoan_vay", lambda *a, **k: ("fixture", ANSWER) if route == "financial" else None)
    monkeypatch.setattr(sp, "tra_loi_ho_so", lambda *a, **k: ("fixture", ANSWER) if route == "profile" else None)
    monkeypatch.setattr(sp, "doc_nguyen_van", lambda row: True)
    monkeypatch.setattr(sp, "kho_tieng_san", SimpleNamespace(lay=lookup, dung_mot=warm))
    monkeypatch.setattr(sp, "GOP_LO", False)
    monkeypatch.setattr(sp.settings, "tieng_san_bat", True)
    monkeypatch.setattr(sp.settings, "f5tts_gop_manh", True)
    monkeypatch.setattr(sp.settings, "ngu_canh_tron_tai_lieu", True)
    pipe = sp.StreamingPipeline.__new__(sp.StreamingPipeline)
    pipe.tts = SimpleNamespace(_is_loaded=True, _giong_thuc=lambda voice: "fixture")
    pipe.llm = SimpleNamespace(build_system_prompt=lambda **kwargs: "")
    pipe.rag = SimpleNamespace(neo_moi_tu_cau=lambda *args: None,
                               _san_pham_co_tai_lieu=lambda: [])
    pipe._tra_bang_cong_cu = no_tool
    pipe._tra_bang_hoi_dap = lambda *a, **k: (
        {"id": "fixture", "tra_loi": ANSWER, "diem": 1.0} if route == "approved" else None)
    pipe._try_synthesize = synthesize
    session = CallSession()
    session.so_can_cu = None
    session.add_turn("user", "Câu hỏi thử nghiệm")
    sink = Sink()
    metrics = {"la_thoai": True}
    if with_filler:
        metrics.update(filler_text=FILLER, filler_xong_luc=time.perf_counter() + 3)

    async def run():
        await pipe._generate_response(session.history[-1]["content"], session, sink,
                                      time.perf_counter(), metrics)
        await asyncio.sleep(0)  # finish the fake cache warmer before leaving the loop

    asyncio.run(run())
    completed = [e for e in sink.events if e["type"] == "turn_complete"]
    assert len(completed) == 1
    assert normalize(completed[0]["full_response"]) == normalize(expected)
    assert normalize(session.history[-1]["content"]) == normalize(expected)
    audio_events = [e for e in sink.events if e["type"] == "audio"]
    assert audio_events
    for event in audio_events:
        with wave.open(io.BytesIO(base64.b64decode(event["data"])), "rb") as wav:
            pcm = wav.readframes(wav.getnframes())
        marker = struct.unpack("<h", pcm[-2:])[0]
        assert normalize(event["text"]) == normalize(wave_text[marker])
    assert normalize(" ".join(e["text"] for e in audio_events)) == normalize(expected)
    assert normalize(" ".join(e["text"] for e in sink.events if e["type"] == "response_chunk")) == normalize(expected)
    assert len(lookups) == 1
    if cached:
        assert not synthesis_calls and not warmed
    else:
        assert synthesis_calls and warmed == lookups
        if with_filler:
            assert metrics["ghep_dau_so_manh"] >= 2
        else:
            assert "ghep_dau_so_manh" not in metrics
    assert bool(metrics.get("noi_dem_bo_mo_dau_lap")) == with_filler
