"""Thử hai lượt cùng phiên: AI báo lãi, khách chê bằng câu không nêu chủ đề."""

import asyncio
import audioop
import base64
import io
import json
import sys
import time
import urllib.parse
import urllib.request
import wave

import websockets


async def _turn(ws, kind: str, text: str) -> dict:
    await ws.send(json.dumps({"type": kind, "text": text}, ensure_ascii=False))
    while True:
        event = json.loads(await asyncio.wait_for(ws.recv(), timeout=90))
        if event.get("type") == "turn_complete":
            m = event.get("metrics") or {}
            return {
                "question": text,
                "answer": event.get("full_response", ""),
                "filler": m.get("filler_text"),
                "situation": m.get("tinh_huong_id"),
                "route": m.get("tinh_huong_cach_chon"),
                "skipped": m.get("filler_bo_qua"),
                "pick_ms": m.get("tinh_huong_chon_ms"),
            }


def _voice_pcm(text: str) -> bytes:
    form = urllib.parse.urlencode({"text": text, "voice_name": "default"}).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:8100/api/voices/test-tts", data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=90) as response:
        payload = json.load(response)
    if payload.get("error"):
        raise RuntimeError(payload["error"])
    with wave.open(io.BytesIO(base64.b64decode(payload["audio"]))) as wav:
        assert wav.getnchannels() == 1 and wav.getsampwidth() == 2
        pcm = wav.readframes(wav.getnframes())
        rate = wav.getframerate()
    return audioop.ratecv(pcm, 2, 1, rate, 16000, None)[0]


async def _voice_turn(ws, text: str) -> dict:
    pcm = _voice_pcm(text)
    for offset in range(0, len(pcm), 3200):
        await ws.send(json.dumps({
            "type": "audio_chunk",
            "data": base64.b64encode(pcm[offset:offset + 3200]).decode(),
        }))
        await asyncio.sleep(0.1)
    t_end = time.perf_counter()
    await ws.send(json.dumps({"type": "audio_end"}))
    transcript = ""
    first_audio_ms = None
    while True:
        event = json.loads(await asyncio.wait_for(ws.recv(), timeout=90))
        if event.get("type") == "audio" and first_audio_ms is None:
            first_audio_ms = round((time.perf_counter() - t_end) * 1000, 1)
        if event.get("type") == "transcript":
            transcript = event.get("text", "")
        if event.get("type") == "turn_complete":
            m = event.get("metrics") or {}
            return {
                "transcript": transcript,
                "answer": event.get("full_response", ""),
                "filler": m.get("filler_text"),
                "situation": m.get("tinh_huong_id"),
                "route": m.get("tinh_huong_cach_chon"),
                "skipped": m.get("filler_bo_qua"),
                "spec_stt_coverage": m.get("tinh_huong_do_phu"),
                "stt_before_filler_ms": m.get("stt_truoc_dem_ms"),
                "first_audio_ms": first_audio_ms,
            }


async def main():
    async with websockets.connect("ws://127.0.0.1:8100/ws/call/new", max_size=None) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type": "set_session", "product": "vay tín chấp"}))
        while json.loads(await ws.recv()).get("type") != "session_updated":
            pass
        first = await _turn(ws, "text_soi", "Lãi suất vay tín chấp bên em bao nhiêu?")
        second = (await _voice_turn(ws, "Cao thế em.")
                  if "--voice" in sys.argv else await _turn(ws, "text", "Cao thế em."))
        print(json.dumps({"first": first, "second": second}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
