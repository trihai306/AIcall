"""Read-only progress for the Windows Shinhan teacher task."""
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data/training/shinhan_large/pending.sqlite"
CARDS = ROOT / "data/training/shinhan_verified_fact_cards.json"


def main():
    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True) as db:
        status = dict(db.execute("SELECT status,count(*) FROM questions GROUP BY status"))
        generated = db.execute("SELECT count(*) FROM questions").fetchone()[0]
        prefiltered = db.execute("SELECT count(*) FROM rejected").fetchone()[0]
        fact_candidates = (db.execute("SELECT count(*) FROM fact_candidates").fetchone()[0]
                           if db.execute("SELECT 1 FROM sqlite_master WHERE name='fact_candidates'").fetchone()
                           else 0)
        mined_chunks = (db.execute("SELECT count(*) FROM mining_chunks WHERE status='done'").fetchone()[0]
                        if db.execute("SELECT 1 FROM sqlite_master WHERE name='mining_chunks'").fetchone()
                        else 0)
    cards = json.loads(CARDS.read_text(encoding="utf-8"))
    print(json.dumps({"fact_cards": len(cards), "generated": generated,
                      "status": status, "rejection_audit_rows": prefiltered,
                      "fact_candidates_waiting_for_source_review": fact_candidates,
                      "mined_source_chunks": mined_chunks,
                      "max_raw_at_current_cap": len(cards) * 300},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
