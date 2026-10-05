"""Windows-only candidate cycle for source-reviewed Shinhan conversations.

The teacher and trainer share one lock. Training never consumes raw teacher_pass
rows. A 1,000+ row experimental batch can include the separately reviewed bulk
shortlist only after an exact-hash sample audit; it never changes production.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

if __package__:
    from .shinhan_large_teacher import STATE_DIR, allowed, exclusive_worker, free_gib
    from .shinhan_review import export_training
    from .shinhan_progress import collect, save
else:
    from shinhan_large_teacher import STATE_DIR, allowed, exclusive_worker, free_gib
    from shinhan_review import export_training
    from shinhan_progress import collect, save

ROOT = Path(__file__).resolve().parents[2]
DB = STATE_DIR / "pending.sqlite"
RUNS = ROOT / "data/training/shinhan_train_runs.jsonl"
MANUAL_DATASET = ROOT / "data/training/shinhan_approved_current.jsonl"
BULK_DATASET = ROOT / "data/training/shinhan_bulk_shortlist.jsonl"
BULK_AUDIT = ROOT / "data/training/shinhan_bulk_audit.json"
DATASET = ROOT / "data/training/shinhan_bulk_train_current.jsonl"


def run(command: list[str]) -> None:
    print("[RUN]", subprocess.list2cmdline(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def prior_runs() -> list[dict]:
    if not RUNS.exists():
        return []
    return [json.loads(line) for line in RUNS.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()]


def assemble_dataset() -> tuple[int, int, str]:
    manual = [json.loads(line) for line in MANUAL_DATASET.read_text(encoding="utf-8").splitlines()
              if line.strip()]
    if not BULK_DATASET.exists() or not BULK_AUDIT.exists():
        return len(manual), 0, "awaiting_bulk_shortlist_and_audit"
    audit = json.loads(BULK_AUDIT.read_text(encoding="utf-8"))
    bulk_hash = hashlib.sha256(BULK_DATASET.read_bytes()).hexdigest()
    if audit.get("shortlist_sha256") != bulk_hash:
        return len(manual), 0, "bulk_audit_stale_for_current_shortlist"
    bulk = [json.loads(line) for line in BULK_DATASET.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    items = audit.get("items") or []
    decisions = [item.get("decision") for item in items if isinstance(item, dict)]
    error_count = sum(value is False for value in decisions)
    sample_matches = all(
        isinstance(item.get("index"), int) and 0 <= item["index"] < len(bulk) and
        item.get("scenario_id") == bulk[item["index"]].get("scenario_id") and
        item.get("question") == bulk[item["index"]]["messages"][-2]["content"] and
        item.get("answer") == bulk[item["index"]]["messages"][-1]["content"]
        for item in items if isinstance(item, dict))
    if (int(audit.get("sample_size", 0)) < 100 or
            len(items) != int(audit.get("sample_size", 0)) or
            len(decisions) != len(items) or
            len({item.get("index") for item in items if isinstance(item, dict)}) != len(items) or
            not sample_matches or
            any(type(value) is not bool for value in decisions) or
            int(audit.get("errors", -1)) != error_count or error_count > 3):
        return len(manual), 0, "bulk_audit_quality_failed"
    if len(bulk) < 900:
        return len(manual), len(bulk), "bulk_shortlist_below_900"
    rows = []
    seen = set()
    for row in manual + bulk:
        messages = row.get("messages") or []
        if len(messages) < 3 or messages[-1].get("role") != "assistant":
            raise ValueError("Invalid Shinhan training example")
        key = messages[-2].get("content", "").casefold().strip()
        if key and key not in seen:
            seen.add(key)
            rows.append(row)
    temp = DATASET.with_suffix(".jsonl.tmp")
    temp.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                    encoding="utf-8")
    os.replace(temp, DATASET)
    return len(manual), len(rows) - len(manual), "ready"


def ready(total_rows: int, digest: str, previous: list[dict]) -> str:
    current = next((r for r in reversed(previous) if r.get("dataset_sha256") == digest), None)
    if current:
        return "same_dataset_already_trained"
    last = next((r for r in reversed(previous) if r.get("dataset_rows") is not None), None)
    prior_count = int(last["dataset_rows"]) if last else 0
    if total_rows < 1000 or total_rows - prior_count < 500:
        return f"need_1000_total_and_500_new_rows: {total_rows}-{prior_count}"
    if free_gib() < 11:
        return "disk_below_11_gib"
    if not allowed("", dedicated=True):
        return "customer_backend_running"
    return "ready"


def warm_teacher() -> None:
    body = json.dumps({"model": "qwen3.5:9b", "prompt": "Chào", "stream": False,
                       "keep_alive": -1, "options": {"num_predict": 1, "num_ctx": 4096}}).encode()
    request = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=body,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=180) as response:
        response.read()


def update_run(digest: str, **fields) -> None:
    runs = prior_runs()
    for item in reversed(runs):
        if item.get("dataset_sha256") == digest:
            item.update(fields)
            break
    else:
        raise RuntimeError("Trained adapter missing from Shinhan run ledger")
    temp = RUNS.with_name(RUNS.name + f".{os.getpid()}.tmp")
    temp.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in runs),
                    encoding="utf-8")
    os.replace(temp, RUNS)


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        with exclusive_worker(STATE_DIR / "worker.lock"):
            with sqlite3.connect(DB) as db:
                approved = db.execute("SELECT count(*) FROM questions WHERE status='approved'").fetchone()[0]
                export_training(db, MANUAL_DATASET)
                manual_rows, bulk_rows, assembly = assemble_dataset()
                if assembly != "ready":
                    print(json.dumps({"train": assembly, "manual": manual_rows,
                                      "bulk": bulk_rows}, ensure_ascii=False), flush=True)
                    return
                digest = hashlib.sha256(DATASET.read_bytes()).hexdigest()
                total_rows = manual_rows + bulk_rows
                state = ready(total_rows, digest, prior_runs())
                if state != "ready":
                    print(json.dumps({"train": state, "manual": approved,
                                      "bulk": bulk_rows},
                                     ensure_ascii=False), flush=True)
                    return
                save(collect(db, worker_state="running", phase="training_candidate"))

            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            name = f"shinhan-qwen35-2b-{stamp}"
            adapter = ROOT / "models/llm" / name
            gguf = ROOT / "models/llm" / (name + "-gguf")
            try:
                run(["ollama", "stop", "qwen3.5:9b"])
                run([sys.executable, str(ROOT / "training/llm/train_lora.py"),
                     "--dataset", str(DATASET), "--base-model", "Qwen/Qwen3.5-2B",
                     "--load-in-16bit", "--epochs", "1", "--lr", "5e-5",
                     "--batch-size", "1", "--grad-accum", "8",
                     "--max-seq-len", "1024", "--candidate-name", name,
                     "--output-dir", str(adapter), "--gguf-dir", str(gguf)])
                update_run(digest, approved_rows=approved, bulk_rows=bulk_rows,
                           bulk_audit=str(BULK_AUDIT.relative_to(ROOT)),
                           status="adapter_saved")
                run([sys.executable, str(ROOT / "training/llm/deploy_ollama.py"),
                     "--name", name, "--modelfile", "auto-qwen35",
                     "--gguf-name", name + ".gguf", "--gguf-dir", str(gguf),
                     "--cleanup-export"])
                reports = {}
                for label, script in (
                    ("shinhan_heldout", "evaluate_shinhan_style.py"),
                    ("natural_dialogue", "evaluate_natural_dialogue.py"),
                    ("legacy_generic_banking", "evaluate_banking_style.py"),
                ):
                    output = ROOT / "data/training" / f"{name}-{label}-eval.json"
                    run([sys.executable, str(ROOT / "training/llm" / script),
                         "--model", name, "--output", str(output)])
                    reports[label] = str(output.relative_to(ROOT))
                shinhan = json.loads((ROOT / reports["shinhan_heldout"]).read_text(encoding="utf-8"))
                natural = json.loads((ROOT / reports["natural_dialogue"]).read_text(encoding="utf-8"))
                # The old banking suite uses fictitious MD; keep its score separate.
                auto_gate = (shinhan["passed"] == shinhan["total"] and
                             natural["passed"] == natural["total"])
                # Passing automated checks still needs a read-through of every
                # answer before anyone calls the candidate production-ready.
                update_run(digest,
                           status="candidate_pending_manual_review" if auto_gate
                           else "candidate_evaluated",
                           eval_reports=reports, automated_gate_passed=auto_gate,
                           quality_gate_passed=None if auto_gate else False)
                print(json.dumps({"candidate": name, "approved_rows": approved,
                                  "bulk_rows": bulk_rows,
                                  "shinhan": f"{shinhan['passed']}/{shinhan['total']}",
                                  "natural": f"{natural['passed']}/{natural['total']}",
                                  "automated_gate_passed": auto_gate,
                                  "quality_gate_passed": None if auto_gate else False,
                                  "production_unchanged": True}, ensure_ascii=False), flush=True)
            finally:
                subprocess.run(["ollama", "stop", name], cwd=ROOT,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                warm_teacher()
                with sqlite3.connect(DB) as db:
                    save(collect(db, worker_state="stopped", phase="candidate_cycle_done"),
                         force_history=True)
    except SystemExit as exc:
        print(str(exc), flush=True)


if __name__ == "__main__":
    main()
