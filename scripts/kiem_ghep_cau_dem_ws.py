"""Compare actual backend filler/answer packets before and after a join change.

Run on Windows. Creates labelled TEST sessions, never dials. WAVs replay the
received packets in FIFO order, including arrival gaps; they do not measure
phone end-to-ear latency and are not a human assessment of naturalness.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import time

import httpx
import numpy as np
import soundfile as sf
import websockets

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    ("intro", "em tư vấn cho anh về khoản vay bên mình này", "gioi_thieu_san_pham"),
    ("amount", "anh muốn vay 275 triệu trong 24 tháng", "nhu_cau_vay"),
    ("calculation", "anh vay 425 triệu trong 24 tháng mỗi tháng đóng bao nhiêu", "tinh_tra_gop"),
    ("procedure", "hồ sơ vay cần giấy tờ gì", "ho_so_can_thiet"),
]


def normal(text):
    return re.sub(r"\s+([.,!?;:])", r"\1", " ".join(text.split()))


def save_fifo(events, path):
    pieces, cursor, rate = [], 0, None
    origin = events[0][0]
    for arrived, data in events:
        audio, sr = sf.read(io.BytesIO(data), dtype="int16", always_2d=True)
        if rate is None:
            rate = sr
        assert sr == rate and audio.shape[1] == 1, (sr, rate, audio.shape)
        start = max(cursor, round((arrived - origin) * sr))
        if start > cursor:
            pieces.append(np.zeros((start - cursor, 1), dtype=np.int16))
        pieces.append(audio)
        cursor = start + len(audio)
    sf.write(path, np.concatenate(pieces), rate, subtype="PCM_16")


async def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("before", "after"), required=True)
    args = parser.parse_args()
    out = ROOT / "logs" / f"filler_join_{args.phase}_{time.time_ns()}"
    out.mkdir(exist_ok=False)
    report = {"phase": args.phase, "rows": [], "scope": __doc__, "passed": False}
    try:
        async with httpx.AsyncClient(base_url="http://127.0.0.1:8100", timeout=15, trust_env=False) as client:
            async def get(path):
                response = await client.get(path)
                response.raise_for_status()
                return response.json()
            async def idle():
                state = await get("/api/devices/voice/status")
                assert "calls" in state and not state["calls"], state
                device = await get("/api/devices/dev_643aeac5/call-state")
                assert device.get("state") == "idle", device
            await idle()
            health = await get("/api/health")
            report["health"] = health
            assert health["system"]["platform"] == "Windows" and health["system"]["device"] == "cuda", health
            assert health["services"]["stt_engine"] == "gipformer", health
            assert health["services"]["tts"] == "loaded" and health["services"]["llm"] == "ok", health
            report["source_hashes"] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in [ROOT / "backend/pipeline/streaming_pipeline.py", ROOT / "backend/services/tieng_san.py",
                          ROOT / "backend/pipeline/noi_cau_dem.py"] if p.exists()}

            async def run_case(name, text, expected, *, audio=None):
                await idle()
                row = {"name": name, "input": text, "errors": [], "audio_text": [], "chunks": [], "packets": []}
                report["rows"].append(row)
                packets = []
                async with websockets.connect(f"ws://127.0.0.1:8100/ws/call/join-test-{time.time_ns()}",
                        open_timeout=15, max_size=16 * 1024 * 1024) as ws:
                    await asyncio.wait_for(ws.recv(), 15)
                    await ws.send(json.dumps({"type": "set_session", "customer_name": f"TEST filler {args.phase} - khong goi",
                                              "product": "vay tín chấp"}, ensure_ascii=False))
                    updated = json.loads(await asyncio.wait_for(ws.recv(), 15))
                    assert updated["type"] == "session_updated", updated
                    row["session_id"] = updated["session"]["session_id"]
                    message = {"type": "text", "text": text, "turn_id": 1}
                    if audio:
                        message = {"type": "audio", "data": base64.b64encode(audio).decode(), "turn_id": 1}
                    started = time.perf_counter()
                    await ws.send(json.dumps(message, ensure_ascii=False))
                    deadline = time.monotonic() + 60
                    while True:
                        event = json.loads(await asyncio.wait_for(ws.recv(), max(.01, deadline - time.monotonic())))
                        kind = event.get("type")
                        if kind == "audio":
                            arrival = time.perf_counter() - started
                            data = base64.b64decode(event["data"])
                            packets.append((arrival, data))
                            row["packets"].append({"arrival_ms": round(arrival * 1000, 1),
                                "duration_ms": round(sf.info(io.BytesIO(data)).duration * 1000, 1),
                                "is_filler": bool(event.get("is_filler")), "text": event.get("text", "")})
                            if not event.get("is_filler"):
                                row["audio_text"].append(event.get("text", ""))
                        elif kind == "response_chunk":
                            row["chunks"].append(event["text"])
                        elif kind == "transcript":
                            row["transcript"] = event.get("text", "")
                        elif kind == "error":
                            row["errors"].append(event)
                        elif kind == "turn_complete":
                            row["response"] = event.get("full_response", "")
                            row["metrics"] = event.get("metrics", {})
                            break
                assert packets and not row["errors"] and row["response"], row
                metrics = row["metrics"]
                assert metrics.get("tra_tu_quy_tac_tai_chinh") == expected, row
                assert metrics.get("filler_text"), row
                row["audio_matches_text"] = normal(" ".join(row["audio_text"])) == normal(row["response"])
                row["audio_match_scope"] = "Packet text metadata versus response; not a transcription of generated speech"
                filler_end = None
                for packet in row["packets"]:
                    if packet["is_filler"]:
                        filler_end = packet["arrival_ms"] + packet["duration_ms"]
                    elif filler_end is not None:
                        row["fifo_gap_after_filler_ms"] = round(max(0, packet["arrival_ms"] - filler_end), 1)
                        break
                row["wav"] = str(out / f"{name}.wav")
                save_fifo(packets, row["wav"])
                if args.phase == "after":
                    assert metrics.get("noi_dem_bo_mo_dau_lap"), row
                    assert not re.match(r"^(?:dạ|vâng)\b", row["response"], re.I), row
                    assert row["audio_matches_text"], row
                    assert normal(" ".join(row["chunks"])) == normal(row["response"]), row
                for _ in range(10):
                    saved = (await get(f"/api/sessions/{row['session_id']}"))["session"]
                    if len(saved["history"]) >= 2:
                        break
                    await asyncio.sleep(.1)
                assert saved["history"][-1]["content"] == row["response"], saved
                print(json.dumps({k: row.get(k) for k in ("name", "session_id", "response", "audio_matches_text", "wav")},
                                 ensure_ascii=False), flush=True)

            for iteration in range(1 if args.phase == "before" else 2):
                for name, text, rule in CASES:
                    await run_case(f"{iteration + 1}_{name}", text, rule)
            if args.phase == "after":
                sample = ROOT / "logs/asr_eval_20260912/samples/d9b57f0b_07.wav"
                await run_case("recorded_audio", str(sample), "nhu_cau_vay", audio=sample.read_bytes())
                assert any(r["metrics"].get("tieng_san", "").endswith("_noi_dem") for r in report["rows"]), \
                    "Continuation cache not exercised"
            report["passed"] = True
    finally:
        with (out / "report.json").open("x", encoding="utf-8") as output:
            json.dump(report, output, ensure_ascii=False, indent=2)
        print("REPORT", out, flush=True)
    print("PASS", args.phase, len(report["rows"]), "sessions")


if __name__ == "__main__":
    asyncio.run(main())
