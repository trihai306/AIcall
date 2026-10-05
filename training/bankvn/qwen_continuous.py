#!/usr/bin/env python3
"""Safe 24/7 QLoRA loop for the marketed Qwen2.5 3B (3.1B parameters)."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[2]
BANKVN = ROOT / "training" / "bankvn"
STATE = ROOT / "data" / "bankvn" / "state"
RAW_TEACHER = ROOT / "data" / "bankvn" / "sft" / "qwen_teacher_raw.jsonl"
OLD_TEACHER = ROOT / "data" / "bankvn" / "sft" / "teacher.jsonl"
CLEAN_DATA = ROOT / "data" / "bankvn" / "sft" / "qwen_assistant_clean.jsonl"
BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"
PROFILE = "qwen2.5-3b-qlora-24x7"


QWEN_MODELFILE = '''FROM "{gguf}"

TEMPLATE """{{{{- if .Messages }}}}
{{{{- if .System }}}}<|im_start|>system
{{{{ .System }}}}<|im_end|>
{{{{ end }}}}
{{{{- range .Messages }}}}
{{{{- if eq .Role "user" }}}}<|im_start|>user
{{{{ .Content }}}}<|im_end|>
{{{{- else if eq .Role "assistant" }}}}<|im_start|>assistant
{{{{ .Content }}}}<|im_end|>
{{{{- end }}}}
{{{{- end }}}}<|im_start|>assistant
{{{{- else }}}}<|im_start|>system
{{{{ .System }}}}<|im_end|>
<|im_start|>user
{{{{ .Prompt }}}}<|im_end|>
<|im_start|>assistant
{{{{- end }}}}"""

PARAMETER stop "<|im_start|>"
PARAMETER stop "<|im_end|>"
PARAMETER num_ctx 4096
PARAMETER temperature 0
'''


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def progress(phase: str, **extra) -> None:
    payload = {"phase": phase, "profile": PROFILE, "updated_at_utc": utc_now(), **extra}
    atomic_json(STATE / "progress.json", payload)


def run(cmd: list[str], *, env: dict | None = None, check: bool = True) -> int:
    print("[RUN]", subprocess.list2cmdline(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=str(ROOT), env=env)
    if check and proc.returncode:
        raise RuntimeError(f"Lệnh lỗi {proc.returncode}: {subprocess.list2cmdline(cmd)}")
    return proc.returncode


def count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(encoding="utf-8", errors="ignore") as src:
        return sum(1 for line in src if line.strip())


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as src:
        for chunk in iter(lambda: src.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def merge_unique(target: Path, shard: Path) -> int:
    known: set[str] = set()
    rows: list[str] = []
    for path in (target, shard):
        if not path.exists():
            continue
        with path.open(encoding="utf-8", errors="ignore") as src:
            for line in src:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                key = str(obj.get("source_id") or "").strip()
                if not key or key in known:
                    continue
                known.add(key)
                rows.append(json.dumps(obj, ensure_ascii=False))
    before = count_jsonl(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + f".{os.getpid()}.tmp")
    tmp.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")
    os.replace(tmp, target)
    return max(0, len(rows) - before)


def test_ollama_ready(url: str) -> bool:
    try:
        with urlopen(url.rstrip("/") + "/api/tags", timeout=5) as response:
            return response.status == 200
    except (OSError, URLError):
        return False


def compare_with_baseline(candidate: dict, baseline: dict) -> tuple[bool, list[str]]:
    failures = list(candidate.get("failures") or [])
    for key in ("usable_rate", "semantic_rate", "safe_rate", "stop_rate"):
        if float(candidate.get(key, 0.0)) < float(baseline.get(key, 0.0)):
            failures.append(f"{key} {candidate.get(key)} < base {baseline.get(key)}")
    if float(candidate.get("degenerate_rate", 1.0)) > float(baseline.get("degenerate_rate", 0.0)):
        failures.append(
            f"degenerate_rate {candidate.get('degenerate_rate')} > base "
            f"{baseline.get('degenerate_rate')}"
        )
    return not failures, failures


def pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.windll.kernel32.GetLastError() == 5
        try:
            code = ctypes.c_ulong()
            return bool(
                ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
                and code.value == 259
            )
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@contextmanager
def single_instance():
    STATE.mkdir(parents=True, exist_ok=True)
    lock = STATE / "qwen3b-24x7.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            old_pid = int(lock.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            old_pid = 0
        if old_pid and pid_is_alive(old_pid):
            raise SystemExit(f"[ERROR] Qwen 3B 24/7 đang chạy với PID {old_pid}")
        print(f"[WARN] Dọn stale lock Qwen 3B PID={old_pid or 'invalid'}", flush=True)
        lock.unlink(missing_ok=True)
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(fd, str(os.getpid()).encode("ascii"))
        os.close(fd)
        yield
    finally:
        lock.unlink(missing_ok=True)


def generate_teacher(args, cycle_id: str) -> int:
    if args.teacher_samples <= 0:
        return 0
    shard = ROOT / "data" / "bankvn" / "sft" / "qwen_teacher_shards" / f"{cycle_id}.jsonl"
    shard.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, str(BANKVN / "teacher_generate.py"), str(ROOT / "knowledge"),
        "--output", str(shard),
        "--dedupe-from", str(OLD_TEACHER),
        "--dedupe-from", str(RAW_TEACHER),
        "--model", args.teacher_model,
        "--max-samples", str(args.teacher_samples),
        "--max-attempts", str(args.teacher_max_attempts),
        "--workers", str(args.teacher_workers),
        "--num-predict", "384", "--retry-num-predict", "768",
        "--num-ctx", "4096", "--speech-profiles-per-source", "3",
        "--seed", str(args.seed),
    ]
    run(cmd)
    return merge_unique(RAW_TEACHER, shard)


def clean_dataset() -> dict:
    stats_path = STATE / "qwen-assistant-clean.json"
    run([
        sys.executable, str(BANKVN / "prepare_qwen_assistant_data.py"),
        str(OLD_TEACHER), str(RAW_TEACHER),
        "--output", str(CLEAN_DATA), "--stats", str(stats_path),
    ])
    return json.loads(stats_path.read_text(encoding="utf-8"))


def find_gguf(path: Path) -> Path:
    candidates = sorted(path.rglob("*.gguf"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not candidates:
        raise RuntimeError(f"Không tìm thấy GGUF sau train trong {path}")
    return candidates[0]


def train_and_benchmark(args, cycle_number: int, clean_hash: str) -> dict:
    slot = "a" if cycle_number % 2 else "b"
    output = ROOT / "models" / "bankvn" / f"qwen2.5-3b-24x7-{slot}"
    gguf_requested = ROOT / "models" / "bankvn" / f"qwen2.5-3b-24x7-{slot}-gguf"
    gguf_actual = Path(str(gguf_requested) + "_gguf")
    for disposable in (output, gguf_requested, gguf_actual):
        if disposable.exists():
            shutil.rmtree(disposable)

    try:
        subprocess.run(["ollama", "stop", args.teacher_model], cwd=str(ROOT), timeout=30)
    except Exception:
        pass
    progress("sft_training", cycle=cycle_number, clean_samples=count_jsonl(CLEAN_DATA))
    run([
        sys.executable, str(ROOT / "training" / "llm" / "train_lora.py"),
        "--dataset", str(CLEAN_DATA), "--mode", "assistant",
        "--base-model", BASE_MODEL, "--epochs", str(args.epochs),
        "--lr", str(args.learning_rate), "--lora-rank", str(args.lora_rank),
        "--batch-size", "1", "--grad-accum", "16",
        "--max-samples", str(args.max_samples),
        "--output-dir", str(output), "--gguf-dir", str(gguf_requested),
    ])
    gguf = find_gguf(gguf_actual)

    if not test_ollama_ready(args.test_ollama_url):
        raise RuntimeError(f"Ollama test chưa sẵn sàng tại {args.test_ollama_url}")
    modelfile = output / "Modelfile.test"
    modelfile.write_text(QWEN_MODELFILE.format(gguf=str(gguf.resolve())), encoding="utf-8")
    test_env = os.environ.copy()
    test_env["OLLAMA_HOST"] = args.test_ollama_host
    staging_model = "bankvn-qwen3b-staging"
    run(["ollama", "create", staging_model, "-f", str(modelfile)], env=test_env)

    progress("benchmarking", cycle=cycle_number, clean_samples=count_jsonl(CLEAN_DATA))
    candidate_output = STATE / "qwen3b-24x7-candidate-gate.json"
    rc = run([
        sys.executable, str(BANKVN / "assistant_benchmark.py"),
        "--model", staging_model, "--ollama-url", args.test_ollama_url,
        "--output", str(candidate_output),
    ], check=False)
    candidate = json.loads(candidate_output.read_text(encoding="utf-8"))
    baseline = json.loads((ROOT / args.baseline).read_text(encoding="utf-8"))
    passed, failures = compare_with_baseline(candidate, baseline)
    passed = passed and rc == 0
    candidate.update({
        "passed": passed,
        "failures": failures,
        "base_model": BASE_MODEL,
        "parameter_size": "3.1B",
        "clean_dataset_sha256": clean_hash,
        "clean_samples": count_jsonl(CLEAN_DATA),
        "trained_at_utc": utc_now(),
    })
    atomic_json(candidate_output, candidate)

    if passed:
        run(["ollama", "create", args.live_model, "-f", str(modelfile)], env=test_env)
        live_gate = dict(candidate)
        live_gate["model"] = args.live_model
        atomic_json(STATE / "assistant-gate.json", live_gate)
    else:
        atomic_json(STATE / "assistant-last-rejected.json", candidate)
    return candidate


def cycle(args, cycle_number: int) -> dict:
    started = time.perf_counter()
    cycle_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    progress("teacher_generation", cycle=cycle_number, base_model=BASE_MODEL)
    added = generate_teacher(args, cycle_id)
    progress("filtering_teacher", cycle=cycle_number, new_teacher_samples=added)
    stats = clean_dataset()
    if stats["kept"] < args.min_clean_samples:
        raise RuntimeError(
            f"Dữ liệu sạch chỉ có {stats['kept']} mẫu < {args.min_clean_samples}; không train"
        )
    clean_hash = file_sha256(CLEAN_DATA)
    previous = {}
    state_path = STATE / "continuous.json"
    if state_path.exists():
        try:
            previous = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    if previous.get("clean_dataset_sha256") == clean_hash and not args.force_retrain:
        result = {"passed": None, "failures": ["Không có dữ liệu sạch mới"]}
        promotion = "no_new_clean_data"
    else:
        result = train_and_benchmark(args, cycle_number, clean_hash)
        promotion = "eligible_test_candidate" if result["passed"] else "rejected_by_assistant_gate"

    state = {
        "last_cycle_utc": utc_now(), "profile": PROFILE,
        "base_model": BASE_MODEL, "parameter_size": "3.1B",
        "new_teacher_samples": added,
        "new_assistant_samples": stats["kept"], "new_router_samples": 0,
        "teacher_samples_total": stats["kept"],
        "clean_dataset": str(CLEAN_DATA), "clean_dataset_sha256": clean_hash,
        "cleaning": stats, "promotion": promotion,
        "assistant_gate_passed": result.get("passed"),
        "assistant_gate_failures": result.get("failures") or [],
        "production_model_unchanged": True,
        "cycle_elapsed_seconds": time.perf_counter() - started,
    }
    atomic_json(state_path, state)
    with (STATE / "history.jsonl").open("a", encoding="utf-8") as history:
        history.write(json.dumps(state, ensure_ascii=False) + "\n")
    return state


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Train Qwen2.5-3B BankVN an toàn 24/7")
    parser.add_argument("--teacher-model", default="qwen3.5:9b")
    parser.add_argument("--teacher-samples", type=int, default=100)
    parser.add_argument("--teacher-max-attempts", type=int, default=600)
    parser.add_argument("--teacher-workers", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--epochs", type=float, default=1.0)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--lora-rank", type=int, default=16)
    parser.add_argument("--max-samples", type=int, default=6000)
    parser.add_argument("--min-clean-samples", type=int, default=1000)
    parser.add_argument("--baseline", default="data/bankvn/state/qwen2.5-3b-base-strict-gate.json")
    parser.add_argument("--test-ollama-host", default="127.0.0.1:11435")
    parser.add_argument("--test-ollama-url", default="http://127.0.0.1:11435")
    parser.add_argument("--live-model", default="bankvn-candidate-live")
    parser.add_argument("--sleep-seconds", type=int, default=1800)
    parser.add_argument("--forever", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--force-retrain", action="store_true")
    args = parser.parse_args()

    with single_instance():
        STATE.mkdir(parents=True, exist_ok=True)
        if args.prepare_only:
            stats = clean_dataset()
            progress("prepared", clean_samples=stats["kept"])
            return
        (STATE / "paused.json").unlink(missing_ok=True)
        cycle_number = 1
        while True:
            try:
                state = cycle(args, cycle_number)
                progress(
                    "sleeping", cycle=cycle_number,
                    last_promotion=state["promotion"],
                    next_cycle_in_seconds=max(60, args.sleep_seconds),
                )
            except Exception as exc:
                progress("error", cycle=cycle_number, error=f"{type(exc).__name__}: {exc}")
                print(f"[ERROR] {type(exc).__name__}: {exc}", flush=True)
                if not args.forever:
                    raise
            if not args.forever:
                break
            cycle_number += 1
            time.sleep(max(60, args.sleep_seconds))


if __name__ == "__main__":
    main()
