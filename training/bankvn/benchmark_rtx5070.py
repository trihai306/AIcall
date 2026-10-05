#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


ROOT = Path(__file__).resolve().parents[2]
BANKVN = ROOT / "training" / "bankvn"
STATE = ROOT / "data" / "bankvn" / "state"


def run_capture(cmd: list[str]) -> tuple[int, str, float]:
    started = time.perf_counter()
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    elapsed = time.perf_counter() - started
    print(proc.stdout, end="")
    return proc.returncode, proc.stdout, elapsed


def parsed_objects(output: str) -> list[dict]:
    rows: list[dict] = []
    for raw in output.splitlines():
        line = raw.strip()
        if not (line.startswith("{") and line.endswith("}")):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            try:
                obj = ast.literal_eval(line)
            except (SyntaxError, ValueError):
                continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def free_vram_mb() -> int | None:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            text=True,
            timeout=10,
        )
        return int(out.strip().splitlines()[0])
    except Exception:
        return None


def stop_teacher(model: str) -> None:
    subprocess.run(
        ["ollama", "stop", model],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=30,
        check=False,
    )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        free = free_vram_mb()
        if free is None or free >= 9000:
            return
        time.sleep(1)


def benchmark_teacher(args, stamp: str) -> list[dict]:
    rows: list[dict] = []
    workers_list = [int(x.strip()) for x in args.teacher_workers.split(",") if x.strip()]
    for workers in workers_list:
        if workers < 1:
            raise SystemExit("[ERROR] --teacher-workers chỉ nhận số nguyên >= 1")
        output = STATE / f"teacher-bench-w{workers}-{stamp}.jsonl"
        cmd = [
            sys.executable,
            str(BANKVN / "teacher_generate.py"),
            str(ROOT / "knowledge" / "faq"),
            str(ROOT / "knowledge" / "products"),
            str(ROOT / "data" / "bankvn" / "clean" / "banking_corpus.jsonl"),
            "--output", str(output),
            "--model", args.teacher_model,
            "--max-samples", str(args.teacher_samples),
            "--max-attempts", str(max(4, args.teacher_samples * 4)),
            "--workers", str(workers),
            "--source-chars", str(args.teacher_source_chars),
            "--source-overlap-chars", str(args.teacher_source_overlap_chars),
            "--max-chunks-per-source", str(args.teacher_max_chunks_per_source),
            "--num-predict", "192",
            "--num-ctx", "4096",
            "--source-min-score", "0.24",
        ]
        code, stdout, wall = run_capture(cmd)
        objects = parsed_objects(stdout)
        metric = next((x for x in reversed(objects) if "samples_per_minute" in x), {})
        rows.append({
            "workers": workers,
            "returncode": code,
            "wall_seconds": round(wall, 3),
            **metric,
        })
    return rows


def ensure_benchmark_corpus() -> Path:
    corpus = STATE / "strict-smoke.jsonl"
    if corpus.exists() and corpus.stat().st_size > 0:
        return corpus
    code, _, _ = run_capture([
        sys.executable,
        str(BANKVN / "prepare_corpus.py"),
        str(ROOT / "knowledge" / "faq" / "faq_banking.md"),
        "--output", str(corpus),
        "--strict-vietnamese",
        "--min-score", "0.28",
    ])
    if code:
        raise SystemExit("[ERROR] Không tạo được corpus benchmark")
    return corpus


def benchmark_pretrain(args, stamp: str) -> list[dict]:
    corpus = ensure_benchmark_corpus()
    tokenizer = ROOT / "models" / "bankvn" / "tokenizer-sp-smoke6"
    all_profiles = [
        ("baseline", ROOT / "training" / "bankvn" / "configs" / "bankvn-350m.json"),
        ("fast", ROOT / "training" / "bankvn" / "configs" / "bankvn-350m-rtx5070-fast.json"),
        ("safe", ROOT / "training" / "bankvn" / "configs" / "bankvn-350m-rtx5070-safe.json"),
    ]
    wanted = {x.strip() for x in args.pretrain_profiles.split(",") if x.strip()}
    profiles = [(name, path) for name, path in all_profiles if name in wanted]
    if not profiles:
        raise SystemExit("[ERROR] --pretrain-profiles không có profile hợp lệ")
    rows: list[dict] = []
    for label, profile in profiles:
        output = ROOT / "models" / "bankvn" / "bench" / f"{label}-{stamp}"
        cmd = [
            sys.executable,
            str(BANKVN / "pretrain.py"),
            "--profile", str(profile),
            "--tokenizer", str(tokenizer),
            "--corpus", str(corpus),
            "--output", str(output),
            "--max-steps", str(args.pretrain_steps),
        ]
        code, stdout, wall = run_capture(cmd)
        objects = parsed_objects(stdout)
        train = next((x for x in reversed(objects) if "train_steps_per_second" in x), {})
        cuda = next((x for x in reversed(objects) if "cuda_peak_reserved_gb" in x), {})
        setup = next((x for x in objects if "gradient_checkpointing" in x), {})
        rows.append({
            "profile": label,
            "returncode": code,
            "wall_seconds": round(wall, 3),
            "train_steps_per_second": train.get("train_steps_per_second"),
            "train_runtime": train.get("train_runtime"),
            "cuda_peak_allocated_gb": cuda.get("cuda_peak_allocated_gb"),
            "cuda_peak_reserved_gb": cuda.get("cuda_peak_reserved_gb"),
            "batch_size": setup.get("batch_size"),
            "gradient_accumulation_steps": setup.get("gradient_accumulation_steps"),
            "gradient_checkpointing": setup.get("gradient_checkpointing"),
        })
        if not args.keep_models and output.exists():
            shutil.rmtree(output)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Benchmark BankVN trên RTX 5070 12GB")
    ap.add_argument("--teacher-model", default="qwen3.5:9b")
    ap.add_argument("--teacher-samples", type=int, default=6)
    ap.add_argument("--teacher-workers", default="1,2,4",
                    help="Danh sách số worker teacher cần benchmark, ví dụ 1,2,4")
    ap.add_argument("--teacher-source-chars", type=int, default=1600)
    ap.add_argument("--teacher-source-overlap-chars", type=int, default=160)
    ap.add_argument("--teacher-max-chunks-per-source", type=int, default=8)
    ap.add_argument("--pretrain-steps", type=int, default=30)
    ap.add_argument("--pretrain-profiles", default="baseline,fast,safe")
    ap.add_argument("--skip-teacher", action="store_true")
    ap.add_argument("--skip-pretrain", action="store_true")
    ap.add_argument("--keep-models", action="store_true")
    args = ap.parse_args()

    STATE.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "teacher": [],
        "pretrain": [],
    }
    if not args.skip_teacher:
        summary["teacher"] = benchmark_teacher(args, stamp)
    stop_teacher(args.teacher_model)
    summary["free_vram_mb_after_teacher_stop"] = free_vram_mb()
    if not args.skip_pretrain:
        summary["pretrain"] = benchmark_pretrain(args, stamp)

    payload = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    target = STATE / "benchmark_rtx5070.json"
    archived = STATE / f"benchmark_rtx5070-{stamp}.json"
    target.write_text(payload, encoding="utf-8")
    archived.write_text(payload, encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    print(f"[OK] {target} | {archived}")


if __name__ == "__main__":
    main()
