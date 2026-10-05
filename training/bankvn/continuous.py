#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ctypes
from collections import Counter
import json
import math
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BANKVN = ROOT / "training" / "bankvn"
STATE_DIR = ROOT / "data" / "bankvn" / "state"
PROGRESS_HEARTBEAT_SECONDS = 20.0
_ACTIVE_PHASE: str | None = None


def count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(encoding="utf-8", errors="ignore") as f:
        return sum(1 for line in f if line.strip())


def merge_jsonl_unique(target: Path, shard: Path, key: str = "source_id") -> dict[str, int]:
    """Atomically merge valid shard records into target, deduped by a stable key."""
    existing_bytes = target.read_bytes() if target.exists() else b""
    used: set[str] = set()
    for raw in existing_bytes.splitlines():
        try:
            obj = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        value = str(obj.get(key) or "").strip()
        if value:
            used.add(value)

    stats = {"records": 0, "merged": 0, "duplicates": 0, "invalid": 0}
    additions: list[bytes] = []
    if shard.exists():
        for raw in shard.read_bytes().splitlines():
            if not raw.strip():
                continue
            stats["records"] += 1
            try:
                obj = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                stats["invalid"] += 1
                continue
            value = str(obj.get(key) or "").strip()
            if not value:
                stats["invalid"] += 1
                continue
            if value in used:
                stats["duplicates"] += 1
                continue
            used.add(value)
            additions.append(raw.strip() + b"\n")

    if not additions:
        return stats

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.merge-{os.getpid()}.tmp")
    with tmp.open("wb") as dst:
        dst.write(existing_bytes)
        if existing_bytes and not existing_bytes.endswith(b"\n"):
            dst.write(b"\n")
        for raw in additions:
            dst.write(raw)
        dst.flush()
        os.fsync(dst.fileno())
    os.replace(tmp, target)
    stats["merged"] = len(additions)
    return stats


def count_new_jsonl_field(path: Path, start_line: int, field: str) -> dict[str, int]:
    counts: Counter[str] = Counter()
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", errors="ignore") as f:
        seen = 0
        for line in f:
            if not line.strip():
                continue
            seen += 1
            if seen <= start_line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            value = str(obj.get(field) or "").strip()
            if value:
                counts[value] += 1
    return dict(counts)


def write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def write_progress(phase: str, **extra) -> None:
    global _ACTIVE_PHASE
    _ACTIVE_PHASE = phase
    path = STATE_DIR / "progress.json"
    payload: dict = {}
    try:
        old = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(old, dict):
            payload.update(old)
    except (OSError, json.JSONDecodeError):
        pass
    payload.update(extra)
    payload["phase"] = phase
    payload["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    write_json_atomic(path, payload)


def append_cycle_history(payload: dict) -> None:
    path = STATE_DIR / "history.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def run(cmd: list[str], check: bool = True) -> int:
    print("[RUN]", " ".join(cmd), flush=True)
    child_env = os.environ.copy()
    child_env["PYTHONUTF8"] = "1"
    child_env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.Popen(cmd, cwd=str(ROOT), env=child_env)
    started = time.perf_counter()
    process_name = Path(cmd[1] if len(cmd) > 1 else cmd[0]).name
    try:
        while True:
            try:
                return_code = proc.wait(timeout=PROGRESS_HEARTBEAT_SECONDS)
                break
            except subprocess.TimeoutExpired:
                write_progress(
                    _ACTIVE_PHASE or "running",
                    active_process=process_name,
                    active_process_pid=proc.pid,
                    active_process_elapsed_seconds=time.perf_counter() - started,
                )
    except BaseException:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        raise

    write_progress(
        _ACTIVE_PHASE or "running",
        active_process=None,
        active_process_pid=None,
        active_process_elapsed_seconds=time.perf_counter() - started,
    )
    if check and return_code:
        raise RuntimeError(f"Lệnh lỗi {return_code}: {' '.join(cmd)}")
    return return_code


def generate_teacher_shards(args, teacher_inputs: list[str], output: Path) -> dict:
    target_samples = max(0, args.teacher_samples)
    batch_size = max(1, args.teacher_batch_size)
    max_batches = max(1, args.teacher_max_batches)
    attempts_per_batch = (
        max(1, math.ceil(args.teacher_max_attempts / max_batches))
        if args.teacher_max_attempts > 0 else 0
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    shard_root = ROOT / args.teacher_shard_dir / stamp
    shard_root.mkdir(parents=True, exist_ok=True)
    manifest_path = shard_root / "manifest.json"
    batches: list[dict] = []
    total_merged = total_invalid = total_duplicates = 0
    successful_processes = 0

    for batch_index in range(1, max_batches + 1):
        remaining = target_samples - total_merged
        if remaining <= 0:
            break
        batch_target = min(batch_size, remaining)
        shard = shard_root / f"teacher-{batch_index:03d}.jsonl"
        write_progress(
            "teacher_generation",
            teacher_batch=batch_index,
            teacher_max_batches=max_batches,
            teacher_batch_target=batch_target,
            teacher_merged_this_cycle=total_merged,
            teacher_target_this_cycle=target_samples,
            teacher_shard=str(shard),
        )
        cmd = [
            sys.executable, str(BANKVN / "teacher_generate.py"), *teacher_inputs,
            "--output", str(shard),
            "--dedupe-from", str(output),
            "--model", args.teacher_model,
            "--max-samples", str(batch_target),
            "--workers", str(args.teacher_workers),
            "--source-chars", str(args.teacher_source_chars),
            "--source-overlap-chars", str(args.teacher_source_overlap_chars),
            "--max-chunks-per-source", str(args.teacher_max_chunks_per_source),
            "--num-predict", str(args.teacher_num_predict),
            "--retry-num-predict", str(args.teacher_retry_num_predict),
            "--num-ctx", str(args.teacher_num_ctx),
            "--source-min-score", str(args.teacher_source_min_score),
            "--speech-profiles-per-source", str(args.teacher_speech_profiles_per_source),
            "--seed", str(args.teacher_seed + batch_index - 1),
        ]
        if attempts_per_batch > 0:
            cmd += ["--max-attempts", str(attempts_per_batch)]
        rc = run(cmd, check=False)
        successful_processes += int(rc == 0)
        merge_stats = merge_jsonl_unique(output, shard)
        total_merged += merge_stats["merged"]
        total_invalid += merge_stats["invalid"]
        total_duplicates += merge_stats["duplicates"]
        batch_state = {
            "batch": batch_index,
            "target": batch_target,
            "max_attempts": attempts_per_batch,
            "return_code": rc,
            "shard": str(shard),
            **merge_stats,
        }
        batches.append(batch_state)
        write_json_atomic(manifest_path, {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "target_samples": target_samples,
            "batch_size": batch_size,
            "max_batches": max_batches,
            "max_attempts_total": args.teacher_max_attempts,
            "num_predict": args.teacher_num_predict,
            "retry_num_predict": args.teacher_retry_num_predict,
            "merged": total_merged,
            "invalid": total_invalid,
            "duplicates": total_duplicates,
            "batches": batches,
        })
        write_progress(
            "teacher_generation",
            teacher_batch=batch_index,
            teacher_merged_this_cycle=total_merged,
            teacher_target_this_cycle=target_samples,
        )
        if rc:
            print(
                f"[WARN] Teacher shard {batch_index} lỗi mã {rc}; đã giữ "
                f"{merge_stats['merged']} mẫu hợp lệ và tiếp tục",
                flush=True,
            )

    if not successful_processes and not total_merged:
        raise RuntimeError("Tất cả tiến trình teacher shard đều lỗi và không gộp được mẫu nào")
    return {
        "root": str(shard_root),
        "manifest": str(manifest_path),
        "batches": len(batches),
        "merged": total_merged,
        "invalid": total_invalid,
        "duplicates": total_duplicates,
        "target": target_samples,
    }


def free_vram_mb() -> int | None:
    try:
        out = subprocess.check_output([
            "nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"
        ], text=True, timeout=10)
        return int(out.strip().splitlines()[0])
    except Exception:
        return None


def pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False

    if os.name == "nt":
        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            # ERROR_ACCESS_DENIED means the PID exists but cannot be queried.
            return kernel32.GetLastError() == 5
        try:
            exit_code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return True
            return exit_code.value == still_active
        finally:
            kernel32.CloseHandle(handle)

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@contextmanager
def single_instance():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock = STATE_DIR / "continuous.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            old_pid = int(lock.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            old_pid = 0

        if old_pid and pid_is_alive(old_pid):
            raise SystemExit(
                f"[ERROR] BankVN continuous đã chạy với PID {old_pid}: {lock}"
            )

        print(f"[WARN] Dọn stale lock BankVN (PID {old_pid or 'không hợp lệ'}): {lock}", flush=True)
        lock.unlink(missing_ok=True)
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise SystemExit(f"[ERROR] BankVN continuous lock vừa được tiến trình khác tạo: {lock}")
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        lock.unlink(missing_ok=True)


def stop_teacher(model: str) -> None:
    try:
        subprocess.run(["ollama", "stop", model], cwd=str(ROOT), timeout=30,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def cycle(args) -> None:
    cycle_started = time.perf_counter()
    write_progress(
        "starting",
        cycle_started_utc=datetime.now(timezone.utc).isoformat(),
        profile=args.profile_name,
        error=None,
    )
    clean = ROOT / "data" / "bankvn" / "clean" / "corpus.jsonl"
    tokenizer = ROOT / args.tokenizer
    raw = ROOT / "data" / "bankvn" / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    fetched_docs = 0
    if args.fetch_docs_per_cycle > 0:
        write_progress("fetching_data")
        fetch_output = ROOT / args.fetch_output
        before_fetch = count_jsonl(fetch_output)
        fetch_rc = run([
            sys.executable, str(BANKVN / "fetch_sources.py"),
            "--dataset", args.fetch_dataset,
            "--output", str(fetch_output),
            "--max-docs", str(args.fetch_docs_per_cycle),
            "--resume",
        ], check=False)
        after_fetch = count_jsonl(fetch_output)
        fetched_docs = max(0, after_fetch - before_fetch)
        if fetch_rc:
            print(
                f"[WARN] fetch source lỗi mã {fetch_rc}; tiếp tục bằng corpus hiện có",
                flush=True,
            )

    inputs = [str(raw), str(ROOT / "data" / "kich_ban_van_noi.txt"),
              str(ROOT / "knowledge" / "faq" / "faq_banking.md")]
    write_progress("preparing_corpus", fetched_docs=fetched_docs)
    run([sys.executable, str(BANKVN / "prepare_corpus.py"), *inputs,
         "--output", str(clean),
         "--min-score", str(args.corpus_min_score),
         "--strict-vietnamese"])
    corpus_docs = count_jsonl(clean)
    if corpus_docs < args.min_corpus_docs and not args.force:
        raise RuntimeError(
            f"Corpus strict Vietnamese chỉ có {corpus_docs} docs < {args.min_corpus_docs}; "
            "không train để tránh overfit dữ liệu quá nhỏ"
        )

    banking_corpus = ROOT / "data" / "bankvn" / "clean" / "banking_corpus.jsonl"
    run([sys.executable, str(BANKVN / "mine_banking_corpus.py"),
         "--input", str(clean), "--output", str(banking_corpus)])
    banking_docs = count_jsonl(banking_corpus)

    if not (tokenizer / "tokenizer.json").exists():
        run([sys.executable, str(BANKVN / "train_tokenizer.py"),
             "--corpus", str(clean), "--output", str(tokenizer)])

    sft_data = ROOT / "data" / "bankvn" / "sft" / "teacher.jsonl"
    router_teacher_data = ROOT / args.router_teacher_output
    assistant_teacher_before = count_jsonl(sft_data)
    router_teacher_before = count_jsonl(router_teacher_data)
    teacher_before = assistant_teacher_before + router_teacher_before
    teacher_started = time.perf_counter()
    write_progress(
        "teacher_generation",
        teacher_samples_before=teacher_before,
        teacher_model=args.teacher_model,
    )
    teacher_shard_state = {
        "root": None,
        "manifest": None,
        "batches": 0,
        "merged": 0,
        "invalid": 0,
        "duplicates": 0,
        "target": args.teacher_samples,
    }
    if args.router_teacher_samples_per_class > 0:
        router_teacher_before_generate = count_jsonl(router_teacher_data)
        router_teacher_rc = run([
            sys.executable, str(BANKVN / "teacher_router_generate.py"),
            "--output", str(router_teacher_data),
            "--model", args.teacher_model,
            "--samples-per-class", str(args.router_teacher_samples_per_class),
            "--batch-size", str(args.router_teacher_batch_size),
            "--workers", str(args.teacher_workers),
            "--num-predict", str(args.router_teacher_num_predict),
            "--num-ctx", str(args.teacher_num_ctx),
            "--temperature", str(args.router_teacher_temperature),
        ], check=False)
        router_teacher_after_generate = count_jsonl(router_teacher_data)
        router_teacher_added = max(
            0, router_teacher_after_generate - router_teacher_before_generate
        )
        if router_teacher_rc == 2:
            print(
                f"[WARN] Router teacher chưa đủ quota; giữ {router_teacher_added} "
                "mẫu mới hợp lệ và tiếp tục cycle",
                flush=True,
            )
        elif router_teacher_rc:
            raise RuntimeError(f"Router teacher {args.teacher_model} lỗi với mã {router_teacher_rc}")
    if args.teacher_samples > 0:
        teacher_inputs = [
            str(ROOT / "knowledge"),
        ]
        if banking_docs > 0:
            teacher_inputs.append(str(banking_corpus))
        teacher_shard_state = generate_teacher_shards(args, teacher_inputs, sft_data)
    stop_teacher(args.teacher_model)
    teacher_elapsed_seconds = time.perf_counter() - teacher_started
    teacher_after = count_jsonl(sft_data) + count_jsonl(router_teacher_data)
    new_teacher_samples = max(0, teacher_after - teacher_before)
    assistant_teacher_after = count_jsonl(sft_data)
    router_teacher_after = count_jsonl(router_teacher_data)
    new_assistant_samples = max(0, assistant_teacher_after - assistant_teacher_before)
    new_router_samples = max(0, router_teacher_after - router_teacher_before)
    new_speech_profiles = count_new_jsonl_field(
        sft_data, assistant_teacher_before, "speech_profile"
    )
    new_speech_regions = count_new_jsonl_field(
        sft_data, assistant_teacher_before, "speech_region"
    )
    teacher_samples_per_minute = (
        new_teacher_samples / (teacher_elapsed_seconds / 60.0)
        if new_teacher_samples > 0 and teacher_elapsed_seconds > 0 else 0.0
    )

    # Teacher 9B phải rời GPU trước khi student train. Kiểm tra ở đây thay vì
    # đầu cycle vì Qwen đang resident là trạng thái bình thường của bước teacher.
    free = free_vram_mb()
    if free is not None and free < args.min_free_vram_mb and not args.force:
        raise RuntimeError(
            f"VRAM trống sau khi dừng teacher chỉ {free}MB < {args.min_free_vram_mb}MB"
        )

    # Router đã tách khỏi student sinh văn bản. Qwen 9B sinh ví dụ intent, một
    # classifier rất nhỏ học profile/product/assistant và chỉ trở thành candidate.
    # Không ghi đè model router đang dùng ở production trong vòng continual.
    router_classifier_state: dict = {
        "status": "no_new_router_data",
        "candidate": None,
        "benchmark": None,
        "gate": None,
    }
    if new_router_samples > 0 and router_teacher_data.exists():
        write_progress(
            "router_training",
            new_teacher_samples=new_teacher_samples,
            new_assistant_samples=new_assistant_samples,
            new_router_samples=new_router_samples,
        )
        classifier_candidate = ROOT / args.router_classifier_candidate
        classifier_train_cmd = [
            sys.executable, str(BANKVN / "router_classifier.py"), "train",
            "--dataset", str(router_teacher_data.relative_to(ROOT)),
        ]
        if sft_data.exists() and sft_data.stat().st_size > 0:
            classifier_train_cmd += ["--dataset", str(sft_data.relative_to(ROOT))]
        classifier_train_cmd += [
            "--output", str(classifier_candidate.relative_to(ROOT)),
            "--alpha", str(args.router_classifier_alpha),
        ]
        run(classifier_train_cmd)

        classifier_benchmark = ROOT / args.router_classifier_benchmark_output
        benchmark_dataset = ROOT / args.router_classifier_benchmark_dataset
        if not benchmark_dataset.exists():
            raise RuntimeError(f"Không thấy router classifier benchmark: {benchmark_dataset}")
        run([
            sys.executable, str(BANKVN / "router_classifier.py"), "benchmark",
            "--model", str(classifier_candidate.relative_to(ROOT)),
            "--dataset", str(benchmark_dataset.relative_to(ROOT)),
            "--output", str(classifier_benchmark.relative_to(ROOT)),
            "--min-confidence", str(args.router_classifier_min_confidence),
            "--min-margin", str(args.router_classifier_min_margin),
        ])
        classifier_metrics = json.loads(classifier_benchmark.read_text(encoding="utf-8"))

        current_metrics = None
        current_model = ROOT / args.router_classifier_current
        current_benchmark = ROOT / args.router_classifier_baseline_output
        if current_model.exists():
            run([
                sys.executable, str(BANKVN / "router_classifier.py"), "benchmark",
                "--model", str(current_model.relative_to(ROOT)),
                "--dataset", str(benchmark_dataset.relative_to(ROOT)),
                "--output", str(current_benchmark.relative_to(ROOT)),
                "--min-confidence", str(args.router_classifier_min_confidence),
                "--min-margin", str(args.router_classifier_min_margin),
            ])
            current_metrics = json.loads(current_benchmark.read_text(encoding="utf-8"))

        domain_floor = args.router_classifier_min_domain_accuracy
        tool_floor = args.router_classifier_min_tool_call_accuracy
        no_tool_floor = args.router_classifier_min_no_tool_accuracy
        hallucination_ceiling = args.router_classifier_max_hallucination_rate
        latency_ceiling = args.router_classifier_max_p95_ms
        if current_metrics:
            domain_floor = max(domain_floor, current_metrics.get("domain_accuracy", 0.0))
            tool_floor = max(tool_floor, current_metrics.get("tool_call_accuracy", 0.0))
            no_tool_floor = max(no_tool_floor, current_metrics.get("no_tool_accuracy", 0.0))
            hallucination_ceiling = min(
                hallucination_ceiling,
                current_metrics.get("hallucination_rate", hallucination_ceiling),
            )
            current_p95 = float(current_metrics.get("p95_latency_ms") or 0.0)
            if current_p95 > 0:
                latency_ceiling = min(
                    latency_ceiling,
                    max(0.5, current_p95 * args.router_classifier_latency_factor),
                )
        classifier_checks = {
            "domain_accuracy": classifier_metrics.get("domain_accuracy", 0.0)
            >= domain_floor,
            "tool_call_accuracy": classifier_metrics.get("tool_call_accuracy", 0.0)
            >= tool_floor,
            "no_tool_accuracy": classifier_metrics.get("no_tool_accuracy", 0.0)
            >= no_tool_floor,
            "hallucination_rate": classifier_metrics.get("hallucination_rate", 1.0)
            <= hallucination_ceiling,
            "p95_latency_ms": classifier_metrics.get("p95_latency_ms", float("inf"))
            <= latency_ceiling,
        }
        classifier_eligible = all(classifier_checks.values())
        classifier_gate = ROOT / args.router_classifier_gate_output
        classifier_gate.parent.mkdir(parents=True, exist_ok=True)
        classifier_gate.write_text(json.dumps({
            "eligible_manual_review": classifier_eligible,
            "checks": classifier_checks,
            "metrics": classifier_metrics,
            "current_metrics": current_metrics,
            "required": {
                "domain_accuracy": domain_floor,
                "tool_call_accuracy": tool_floor,
                "no_tool_accuracy": no_tool_floor,
                "hallucination_rate_max": hallucination_ceiling,
                "p95_latency_ms_max": latency_ceiling,
            },
            "candidate": str(classifier_candidate),
            "note": "Không tự promote; cần holdout độc lập và review trước khi thay router production.",
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        router_classifier_state = {
            "status": "eligible_manual_review" if classifier_eligible else "rejected_by_gate",
            "candidate": str(classifier_candidate),
            "benchmark": str(classifier_benchmark),
            "current_benchmark": str(current_benchmark) if current_metrics else None,
            "gate": str(classifier_gate),
        }

    pretrain_out = ROOT / args.pretrain_output
    if args.enable_pretrain:
        write_progress("pretraining")
        pretrain_cmd = [
            sys.executable, str(BANKVN / "pretrain.py"),
            "--profile", str(ROOT / args.profile),
            "--tokenizer", str(tokenizer),
            "--corpus", str(clean),
            "--output", str(pretrain_out),
        ]
        has_checkpoint = any(pretrain_out.glob("checkpoint-*")) if pretrain_out.exists() else False
        if has_checkpoint:
            pretrain_cmd += ["--resume", "--additional-steps", str(args.steps_per_cycle)]
        else:
            if args.init_from:
                init_from = ROOT / args.init_from
                if not init_from.exists():
                    raise RuntimeError(f"Không thấy checkpoint khởi tạo fast lineage: {init_from}")
                pretrain_cmd += ["--init-from", str(init_from)]
            pretrain_cmd += ["--max-steps", str(args.steps_per_cycle)]
        run(pretrain_cmd)
        base = pretrain_out / "final"
    else:
        base = ROOT / args.sft_base
        if not base.exists():
            raise RuntimeError(f"Không thấy SFT base ổn định: {base}")

    candidate = ROOT / args.sft_output
    train_elapsed_seconds = 0.0
    sft_quality: dict | None = None
    primary_sft_data = (
        sft_data if sft_data.exists() and sft_data.stat().st_size > 0 else None
    )
    if (new_assistant_samples > 0 and primary_sft_data is not None
            and primary_sft_data.exists() and primary_sft_data.stat().st_size > 0):
        write_progress(
            "sft_training",
            new_teacher_samples=new_teacher_samples,
            new_assistant_samples=new_assistant_samples,
            new_router_samples=new_router_samples,
        )
        sft_cmd = [
            sys.executable, str(BANKVN / "sft.py"), "--base", str(base),
            "--dataset", str(primary_sft_data), "--output", str(candidate),
            "--epochs", str(args.sft_epochs), "--lora-rank", str(args.lora_rank),
            "--min-updates", str(args.sft_min_updates),
            "--lr", str(args.sft_lr),
            "--batch-size", str(args.sft_batch_size),
            "--grad-accum", str(args.sft_grad_accum),
            "--replay-repeat", str(args.sft_replay_repeat),
            "--max-source-records", str(args.sft_max_source_records),
            "--max-replay-records", str(args.sft_max_replay_records),
            "--assistant-router-ratio", str(args.sft_assistant_router_ratio),
            *(["--balance-router-tools"] if args.sft_balance_router_tools else ["--no-balance-router-tools"]),
            *(["--router-format-tokens"] if args.sft_router_format_tokens else []),
            *(["--no-gradient-checkpointing"] if args.sft_no_gradient_checkpointing else []),
        ]
        for replay_dataset in args.sft_replay_dataset:
            sft_cmd += ["--replay-dataset", str(ROOT / replay_dataset)]
        train_started = time.perf_counter()
        run(sft_cmd)
        train_elapsed_seconds = time.perf_counter() - train_started
        metrics_path = candidate / "metrics.json"
        if metrics_path.exists():
            raw_metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            quality_keys = (
                "sft_training_loss",
                "sft_eval_loss_before",
                "sft_eval_loss_after",
                "sft_eval_loss_improvement_pct",
                "train_runtime",
                "train_samples_per_second",
                "cuda_peak_allocated_gb",
                "cuda_peak_reserved_gb",
            )
            sft_quality = {key: raw_metrics.get(key) for key in quality_keys}

    candidate_final = candidate / "final"
    benchmark_elapsed_seconds = 0.0
    benchmark_error: str | None = None
    gate_rc: int | None = None
    promotion = "no_new_teacher_data"
    if candidate_final.exists() and new_assistant_samples > 0:
        promotion = "benchmark_skipped_not_eligible" if args.skip_benchmark else "pending_benchmark"
        if not args.skip_benchmark:
            write_progress("benchmarking")
            baseline = ROOT / args.benchmark_baseline
            benchmark_dataset = ROOT / args.benchmark_dataset
            if not baseline.exists():
                raise RuntimeError(f"Không thấy baseline benchmark: {baseline}")
            if not benchmark_dataset.exists():
                raise RuntimeError(f"Không thấy dataset benchmark: {benchmark_dataset}")
            benchmark_output = ROOT / args.benchmark_output
            gate_output = ROOT / args.gate_output
            benchmark_started = time.perf_counter()
            try:
                run([
                    sys.executable, str(BANKVN / "export_ollama.py"),
                    "--model-dir", str(candidate_final),
                    "--name", args.candidate_model_name,
                    "--num-ctx", str(args.teacher_num_ctx),
                    "--ollama-host", args.benchmark_ollama_host,
                ])
                run([
                    sys.executable, str(BANKVN / "router_benchmark.py"),
                    "--model", args.candidate_model_name,
                    "--dataset", str(benchmark_dataset),
                    "--output", str(benchmark_output),
                    "--ollama-url", args.benchmark_ollama_url,
                ])
                gate_rc = run([
                    sys.executable, str(BANKVN / "gate.py"),
                    "--baseline", str(baseline),
                    "--candidate", str(benchmark_output),
                    "--latency-factor", str(args.gate_latency_factor),
                    "--min-domain-accuracy", str(args.gate_min_domain_accuracy),
                    "--min-tool-call-accuracy", str(args.gate_min_tool_call_accuracy),
                    "--max-hallucination-rate", str(args.gate_max_hallucination_rate),
                    "--min-decode-speed-factor", str(args.gate_min_decode_speed_factor),
                    "--min-assistant-usable-rate", str(args.gate_min_assistant_usable_rate),
                    "--max-degenerate-rate", str(args.gate_max_degenerate_rate),
                    "--min-stop-rate", str(args.gate_min_stop_rate),
                    "--result", str(gate_output),
                ], check=False)
                promotion = "eligible_manual_review" if gate_rc == 0 else "rejected_by_gate"
            except Exception as exc:
                benchmark_error = f"{type(exc).__name__}: {exc}"
                promotion = "benchmark_error"
            benchmark_elapsed_seconds = time.perf_counter() - benchmark_started

    state = {
        "last_cycle_utc": datetime.now(timezone.utc).isoformat(),
        "profile": args.profile_name,
        "fetched_docs": fetched_docs,
        "corpus_docs": corpus_docs,
        "banking_corpus_docs": banking_docs,
        "new_teacher_samples": new_teacher_samples,
        "new_assistant_samples": new_assistant_samples,
        "new_router_samples": new_router_samples,
        "teacher_samples_total": teacher_after,
        "teacher_elapsed_seconds": teacher_elapsed_seconds,
        "teacher_samples_per_minute": teacher_samples_per_minute,
        "teacher_workers": args.teacher_workers,
        "teacher_shards": teacher_shard_state,
        "new_speech_profiles": new_speech_profiles,
        "new_speech_regions": new_speech_regions,
        "enable_pretrain": args.enable_pretrain,
        "pretrain_final": str(pretrain_out / "final") if args.enable_pretrain else None,
        "pretrain_output": str(pretrain_out) if args.enable_pretrain else None,
        "init_from": args.init_from or None,
        "sft_base": str(base),
        "sft_lr": args.sft_lr,
        "sft_epochs": args.sft_epochs,
        "sft_min_updates": args.sft_min_updates,
        "sft_balance_router_tools": args.sft_balance_router_tools,
        "sft_assistant_router_ratio": args.sft_assistant_router_ratio,
        "sft_router_format_tokens": args.sft_router_format_tokens,
        "sft_candidate": str(candidate_final) if candidate_final.exists() else None,
        "sft_quality": sft_quality,
        "train_elapsed_seconds": train_elapsed_seconds,
        "benchmark_elapsed_seconds": benchmark_elapsed_seconds,
        "benchmark_error": benchmark_error,
        "benchmark_output": (str(ROOT / args.benchmark_output)
                             if not args.skip_benchmark else None),
        "gate_output": (str(ROOT / args.gate_output)
                        if not args.skip_benchmark else None),
        "gate_return_code": gate_rc,
        "router_classifier": router_classifier_state,
        "promotion": promotion,
        "cycle_elapsed_seconds": time.perf_counter() - cycle_started,
    }
    write_json_atomic(STATE_DIR / "continuous.json", state)
    append_cycle_history(state)
    if promotion in {"rejected_by_gate", "benchmark_error"}:
        write_progress(
            "quality_rejected",
            last_cycle_utc=state["last_cycle_utc"],
            last_promotion=promotion,
            error=benchmark_error,
            cycle_elapsed_seconds=state["cycle_elapsed_seconds"],
        )
        raise SystemExit(
            "[STOP] Candidate không qua kiểm tra sinh câu; dừng 24/7 để tránh train mù."
        )
    write_progress(
        "sleeping",
        last_cycle_utc=state["last_cycle_utc"],
        last_promotion=promotion,
        cycle_elapsed_seconds=state["cycle_elapsed_seconds"],
        next_cycle_in_seconds=max(30, args.sleep_seconds),
    )
    print(f"[OK] Cycle xong; promotion={promotion}; production chưa tự động đổi model.")


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description="Vòng học liên tục BankVN")
    ap.add_argument("--profile", default="training/bankvn/configs/bankvn-350m-rtx5070-continual.json")
    ap.add_argument("--profile-name", default="bankvn-350m-rtx5070-continual")
    ap.add_argument("--fetch-dataset", default="hoanghai2110/vi-pretrain-clean")
    ap.add_argument("--fetch-output",
                    default="data/bankvn/raw/vi_pretrain_clean_20k.jsonl")
    ap.add_argument("--fetch-docs-per-cycle", type=int, default=0,
                    help="0 = không tải thêm; >0 = append từng batch trước mỗi cycle")
    ap.add_argument("--tokenizer", default="models/bankvn/tokenizer-sp-smoke6")
    ap.add_argument("--pretrain-output",
                    default="models/bankvn/pretrain/bankvn-continual-20260920")
    ap.add_argument("--enable-pretrain", action="store_true",
                    help="Bật continual pretrain trước SFT. Mặc định tắt để bảo toàn router.")
    ap.add_argument("--init-from",
                    default="models/bankvn/sft/bankvn-smoke6-router-refine1/final",
                    help="Chỉ dùng lần đầu của lineage mới; các cycle sau resume checkpoint cùng profile")
    ap.add_argument("--sft-base",
                    default="models/bankvn/sft/bankvn-smoke6-router-refine1/final",
                    help="Checkpoint ổn định để distill teacher khi continual pretrain đang tắt")
    ap.add_argument("--steps-per-cycle", type=int, default=200)
    ap.add_argument("--teacher-model", default="qwen3.5:9b")
    ap.add_argument("--teacher-samples", type=int, default=200)
    ap.add_argument("--router-teacher-output",
                    default="data/bankvn/sft/router_teacher.jsonl")
    ap.add_argument("--router-teacher-samples-per-class", type=int, default=20)
    ap.add_argument("--router-teacher-batch-size", type=int, default=3)
    ap.add_argument("--router-teacher-num-predict", type=int, default=512)
    ap.add_argument("--router-teacher-temperature", type=float, default=0.7)
    ap.add_argument("--router-classifier-candidate",
                    default="models/bankvn/router/candidates/router_nb_candidate.json")
    ap.add_argument("--router-classifier-alpha", type=float, default=0.35)
    ap.add_argument("--router-classifier-benchmark-dataset",
                    default="training/bankvn/bench/router_holdout_v1.jsonl")
    ap.add_argument("--router-classifier-benchmark-output",
                    default="data/bankvn/state/router-classifier-candidate.json")
    ap.add_argument("--router-classifier-current",
                    default="models/bankvn/router/router_nb_current.json")
    ap.add_argument("--router-classifier-baseline-output",
                    default="data/bankvn/state/router-classifier-current.json")
    ap.add_argument("--router-classifier-gate-output",
                    default="data/bankvn/state/router-classifier-gate.json")
    ap.add_argument("--router-classifier-min-confidence", type=float, default=0.62)
    ap.add_argument("--router-classifier-min-margin", type=float, default=1.5)
    ap.add_argument("--router-classifier-min-domain-accuracy", type=float, default=0.95)
    ap.add_argument("--router-classifier-min-tool-call-accuracy", type=float, default=0.95)
    ap.add_argument("--router-classifier-min-no-tool-accuracy", type=float, default=0.95)
    ap.add_argument("--router-classifier-max-hallucination-rate", type=float, default=0.05)
    ap.add_argument("--router-classifier-max-p95-ms", type=float, default=1.0)
    ap.add_argument("--router-classifier-latency-factor", type=float, default=1.5)
    ap.add_argument(
        "--teacher-max-attempts", type=int, default=1200,
        help="Tổng ngân sách candidate, chia đều giữa các teacher shard",
    )
    ap.add_argument("--teacher-batch-size", type=int, default=20,
                    help="Số mẫu hợp lệ tối đa trong mỗi file shard")
    ap.add_argument("--teacher-max-batches", type=int, default=12)
    ap.add_argument("--teacher-shard-dir", default="data/bankvn/sft/teacher_shards")
    ap.add_argument("--teacher-seed", type=int, default=42)
    ap.add_argument("--teacher-workers", type=int, default=2)
    ap.add_argument("--teacher-source-chars", type=int, default=1600)
    ap.add_argument("--teacher-source-overlap-chars", type=int, default=160)
    ap.add_argument("--teacher-max-chunks-per-source", type=int, default=8)
    ap.add_argument("--teacher-num-predict", type=int, default=384)
    ap.add_argument("--teacher-retry-num-predict", type=int, default=768,
                    help="Retry JSON bị cắt với output budget lớn hơn")
    ap.add_argument("--teacher-num-ctx", type=int, default=4096)
    ap.add_argument("--teacher-source-min-score", type=float, default=0.24)
    ap.add_argument("--teacher-speech-profiles-per-source", type=int, default=3,
                    help="Số phong cách văn nói mới trên mỗi chunk trong teacher generation")
    ap.add_argument(
        "--corpus-min-score", type=float, default=0.18,
        help=(
            "Ngưỡng cho corpus pretrain đã gắn nhãn vi; 0.18 giữ dữ liệu Việt sạch "
            "mà không làm corpus tụt dưới gate. Teacher/output vẫn dùng gate chặt hơn."
        ),
    )
    ap.add_argument("--min-corpus-docs", type=int, default=10000)
    ap.add_argument("--sft-epochs", type=float, default=0.25)
    ap.add_argument("--sft-output", default="models/bankvn/sft/bankvn-candidate")
    ap.add_argument("--sft-min-updates", type=int, default=0,
                    help="0 = không ép update tối thiểu; conservative continual SFT")
    ap.add_argument("--sft-batch-size", type=int, default=1)
    ap.add_argument("--sft-grad-accum", type=int, default=8)
    ap.add_argument("--sft-lr", type=float, default=2e-6,
                    help="LR conservative đã giữ đúng 2/2 core router probes")
    ap.add_argument("--sft-replay-dataset", action="append", default=[],
                    help="Dataset neo router đã validate; có thể truyền nhiều lần")
    ap.add_argument("--sft-replay-repeat", type=int, default=1)
    ap.add_argument("--sft-max-source-records", type=int, default=600)
    ap.add_argument("--sft-max-replay-records", type=int, default=600)
    ap.add_argument("--sft-assistant-router-ratio", type=float, default=0.5)
    format_tokens = ap.add_mutually_exclusive_group()
    format_tokens.add_argument(
        "--sft-router-format-tokens",
        dest="sft_router_format_tokens",
        action="store_true",
        help="Bật thí nghiệm token JSON/tool chuyên dụng; mặc định tắt vì clean40 đã regression.",
    )
    format_tokens.add_argument(
        "--sft-no-router-format-tokens",
        dest="sft_router_format_tokens",
        action="store_false",
        help="Giữ tương thích với lệnh cũ; token format đang tắt mặc định.",
    )
    ap.set_defaults(sft_router_format_tokens=False)
    ap.add_argument("--sft-no-balance-router-tools", dest="sft_balance_router_tools",
                    action="store_false",
                    help="Tắt oversampling cân bằng tool router cho thí nghiệm đối chứng")
    ap.set_defaults(sft_balance_router_tools=True)
    ap.add_argument("--sft-no-gradient-checkpointing", action="store_true")
    ap.add_argument("--lora-rank", type=int, default=0)
    ap.add_argument("--benchmark-dataset",
                    default="training/bankvn/bench/router_cases.jsonl")
    ap.add_argument("--benchmark-baseline",
                    default="data/bankvn/state/router-baseline-clean40.json")
    ap.add_argument("--benchmark-output",
                    default="data/bankvn/state/router-candidate-continuous.json")
    ap.add_argument("--gate-output", default="data/bankvn/state/router-last-gate.json")
    ap.add_argument("--candidate-model-name", default="bankvn-candidate-continuous")
    ap.add_argument("--legacy-generative-router-gate", action="store_true",
                    help="Tương thích lệnh cũ; generation gate nay luôn bắt buộc.")
    ap.add_argument("--benchmark-ollama-host", default="127.0.0.1:11435")
    ap.add_argument("--benchmark-ollama-url", default="http://127.0.0.1:11435")
    ap.add_argument("--gate-latency-factor", type=float, default=1.25)
    ap.add_argument("--gate-min-domain-accuracy", type=float, default=0.90)
    ap.add_argument("--gate-min-tool-call-accuracy", type=float, default=0.90)
    ap.add_argument("--gate-max-hallucination-rate", type=float, default=0.10)
    ap.add_argument("--gate-min-decode-speed-factor", type=float, default=0.90)
    ap.add_argument("--gate-min-assistant-usable-rate", type=float, default=0.90)
    ap.add_argument("--gate-max-degenerate-rate", type=float, default=0.0)
    ap.add_argument("--gate-min-stop-rate", type=float, default=0.95)
    ap.add_argument("--skip-benchmark", action="store_true",
                    help="Chỉ dùng cho debug; 24/7 production không nên bật")
    ap.add_argument("--min-free-vram-mb", type=int, default=7000,
                    help="Ngưỡng cho BankVN-350M trên RTX 5070 12GB; tăng lên cho profile lớn hơn")
    ap.add_argument("--forever", action="store_true")
    ap.add_argument("--sleep-seconds", type=int, default=300)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    with single_instance():
        while True:
            try:
                cycle(args)
            except Exception as exc:
                write_progress(
                    "error",
                    error=f"{type(exc).__name__}: {exc}",
                )
                print(f"[ERROR] cycle: {type(exc).__name__}: {exc}", flush=True)
                if not args.forever:
                    raise
            if not args.forever:
                break
            time.sleep(max(30, args.sleep_seconds))


if __name__ == "__main__":
    main()
