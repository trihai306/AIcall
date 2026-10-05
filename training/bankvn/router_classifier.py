#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import statistics
import sys
import time
import unicodedata


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from backend.pipeline import cong_cu_llm  # noqa: E402


LABELS = ("profile", "product", "assistant")
TOOL_TO_LABEL = {
    "tra_ho_so_khach": "profile",
    "tra_thong_tin_san_pham": "product",
}
LABEL_TO_TOOL = {value: key for key, value in TOOL_TO_LABEL.items()}


def normalize(text: str) -> str:
    text = (text or "").lower().replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.split())


def features(text: str) -> Counter[str]:
    """Feature rẻ, bền với mất dấu/ASR và không cần dependency ngoài."""
    text = normalize(text)
    out: Counter[str] = Counter()
    padded = f"^{text}$"
    for n in (2, 3, 4, 5):
        for i in range(max(0, len(padded) - n + 1)):
            out[f"c{n}:{padded[i:i+n]}"] += 1
    words = text.split()
    for word in words:
        out[f"w:{word}"] += 2
    for a, b in zip(words, words[1:]):
        out[f"b:{a}_{b}"] += 2
    return out


def row_to_example(obj: dict) -> tuple[str, str] | None:
    target = str(obj.get("target") or "").strip()
    if target not in LABELS:
        target = ""

    messages = [m for m in (obj.get("messages") or []) if isinstance(m, dict)]
    user = next(
        (str(m.get("content") or "").strip() for m in reversed(messages)
         if m.get("role") == "user"),
        "",
    )
    if not user:
        return None

    if not target:
        mode = str(obj.get("mode") or "").strip()
        if mode == "assistant":
            target = "assistant"
        else:
            call_name = ""
            for message in reversed(messages):
                if message.get("role") != "assistant" or not message.get("tool_calls"):
                    continue
                call = message["tool_calls"][0]
                function = call.get("function", call) if isinstance(call, dict) else {}
                call_name = str(function.get("name") or "") if isinstance(function, dict) else ""
                break
            target = TOOL_TO_LABEL.get(call_name, "")

    return (user, target) if target in LABELS else None


def load_examples(paths: list[Path]) -> list[tuple[str, str]]:
    dedup: dict[str, tuple[str, str]] = {}
    for path in paths:
        if not path.exists():
            continue
        with path.open(encoding="utf-8", errors="replace") as src:
            for line in src:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                example = row_to_example(obj)
                if example is None:
                    continue
                user, label = example
                fast = cong_cu_llm.quyet_dinh_nhanh(user)
                if fast == cong_cu_llm.KHONG_CONG_CU:
                    fast_label = "assistant"
                else:
                    fast_label = TOOL_TO_LABEL.get(str(fast), "") if fast else ""
                # Teacher đôi khi sinh câu không đúng lớp được yêu cầu. Chỉ loại
                # khi lưới chắc chắn chứng minh nhãn mâu thuẫn; câu chưa rõ vẫn
                # được giữ để classifier học các biên mà regex không bao phủ.
                if fast_label and fast_label != label:
                    continue
                key = normalize(user)
                old = dedup.get(key)
                if old is None or old[1] == label:
                    dedup[key] = (user, label)
    return list(dedup.values())


def train(examples: list[tuple[str, str]], alpha: float = 0.35) -> dict:
    by_class = {label: Counter() for label in LABELS}
    class_docs = Counter()
    vocabulary: set[str] = set()
    for text, label in examples:
        feats = features(text)
        by_class[label].update(feats)
        class_docs[label] += 1
        vocabulary.update(feats)
    if any(class_docs[label] == 0 for label in LABELS):
        raise SystemExit(f"[ERROR] Thiếu lớp train: {dict(class_docs)}")

    return {
        "version": 1,
        "kind": "bankvn_router_multinomial_nb",
        "labels": list(LABELS),
        "alpha": alpha,
        "class_docs": dict(class_docs),
        "vocab_size": len(vocabulary),
        "feature_totals": {label: sum(by_class[label].values()) for label in LABELS},
        "feature_counts": {label: dict(by_class[label]) for label in LABELS},
        "training_examples": len(examples),
    }


def predict(model: dict, text: str) -> dict:
    feats = features(text)
    labels = tuple(model.get("labels") or LABELS)
    alpha = float(model.get("alpha") or 0.35)
    vocab_size = max(1, int(model.get("vocab_size") or 1))
    feature_totals = model.get("feature_totals") or {}
    feature_counts = model.get("feature_counts") or {}

    scores: dict[str, float] = {}
    # Uniform prior có chủ đích: dữ liệu teacher có thể lệch lớp theo từng chu kỳ.
    prior = -math.log(max(1, len(labels)))
    for label in labels:
        counts = feature_counts.get(label) or {}
        denom = float(feature_totals.get(label) or 0) + alpha * vocab_size
        score = prior
        for feat, count in feats.items():
            score += count * math.log((float(counts.get(feat) or 0) + alpha) / denom)
        scores[label] = score

    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    top_label, top_score = ordered[0]
    second_score = ordered[1][1] if len(ordered) > 1 else top_score
    max_score = max(scores.values())
    exp_scores = {label: math.exp(score - max_score) for label, score in scores.items()}
    total = sum(exp_scores.values()) or 1.0
    probabilities = {label: value / total for label, value in exp_scores.items()}
    return {
        "label": top_label,
        "confidence": probabilities[top_label],
        "margin": top_score - second_score,
        "probabilities": probabilities,
    }


def expected_label(obj: dict) -> tuple[str, str]:
    if "question" in obj and "expected_tool" in obj:
        question = str(obj.get("question") or "")
        tool = obj.get("expected_tool")
        return question, TOOL_TO_LABEL.get(str(tool), "assistant") if tool else "assistant"
    example = row_to_example(obj)
    if example is None:
        return "", "assistant"
    return example


def percentile95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * 0.95) - 1))
    return ordered[idx]


def route(model: dict, question: str, min_confidence: float, min_margin: float) -> dict:
    fast_decision = cong_cu_llm.quyet_dinh_nhanh(question)
    if fast_decision == cong_cu_llm.KHONG_CONG_CU:
        return {
            "label": "assistant",
            "tool": None,
            "source": "regex_no_tool",
            "confidence": 1.0,
            "margin": math.inf,
        }
    if fast_decision:
        return {
            "label": TOOL_TO_LABEL[fast_decision],
            "tool": fast_decision,
            "source": "regex",
            "confidence": 1.0,
            "margin": math.inf,
        }
    pred = predict(model, question)
    confident = pred["confidence"] >= min_confidence and pred["margin"] >= min_margin
    if not confident:
        return {**pred, "tool": None, "source": "uncertain"}
    return {
        **pred,
        "tool": LABEL_TO_TOOL.get(pred["label"]),
        "source": "classifier",
    }


def benchmark(model: dict, dataset: Path, min_confidence: float, min_margin: float) -> dict:
    cases: list[dict] = []
    with dataset.open(encoding="utf-8") as src:
        for line in src:
            if line.strip():
                cases.append(json.loads(line))
    if not cases:
        raise SystemExit("[ERROR] Benchmark rỗng")

    correct = 0
    router_total = 0
    router_correct = 0
    assistant_total = 0
    assistant_correct = 0
    latencies: list[float] = []
    sources = Counter()
    failures: list[dict] = []
    for idx, obj in enumerate(cases, start=1):
        question, expected = expected_label(obj)
        started = time.perf_counter()
        actual = route(model, question, min_confidence, min_margin)
        latencies.append((time.perf_counter() - started) * 1000.0)
        sources[actual["source"]] += 1
        # uncertain được coi là assistant/no-tool; production có thể fallback LLM sau.
        actual_label = actual["label"] if actual["source"] != "uncertain" else "assistant"
        ok = actual_label == expected
        correct += int(ok)
        if expected == "assistant":
            assistant_total += 1
            assistant_correct += int(ok)
        else:
            router_total += 1
            router_correct += int(ok)
        if not ok and len(failures) < 30:
            failures.append({
                "row": idx,
                "question": question,
                "expected": expected,
                "actual": actual_label,
                "source": actual["source"],
                "confidence": actual.get("confidence"),
                "margin": actual.get("margin"),
                "probabilities": actual.get("probabilities"),
            })

    total = len(cases)
    return {
        "engine": "regex+bankvn_router_multinomial_nb",
        "dataset": str(dataset),
        "cases": total,
        "router_cases": router_total,
        "assistant_cases": assistant_total,
        "domain_accuracy": correct / total,
        "tool_call_accuracy": router_correct / router_total if router_total else 0.0,
        "no_tool_accuracy": assistant_correct / assistant_total if assistant_total else 0.0,
        "hallucination_rate": (total - correct) / total,
        "p95_latency_ms": percentile95(latencies),
        "median_latency_ms": statistics.median(latencies),
        "mean_latency_ms": statistics.fmean(latencies),
        "route_sources": dict(sources),
        "min_confidence": min_confidence,
        "min_margin": min_margin,
        "failures": failures,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Train/benchmark router classifier BankVN")
    sub = ap.add_subparsers(dest="command", required=True)

    train_ap = sub.add_parser("train")
    train_ap.add_argument("--dataset", action="append", required=True)
    train_ap.add_argument("--output", required=True)
    train_ap.add_argument("--alpha", type=float, default=0.35)

    bench_ap = sub.add_parser("benchmark")
    bench_ap.add_argument("--model", required=True)
    bench_ap.add_argument("--dataset", required=True)
    bench_ap.add_argument("--output", required=True)
    bench_ap.add_argument("--min-confidence", type=float, default=0.62)
    bench_ap.add_argument("--min-margin", type=float, default=1.5)

    pred_ap = sub.add_parser("predict")
    pred_ap.add_argument("--model", required=True)
    pred_ap.add_argument("text")
    pred_ap.add_argument("--min-confidence", type=float, default=0.62)
    pred_ap.add_argument("--min-margin", type=float, default=1.5)

    args = ap.parse_args()
    if args.command == "train":
        paths = [ROOT / path for path in args.dataset]
        examples = load_examples(paths)
        model = train(examples, args.alpha)
        output = ROOT / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(model, ensure_ascii=False, separators=(",", ":")),
                          encoding="utf-8")
        print(json.dumps({
            "status": "ok",
            "output": str(output),
            "training_examples": model["training_examples"],
            "class_docs": model["class_docs"],
            "vocab_size": model["vocab_size"],
        }, ensure_ascii=False))
    elif args.command == "benchmark":
        model = json.loads((ROOT / args.model).read_text(encoding="utf-8"))
        result = benchmark(
            model,
            ROOT / args.dataset,
            args.min_confidence,
            args.min_margin,
        )
        output = ROOT / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
    else:
        model = json.loads((ROOT / args.model).read_text(encoding="utf-8"))
        print(json.dumps(
            route(model, args.text, args.min_confidence, args.min_margin),
            ensure_ascii=False,
        ))


if __name__ == "__main__":
    main()
