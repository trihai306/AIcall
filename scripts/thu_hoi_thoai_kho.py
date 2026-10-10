"""Thử hội thoại thật và lưu bằng chứng/oracle từng lượt, không tự chấm bằng AI.

python scripts/thu_hoi_thoai_kho.py input.json output.json
Mỗi `luot` là chuỗi hoặc {khach, expect}; không có expect thì giữ unscored.
"""
import argparse
import asyncio
import json
import re
import time
import unicodedata
from pathlib import Path

import websockets


def folded(text):
    return "".join(c for c in unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
                   if unicodedata.category(c) != "Mn")


def check(reply, metrics, expected):
    if expected is None:
        return None, []
    errors, normalized = [], folded(reply)
    route = metrics.get("answer_route", {})
    for pattern in expected.get("require", []):
        if not re.search(pattern, normalized):
            errors.append("missing: " + pattern)
    for pattern in expected.get("forbid", []):
        if re.search(pattern, normalized):
            errors.append("forbidden: " + pattern)
    if expected.get("modes") and route.get("mode") not in expected["modes"]:
        errors.append("mode: " + str(route.get("mode")))
    if expected.get("reasons") and route.get("reason") not in expected["reasons"]:
        errors.append("reason: " + str(route.get("reason")))
    for slot, fields in expected.get("facts", {}).items():
        actual = metrics.get("du_kien_vay", {}).get(slot, {})
        for field, value in fields.items():
            if str(actual.get(field)) != str(value):
                errors.append(f"{slot}.{field}: {actual.get(field)!r}, wanted {value!r}")
    return not errors, errors


async def run_case(case, ws_base):
    session_id = f"quality_{time.time_ns()}"
    rows = []
    case["ket_qua"] = rows
    async with websockets.connect(ws_base + session_id, max_size=None) as ws:
        await ws.send(json.dumps({"type": "set_session", "customer_name": "Khách kiểm thử",
                                  "product": case.get("san_pham", "")}))
        while json.loads(await asyncio.wait_for(ws.recv(), 30)).get("type") != "session_updated":
            pass
        for index, step in enumerate(case["luot"], 1):
            question = step if isinstance(step, str) else step["khach"]
            expected = None if isinstance(step, str) else step.get("expect")
            await ws.send(json.dumps({"type": "text_soi", "text": question, "turn_id": index}))
            deadline, chunks = time.monotonic() + 45, []
            while True:
                raw = await asyncio.wait_for(ws.recv(), max(0.01, deadline - time.monotonic()))
                if isinstance(raw, bytes):
                    continue
                event = json.loads(raw)
                if event.get("type") == "response_chunk":
                    chunks.append(event.get("text", ""))
                elif event.get("type") == "error":
                    rows.append({"khach": question, "ai": "", "error": event,
                                 "pass": False, "issues": ["service error"]})
                    break
                elif event.get("type") == "turn_complete":
                    reply, metrics = event.get("full_response", ""), event.get("metrics", {}) or {}
                    passed, issues = check(reply, metrics, expected)
                    rows.append({"khach": question, "ai": reply, "expect": expected,
                                 "pass": passed, "issues": issues, "metrics": metrics,
                                 "response_chunks": chunks})
                    break
    return rows


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--ws", default="ws://127.0.0.1:8100/ws/call/")
    args = parser.parse_args()
    cases = json.loads(Path(args.input).read_text(encoding="utf-8"))
    output, started = Path(args.output), time.monotonic()
    output.parent.mkdir(parents=True, exist_ok=True)
    for index, case in enumerate(cases, 1):
        try:
            case["ket_qua"] = await asyncio.wait_for(run_case(case, args.ws), 180)
        except Exception as error:
            case["loi"] = repr(error)
            case.setdefault("ket_qua", [])
        output.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
        failed = [i for i, row in enumerate(case.get("ket_qua", []), 1) if row.get("pass") is False]
        if failed or index % 10 == 0 or index == len(cases):
            print(json.dumps({"case": case["ma"], "progress": f"{index}/{len(cases)}",
                              "failed_turns": failed, "error": case.get("loi"),
                              "elapsed_s": round(time.monotonic() - started)}, ensure_ascii=False), flush=True)
    rows = [row for case in cases for row in case.get("ket_qua", [])]
    print(json.dumps({"total_turns": len(rows), "pass": sum(row.get("pass") is True for row in rows),
                      "fail": sum(row.get("pass") is False for row in rows),
                      "unscored": sum(row.get("pass") is None for row in rows),
                      "session_errors": sum(bool(case.get("loi")) for case in cases)}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
