#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


for _stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(_stream, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="replace")


HIGHER_BETTER = ("domain_accuracy", "tool_call_accuracy", "vietnamese_rate")
LOWER_BETTER = ("foreign_script_rate", "hallucination_rate")
REQUIRED_BASELINE_METRICS = HIGHER_BETTER + LOWER_BETTER + (
    "p95_latency_ms",
    "mean_decode_tokens_per_second",
)
REQUIRED_METRICS = REQUIRED_BASELINE_METRICS + (
    "assistant_usable_rate",
    "degenerate_rate",
    "stop_rate",
)


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def evaluate(
    base: dict,
    cand: dict,
    latency_factor: float,
    min_domain_accuracy: float = 0.90,
    min_tool_call_accuracy: float = 0.90,
    max_hallucination_rate: float = 0.10,
    min_decode_speed_factor: float = 0.90,
    min_assistant_usable_rate: float = 0.90,
    max_degenerate_rate: float = 0.0,
    min_stop_rate: float = 0.95,
) -> tuple[bool, list[str]]:
    failures: list[str] = []
    for side, metrics, required in (
        ("baseline", base, REQUIRED_BASELINE_METRICS),
        ("candidate", cand, REQUIRED_METRICS),
    ):
        for key in required:
            if key not in metrics:
                failures.append(f"{side} thiếu metric bắt buộc: {key}")
    for key in HIGHER_BETTER:
        if key in base and key in cand and cand[key] < base[key]:
            failures.append(f"{key}: {cand[key]} < baseline {base[key]}")
    for key in LOWER_BETTER:
        if key in base and key in cand and cand[key] > base[key]:
            failures.append(f"{key}: {cand[key]} > baseline {base[key]}")
    if cand.get("vietnamese_rate", 1.0) < 0.995:
        failures.append(f"vietnamese_rate: {cand.get('vietnamese_rate')} < 0.995")
    if cand.get("foreign_script_rate", 0.0) > 0.001:
        failures.append(f"foreign_script_rate: {cand.get('foreign_script_rate')} > 0.001")
    if cand.get("domain_accuracy", 0.0) < min_domain_accuracy:
        failures.append(
            f"domain_accuracy: {cand.get('domain_accuracy')} < {min_domain_accuracy}"
        )
    if cand.get("tool_call_accuracy", 0.0) < min_tool_call_accuracy:
        failures.append(
            f"tool_call_accuracy: {cand.get('tool_call_accuracy')} < {min_tool_call_accuracy}"
        )
    if cand.get("hallucination_rate", 1.0) > max_hallucination_rate:
        failures.append(
            f"hallucination_rate: {cand.get('hallucination_rate')} > {max_hallucination_rate}"
        )
    if cand.get("assistant_usable_rate", 0.0) < min_assistant_usable_rate:
        failures.append(
            "assistant_usable_rate: "
            f"{cand.get('assistant_usable_rate')} < {min_assistant_usable_rate}"
        )
    if cand.get("degenerate_rate", 1.0) > max_degenerate_rate:
        failures.append(
            f"degenerate_rate: {cand.get('degenerate_rate')} > {max_degenerate_rate}"
        )
    if cand.get("stop_rate", 0.0) < min_stop_rate:
        failures.append(f"stop_rate: {cand.get('stop_rate')} < {min_stop_rate}")
    if "p95_latency_ms" in base and "p95_latency_ms" in cand:
        limit = base["p95_latency_ms"] * latency_factor
        if cand["p95_latency_ms"] > limit:
            failures.append(f"p95_latency_ms: {cand['p95_latency_ms']} > {limit:.1f}")
    if "mean_decode_tokens_per_second" in base and "mean_decode_tokens_per_second" in cand:
        speed_floor = base["mean_decode_tokens_per_second"] * min_decode_speed_factor
        if cand["mean_decode_tokens_per_second"] < speed_floor:
            failures.append(
                "mean_decode_tokens_per_second: "
                f"{cand['mean_decode_tokens_per_second']} < {speed_floor:.1f}"
            )
    return not failures, failures


def main() -> None:
    ap = argparse.ArgumentParser(description="Promotion gate cho BankVN")
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--latency-factor", type=float, default=1.25)
    ap.add_argument("--min-domain-accuracy", type=float, default=0.90)
    ap.add_argument("--min-tool-call-accuracy", type=float, default=0.90)
    ap.add_argument("--max-hallucination-rate", type=float, default=0.10)
    ap.add_argument("--min-decode-speed-factor", type=float, default=0.90)
    ap.add_argument("--min-assistant-usable-rate", type=float, default=0.90)
    ap.add_argument("--max-degenerate-rate", type=float, default=0.0)
    ap.add_argument("--min-stop-rate", type=float, default=0.95)
    ap.add_argument("--result", default="data/bankvn/state/last_gate.json")
    args = ap.parse_args()
    base, cand = load(args.baseline), load(args.candidate)
    passed, failures = evaluate(
        base,
        cand,
        args.latency_factor,
        args.min_domain_accuracy,
        args.min_tool_call_accuracy,
        args.max_hallucination_rate,
        args.min_decode_speed_factor,
        args.min_assistant_usable_rate,
        args.max_degenerate_rate,
        args.min_stop_rate,
    )
    result = {
        "passed": passed,
        "failures": failures,
        "thresholds": {
            "latency_factor": args.latency_factor,
            "min_domain_accuracy": args.min_domain_accuracy,
            "min_tool_call_accuracy": args.min_tool_call_accuracy,
            "max_hallucination_rate": args.max_hallucination_rate,
            "min_decode_speed_factor": args.min_decode_speed_factor,
            "min_assistant_usable_rate": args.min_assistant_usable_rate,
            "max_degenerate_rate": args.max_degenerate_rate,
            "min_stop_rate": args.min_stop_rate,
        },
        "baseline": base,
        "candidate": cand,
    }
    out = Path(args.result)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if passed else 2)


if __name__ == "__main__":
    main()
