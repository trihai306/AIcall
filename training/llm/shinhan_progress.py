"""Durable, human-readable Shinhan data/training/evaluation progress."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DB_PATH = ROOT / "data/training/shinhan_large/pending.sqlite"
CARDS = ROOT / "data/training/shinhan_verified_fact_cards.json"
RUNS = ROOT / "data/training/shinhan_train_runs.jsonl"
LATEST = ROOT / "logs/shinhan_training_progress_latest.json"
LATEST_TEXT = ROOT / "logs/shinhan_training_progress_latest.txt"
HISTORY = ROOT / "logs/shinhan_training_progress.jsonl"
BULK_SHORTLIST = ROOT / "data/training/shinhan_bulk_shortlist.jsonl"
BULK_AUDIT = ROOT / "data/training/shinhan_bulk_audit.json"


def _table_exists(db: sqlite3.Connection, name: str) -> bool:
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                           (name,)).fetchone())


def _runs() -> list[dict]:
    if not RUNS.exists():
        return []
    result = []
    for line in RUNS.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    result.append(item)
            except json.JSONDecodeError:
                continue
    return result


def link_model(gguf_dir: Path | None, model_name: str) -> bool:
    """Associate a loaded candidate with its completed Shinhan fine-tune."""
    if gguf_dir is None or not RUNS.exists():
        return False
    target = str(gguf_dir.resolve()).casefold()
    runs = _runs()
    for run in reversed(runs):
        if str(run.get("gguf_dir") or "").casefold() == target:
            run["model"] = model_name
            run["status"] = "candidate_loaded"
            temp = RUNS.with_name(RUNS.name + f".{os.getpid()}.tmp")
            temp.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n"
                                    for item in runs), encoding="utf-8")
            os.replace(temp, RUNS)
            return True
    return False


def _eval_scores(run: dict) -> dict:
    scores = {}
    candidates = dict(run.get("eval_reports") or {})
    if run.get("model"):
        for path in sorted((ROOT / "data/training").glob("*eval*.json"),
                           key=lambda value: value.stat().st_mtime, reverse=True):
            name = path.name.casefold()
            label = ("shinhan_heldout" if "shinhan_style" in name else
                     "natural_dialogue" if "natural" in name else
                     "legacy_generic_banking" if "banking" in name else None)
            if label and label not in candidates:
                try:
                    data = json.loads(path.read_text(encoding="utf-8-sig"))
                    if data.get("model") == run["model"]:
                        candidates[label] = str(path.relative_to(ROOT))
                except (OSError, ValueError, TypeError):
                    continue
    for label, rel in candidates.items():
        path = ROOT / rel
        try:
            report = json.loads(path.read_text(encoding="utf-8-sig"))
            if report.get("model") != run.get("model"):
                continue
            scores[label] = {"passed": int(report["passed"]),
                             "total": int(report["total"]), "report": rel}
        except (OSError, ValueError, TypeError, KeyError):
            continue
    return scores


def collect(db: sqlite3.Connection, max_per_fact: int = 300,
            worker_state: str = "unknown", phase: str = "unknown") -> dict:
    counts = dict(db.execute("SELECT status,count(*) FROM questions GROUP BY status"))
    generated = sum(counts.values())
    cards = json.loads(CARDS.read_text(encoding="utf-8"))
    mined = (db.execute("SELECT count(*) FROM mining_chunks WHERE status='done'").fetchone()[0]
             if _table_exists(db, "mining_chunks") else 0)
    fact_candidates = (db.execute("SELECT count(*) FROM fact_candidates "
                                  "WHERE status='pending_source_review'").fetchone()[0]
                       if _table_exists(db, "fact_candidates") else 0)
    bulk = (dict(db.execute("SELECT status,count(*) FROM bulk_reviews GROUP BY status"))
            if _table_exists(db, "bulk_reviews") else {})
    shortlist_bytes = BULK_SHORTLIST.read_bytes() if BULK_SHORTLIST.exists() else b""
    shortlist_rows = sum(bool(line.strip()) for line in shortlist_bytes.splitlines())
    audit_state = "not_started"
    reviewed = 0
    audit_errors = None
    if BULK_AUDIT.exists():
        try:
            audit = json.loads(BULK_AUDIT.read_text(encoding="utf-8"))
            if audit.get("shortlist_sha256") != hashlib.sha256(shortlist_bytes).hexdigest():
                audit_state = "stale"
            else:
                items = audit.get("items") or []
                reviewed = sum(type(x.get("decision")) is bool for x in items
                               if isinstance(x, dict))
                audit_state = "complete" if reviewed == len(items) and len(items) >= 100 else "in_progress"
                audit_errors = sum(x.get("decision") is False for x in items
                                   if isinstance(x, dict))
        except (OSError, ValueError, TypeError):
            audit_state = "invalid"
    runs = _runs()
    latest_run = runs[-1] if runs else None
    evaluation = _eval_scores(latest_run) if latest_run else {}
    passed = sum(x["passed"] for x in evaluation.values())
    total = sum(x["total"] for x in evaluation.values())
    cap = len(cards) * max_per_fact
    return {
        "updated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "worker": {"state": worker_state, "phase": phase},
        "questions": {
            "generated_unique": generated,
            "remaining_to_configured_raw_cap_upper_bound": max(0, cap - generated),
            "awaiting_9b_judge": counts.get("pending_review", 0),
            "passed_9b_awaiting_source_review": counts.get("teacher_pass", 0),
            "judge_failed_awaiting_manual_review": counts.get("teacher_unscored", 0),
            "approved_for_future_training": counts.get("approved", 0),
            "teacher_rejected": counts.get("teacher_reject", 0),
            "source_review_rejected": counts.get("rejected", 0),
        },
        "sources": {"verified_fact_cards": len(cards),
                    "mined_chunks": mined,
                    "new_fact_candidates_awaiting_review": fact_candidates},
        "bulk_candidate": {"second_pass_accepted": bulk.get("accepted", 0),
                           "second_pass_rejected": bulk.get("rejected", 0),
                           "second_pass_uncertain": bulk.get("uncertain", 0),
                           "shortlist_rows_after_current_rules": shortlist_rows,
                           "audit_state": audit_state,
                           "audit_items_reviewed": reviewed,
                           "audit_errors": audit_errors,
                           "meaning": "Tập thử nghiệm lọc tự động hai lượt; chưa được duyệt tay và chưa phải mẫu đã train."},
        "training": {
            "completed_runs": len(runs),
            "training_examples_seen_across_runs": sum(int(r.get("train_rows", 0)) for r in runs),
            "latest_run": ({k: latest_run.get(k) for k in
                            ("run_id", "model", "dataset_rows", "train_rows", "holdout_rows",
                             "epochs", "status")}
                           if latest_run else None),
        },
        "learning_checks": {
            "latest_candidate": latest_run.get("model") if latest_run else None,
            "suites": evaluation,
            "passed_cases": passed,
            "total_cases": total,
            "quality_gate_passed": latest_run.get("quality_gate_passed") if latest_run else None,
            "meaning": "Số ca kiểm tra độc lập đạt; không phải số câu model đã nhớ hoặc đã học tốt trong mọi tình huống.",
        },
    }


def render_text(snapshot: dict) -> str:
    q, sources = snapshot["questions"], snapshot["sources"]
    training, learning = snapshot["training"], snapshot["learning_checks"]
    bulk = snapshot.get("bulk_candidate") or {}
    run = training["latest_run"] or {}
    lines = [
        f"Cập nhật UTC: {snapshot['updated_utc']}",
        f"Worker: {snapshot['worker']['state']} / {snapshot['worker']['phase']}",
        f"Câu hỏi đã tạo (không trùng chính tả): {q['generated_unique']}",
        "Còn tới trần cấu hình (ước lượng tối đa, có thể cạn ý sớm): "
        f"{q['remaining_to_configured_raw_cap_upper_bound']}",
        f"Chờ Qwen 9B chấm: {q['awaiting_9b_judge']}",
        f"Qwen 9B cho qua, chờ rà nguồn: {q['passed_9b_awaiting_source_review']}",
        f"9B chấm lỗi, chờ rà tay: {q['judge_failed_awaiting_manual_review']}",
        f"Đã duyệt cho các lượt train tiếp: {q['approved_for_future_training']}",
        f"Ý nghiệp vụ mới chờ rà PDF: {sources['new_fact_candidates_awaiting_review']}",
        f"Ứng viên lô lớn qua lọc lượt hai, chưa duyệt tay: {bulk.get('second_pass_accepted', 0)}",
        f"Shortlist sau lọc hiện hành: {bulk.get('shortlist_rows_after_current_rules', 0)}; "
        f"audit: {bulk.get('audit_state', 'not_started')} "
        f"({bulk.get('audit_items_reviewed', 0)} câu đã rà, "
        f"{bulk.get('audit_errors') if bulk.get('audit_errors') is not None else 'chưa rõ'} lỗi)",
        f"Lượt fine-tune hoàn tất: {training['completed_runs']}",
        f"Câu thật sự dùng cập nhật model qua các lượt: {training['training_examples_seen_across_runs']}",
        f"Candidate gần nhất: {run.get('model') or 'chưa có'}; train {run.get('train_rows', 0)} "
        f"câu, giữ riêng {run.get('holdout_rows', 0)} câu",
    ]
    for label, title in (("shinhan_heldout", "Kiểm tra Shinhan"),
                         ("natural_dialogue", "Kiểm tra nói tự nhiên"),
                         ("legacy_generic_banking", "Kiểm tra nghiệp vụ giả lập cũ")):
        score = learning["suites"].get(label)
        if score:
            lines.append(f"{title}: {score['passed']}/{score['total']} ca đạt")
    gate = learning["quality_gate_passed"]
    lines.append("Kết luận chất lượng: " +
                 ("đạt" if gate is True else "chưa đạt" if gate is False else "chưa kết luận"))
    lines.append("Số ca kiểm tra đạt không phải số câu đã học tốt trong mọi tình huống.")
    return "\n".join(lines) + "\n"


def save(snapshot: dict, *, force_history: bool = False) -> None:
    LATEST.parent.mkdir(parents=True, exist_ok=True)
    suffix = f".{os.getpid()}.{time.monotonic_ns()}.tmp"
    temp = LATEST.with_name(LATEST.name + suffix)
    temp.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, LATEST)
    temp_text = LATEST_TEXT.with_name(LATEST_TEXT.name + suffix)
    temp_text.write_text(render_text(snapshot), encoding="utf-8")
    os.replace(temp_text, LATEST_TEXT)
    if (force_history or not HISTORY.exists() or
            datetime.now(timezone.utc).timestamp() - HISTORY.stat().st_mtime >= 300):
        with HISTORY.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(snapshot, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-per-fact", type=int, default=300)
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()
    with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as db:
        snapshot = collect(db, args.max_per_fact, "snapshot", "read_only")
    if args.save:
        save(snapshot, force_history=True)
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
