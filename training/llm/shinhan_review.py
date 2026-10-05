"""Review Qwen question candidates before including them in Shinhan SFT."""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "data/training/shinhan_large/pending.sqlite"
CARDS = ROOT / "data/training/shinhan_verified_fact_cards.json"


def apply_decisions(db: sqlite3.Connection, path: Path) -> None:
    decisions = json.loads(path.read_text(encoding="utf-8"))
    seen = set()
    for item in decisions:
        row_id = int(item["id"])
        decision = str(item["decision"])
        reason = str(item.get("reason", "")).strip()
        if decision not in {"approved", "rejected"} or row_id in seen:
            raise ValueError(f"Invalid/duplicate decision: {item}")
        if decision == "rejected" and not reason:
            raise ValueError(f"Missing rejection reason: {row_id}")
        row = db.execute("SELECT question,status FROM questions WHERE id=?", (row_id,)).fetchone()
        if not row or row[1] not in {"pending_review", "teacher_pass", "teacher_reject", "teacher_unscored", decision}:
            raise ValueError(f"Missing/already reviewed row: {row_id}")
        if item.get("question") != row[0]:
            raise ValueError(f"Question mismatch at row {row_id}; stale audit file")
        db.execute("UPDATE questions SET status=? WHERE id=?", (decision, row_id))
        if decision == "rejected":
            db.execute("INSERT INTO rejected (fact_id,question,reason) "
                       "SELECT fact_id,question,? FROM questions WHERE id=?", (reason, row_id))
        seen.add(row_id)
    db.commit()
    print(json.dumps({"decisions_applied": len(seen)}, ensure_ascii=False))


def export_pending(db: sqlite3.Connection, path: Path, limit: int,
                   status: str = "teacher_pass") -> None:
    rows = db.execute("SELECT id,fact_id,question,answer,source_url,persona "
                      "FROM questions WHERE status=? ORDER BY id LIMIT ?", (status, limit)).fetchall()
    cards = {x["id"]: x for x in json.loads(CARDS.read_text(encoding="utf-8"))}
    data = [{"id": x[0], "fact_id": x[1], "question": x[2], "answer": x[3],
             "source_url": x[4], "persona": x[5], "verified_fact": cards[x[1]]["fact"]}
            for x in rows]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"pending_exported": len(data), "path": str(path)}, ensure_ascii=False))


def export_training(db: sqlite3.Connection, path: Path) -> None:
    cards = {x["id"]: x for x in json.loads(CARDS.read_text(encoding="utf-8"))}
    rows = []
    for fact_id, question, answer, url, sha in db.execute(
        "SELECT fact_id,question,answer,source_url,source_sha256 "
        "FROM questions WHERE status='approved' ORDER BY id"
    ):
        card = cards[fact_id]
        rows.append({"messages": [
            {"role": "system", "content": (
                "Bạn là tư vấn viên Shinhan Bank Việt Nam. Trả lời tiếng Việt tự nhiên, "
                "chỉ theo nguồn tham khảo và không tự nhận đã xem tài khoản khách.\n\n"
                "THÔNG TIN THAM KHẢO:\n" + card["fact"])},
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer}],
            "source_id": sha[:16], "source_file": card["source"] + ".pdf",
            "source_url": url, "source_sha256": sha,
            "teacher": "qwen3.5:9b-question-only+source_review",
            "reviewed_by": "source_and_style_review",
            "scenario_id": "shinhan-" + fact_id})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows), encoding="utf-8")
    print(json.dumps({"approved_exported": len(rows), "path": str(path)}, ensure_ascii=False))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    action = ap.add_mutually_exclusive_group(required=True)
    action.add_argument("--pending", type=Path)
    action.add_argument("--unscored", type=Path)
    action.add_argument("--decisions", type=Path)
    action.add_argument("--training", type=Path)
    ap.add_argument("--limit", type=int, default=100)
    args = ap.parse_args()
    db = sqlite3.connect(args.db)
    if args.pending:
        export_pending(db, args.pending, args.limit)
    elif args.unscored:
        export_pending(db, args.unscored, args.limit, "teacher_unscored")
    elif args.decisions:
        apply_decisions(db, args.decisions)
    else:
        export_training(db, args.training)


if __name__ == "__main__":
    main()
