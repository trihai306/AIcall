#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
import statistics
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from backend.pipeline import cong_cu_llm  # noqa: E402
from training.bankvn.common import has_cjk_hangul, is_strict_vietnamese  # noqa: E402


TOOL_MARKER = "<|bankvn_tool_call|>"
KNOWN_TOOLS = {item["function"]["name"] for item in cong_cu_llm.DINH_NGHIA}


def is_degenerate_generation(text: str) -> bool:
    """Nhận diện output lặp ký tự/token dù loss vẫn có thể giảm."""
    natural = text.replace("<|bankvn_end|>", "").strip()
    if not natural:
        return True

    longest_run = 1
    current_run = 1
    previous = ""
    for char in natural.casefold():
        if char.isspace():
            continue
        if char == previous:
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            previous = char
            current_run = 1
    if longest_run >= 8:
        return True

    words = [word for word in natural.casefold().split() if word]
    if len(words) >= 8:
        counts = Counter(words)
        if len(counts) / len(words) < 0.30 or counts.most_common(1)[0][1] / len(words) > 0.45:
            return True
    return False


def percentile95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * 0.95) - 1))
    return ordered[idx]


def parse_tool_call(text: str) -> tuple[dict | None, str | None]:
    if TOOL_MARKER not in text:
        return None, None
    payload = text.split(TOOL_MARKER, 1)[1].split("<|bankvn_end|>", 1)[0].strip()
    try:
        obj = json.loads(payload)
    except json.JSONDecodeError:
        return None, "malformed_json"
    if isinstance(obj, list):
        if len(obj) != 1 or not isinstance(obj[0], dict):
            return None, "tool_call_list_invalid"
        obj = obj[0]
    if not isinstance(obj, dict):
        return None, "tool_call_not_object"
    name = obj.get("name")
    arguments = obj.get("arguments")
    if name not in KNOWN_TOOLS:
        return None, "unknown_tool"
    if not isinstance(arguments, dict):
        return None, "arguments_not_object"
    return {"name": name, "arguments": arguments}, None


def expected_from_record(obj: dict) -> tuple[str, dict | None, str]:
    if "question" in obj and "expected_tool" in obj:
        question = str(obj.get("question") or "")
        expected_tool = obj.get("expected_tool")
        if expected_tool is None:
            return question, None, "assistant"
        return question, {"name": str(expected_tool), "arguments": None}, "router"
    messages = [m for m in obj.get("messages") or [] if isinstance(m, dict)]
    user = next((str(m.get("content") or "") for m in reversed(messages)
                 if m.get("role") == "user"), "")
    assistant = next((m for m in reversed(messages) if m.get("role") == "assistant"), {})
    calls = assistant.get("tool_calls") or []
    if calls:
        call = calls[0]
        function = call.get("function", call) if isinstance(call, dict) else {}
        expected = {
            "name": str(function.get("name") or ""),
            "arguments": function.get("arguments") or {},
        }
        return user, expected, "router"
    return user, None, "assistant"


def generate(
    model: str,
    system_prompt: str,
    question: str,
    timeout: float,
    ollama_url: str,
) -> tuple[str, dict, float]:
    prompt = (
        "<|bankvn_system|>" + system_prompt + "<|bankvn_end|>"
        "<|bankvn_user|>" + question + "<|bankvn_end|>"
        "<|bankvn_assistant|>"
    )
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "raw": True,
        "stream": False,
        "options": {"temperature": 0},
    }).encode("utf-8")
    request = Request(
        f"{ollama_url.rstrip('/')}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    started = time.perf_counter()
    with urlopen(request, timeout=timeout) as http_response:
        response = json.loads(http_response.read().decode("utf-8"))
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return str(response.get("response") or ""), response, elapsed_ms


def main() -> None:
    ap = argparse.ArgumentParser(description="Regression benchmark router BankVN qua Ollama")
    ap.add_argument("--model", required=True)
    ap.add_argument("--dataset", default="data/bankvn/sft/teacher.jsonl")
    ap.add_argument("--output", required=True)
    ap.add_argument("--limit", type=int, default=0, help="0 = chạy toàn bộ dataset")
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument(
        "--ollama-url",
        default="http://127.0.0.1:11435",
        help="Runtime Ollama test tách khỏi production/GPU train.",
    )
    args = ap.parse_args()

    dataset = ROOT / args.dataset
    records: list[dict] = []
    with dataset.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    if args.limit > 0:
        records = records[:args.limit]
    if not records:
        raise SystemExit("[ERROR] Dataset benchmark rỗng")

    system_prompt = cong_cu_llm.prompt_tool_bankvn(
        cong_cu_llm.PROMPT_QUYET_DINH,
        cong_cu_llm.DINH_NGHIA,
    )

    latencies: list[float] = []
    decode_rates: list[float] = []
    domain_correct = 0
    router_total = 0
    router_correct = 0
    assistant_total = 0
    assistant_answered = 0
    assistant_vi = 0
    assistant_foreign = 0
    hallucinations = 0
    degenerate = 0
    stopped = 0
    assistant_usable = 0
    failures: list[dict] = []

    for idx, obj in enumerate(records, start=1):
        question, expected, mode = expected_from_record(obj)
        response_text, meta, elapsed_ms = generate(
            args.model, system_prompt, question, args.timeout, args.ollama_url
        )
        response_degenerate = is_degenerate_generation(response_text)
        degenerate += int(response_degenerate)
        stopped += int(meta.get("done_reason") == "stop")
        latencies.append(elapsed_ms)
        eval_count = int(meta.get("eval_count") or 0)
        eval_duration = int(meta.get("eval_duration") or 0)
        if eval_count > 0 and eval_duration > 0:
            decode_rates.append(eval_count / (eval_duration / 1_000_000_000.0))

        actual, parse_error = parse_tool_call(response_text)
        correct = False
        if mode == "router":
            router_total += 1
            if expected and expected.get("arguments") is None:
                correct = (
                    parse_error is None
                    and actual is not None
                    and actual.get("name") == expected.get("name")
                )
            else:
                correct = parse_error is None and actual == expected
            router_correct += int(correct)
            if not correct:
                hallucinations += 1
        else:
            assistant_total += 1
            correct = parse_error is None and actual is None
            if not correct:
                hallucinations += 1
            natural = response_text.replace("<|bankvn_end|>", "").strip()
            if natural and TOOL_MARKER not in natural:
                assistant_answered += 1
                natural_vi = is_strict_vietnamese(natural, min_score=0.24, min_chars=8)
                assistant_vi += int(natural_vi)
                assistant_foreign += int(has_cjk_hangul(natural))
                assistant_usable += int(
                    natural_vi
                    and not response_degenerate
                    and not has_cjk_hangul(natural)
                    and 8 <= len(natural) <= 800
                    and meta.get("done_reason") == "stop"
                )

        domain_correct += int(correct)
        if not correct and len(failures) < 30:
            failures.append({
                "row": idx,
                "source_id": obj.get("source_id"),
                "mode": mode,
                "question": question,
                "expected": expected,
                "actual": actual,
                "parse_error": parse_error,
                "response": response_text[:500],
            })

    total = len(records)
    metrics = {
        "model": args.model,
        "dataset": str(dataset),
        "cases": total,
        "router_cases": router_total,
        "assistant_cases": assistant_total,
        "domain_accuracy": domain_correct / total,
        "tool_call_accuracy": router_correct / router_total if router_total else 0.0,
        "vietnamese_rate": assistant_vi / assistant_answered if assistant_answered else 1.0,
        "foreign_script_rate": assistant_foreign / assistant_answered if assistant_answered else 0.0,
        "hallucination_rate": hallucinations / total,
        "p95_latency_ms": percentile95(latencies),
        "median_latency_ms": statistics.median(latencies),
        "mean_decode_tokens_per_second": statistics.fmean(decode_rates) if decode_rates else 0.0,
        "assistant_answered": assistant_answered,
        "assistant_usable_rate": (
            assistant_usable / assistant_total if assistant_total else 0.0
        ),
        "degenerate_rate": degenerate / total,
        "stop_rate": stopped / total,
        "failures": failures,
    }
    target = ROOT / args.output
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False))


if __name__ == "__main__":
    main()
