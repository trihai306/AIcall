"""Verify real Qwen/F5/STT via loopback; does not dial a telephone number."""
import argparse
import asyncio
import base64
import json
from pathlib import Path
import urllib.parse
import urllib.request

import websockets


BASE = "http://127.0.0.1:8100"


def request(path, data=None, form=False):
    payload = None
    headers = {}
    if data is not None:
        payload = (urllib.parse.urlencode(data).encode() if form else
                   json.dumps(data, ensure_ascii=False).encode())
        headers["Content-Type"] = "application/x-www-form-urlencoded" if form else "application/json"
    with urllib.request.urlopen(urllib.request.Request(BASE + path, payload, headers), timeout=90) as response:
        return json.load(response)


async def turn(scenario_id, question, kind, audio=None):
    async with websockets.connect("ws://127.0.0.1:8100/ws/call/new", max_size=8_000_000) as ws:
        connected = json.loads(await ws.recv())
        await ws.send(json.dumps({"type": "set_session", "scenario_id": scenario_id,
                                  "product": "thẻ tín dụng", "customer_name": "Khách kiểm thử"}))
        while json.loads(await asyncio.wait_for(ws.recv(), 15)).get("type") != "session_updated":
            pass
        payload = {"type": kind, "turn_id": 1}
        payload["data" if audio else "text"] = audio or question
        await ws.send(json.dumps(payload))
        frames, transcript = [], ""
        while True:
            event = json.loads(await asyncio.wait_for(ws.recv(), 60))
            if event.get("type") == "error":
                raise RuntimeError(event.get("message"))
            if event.get("type") == "transcript":
                transcript = event.get("text", "")
            if event.get("type") == "audio" and not event.get("is_filler"):
                frames.append(base64.b64decode(event["data"]))
            if event.get("type") == "turn_complete":
                return {"kind": kind, "session_id": connected["session_id"],
                        "question": question, "transcript": transcript,
                        "answer": event.get("full_response", ""),
                        "metrics": event.get("metrics", {}),
                        "audio_bytes": sum(map(len, frames)), "_frames": frames}


async def main(args):
    health = request("/api/health")
    assert health["system"]["platform"] == "Windows"
    assert health["system"]["device"] == "cuda"
    scenarios = request("/api/scenarios")["scenarios"]
    scenario = next(s for s in scenarios if s["scenario_id"] == args.scenario_id)
    assert "shinhan" in scenario["org_name"].casefold()
    rows = request("/api/knowledge/hoi-dap?nhom=shinhan&ten=shinhan_card_user_guide_vi")["items"]
    allowed = {row["id"] for row in rows if row["bat"]}
    question = "Cách bật hoặc tắt giao dịch thẻ quốc tế trên Shinhan?"
    results = []
    for text in (question, "Tôi muốn bật giao dịch thẻ ở nước ngoài, phải vào đâu?"):
        results.append(await turn(args.scenario_id, text, "text_soi"))
    speech = await asyncio.to_thread(request, "/api/voices/test-tts", {
        "text": question, "voice_name": "default", "qua_dien_thoai": "true"}, True)
    assert "audio" in speech, speech
    results.append(await turn(args.scenario_id, question, "audio", speech["audio"]))
    for i, result in enumerate(results):
        frames = result.pop("_frames")
        if frames:
            Path(args.output).with_name(f"answer_routing_audio_{i}.wav").write_bytes(frames[0])
        route = result["metrics"].get("answer_route", {})
        result["selected_source_answer"] = route.get("answer_id") in allowed
        result["qwen_selected"] = route.get("model") == "qwen3.5:9b"
        result["passed"] = (result["selected_source_answer"] and result["qwen_selected"]
                            and route.get("mode") == "answer_bank"
                            and (result["kind"] != "audio" or result["audio_bytes"] > 44))
    report = {"health": health, "scenario_id": args.scenario_id,
              "transport": "loopback WebSocket, telephone-band audio; no physical call",
              "results": results, "passed": all(r["passed"] for r in results)}
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))
    assert report["passed"], "See report for failed routing cases"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario-id", required=True)
    parser.add_argument("--output", default="docs/answer_routing_live_windows_20261001.json")
    asyncio.run(main(parser.parse_args()))
