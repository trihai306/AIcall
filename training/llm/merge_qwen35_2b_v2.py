"""Merge two-pass-checked rows, remove unsafe/duplicate answers, refresh prompt."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from distill_qwen35_2b import ROOT, SYSTEM
from filter_qwen35_2b import BLOCKED

INPUTS = (
    ROOT / "data/training/qwen35_2b_train.jsonl",
    ROOT / "data/training/qwen35_2b_augmented_checked.jsonl",
    ROOT / "data/training/qwen35_2b_repair_checked.jsonl",
)
OUTPUT = ROOT / "data/training/qwen35_2b_v2_train.jsonl"


def main() -> None:
    challenge_path = ROOT / "data/training/qwen35_2b_challenge.jsonl"
    challenge = {json.loads(line)["messages"][-2]["content"].casefold().strip()
                 for line in challenge_path.read_text(encoding="utf-8").splitlines()
                 if line.strip()}
    seen = set()
    rejected: Counter[str] = Counter()
    rows = []
    for path in INPUTS:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            messages = row["messages"]
            user = messages[-2]["content"].strip()
            answer = messages[-1]["content"].strip()
            source = messages[0]["content"].split("THÔNG TIN THAM KHẢO:\n", 1)[-1]
            key = (row["source_id"], user.casefold())
            reason = next((reason for phrase, reason in BLOCKED.items()
                           if phrase in answer.casefold()), None)
            if not reason and user.casefold() in challenge:
                reason = "trùng câu benchmark"
            if not reason and key in seen:
                reason = "trùng mẫu"
            if reason:
                rejected[reason] += 1
                continue
            seen.add(key)
            messages[0]["content"] = SYSTEM + "\n\nTHÔNG TIN THAM KHẢO:\n" + source
            if path.name == "qwen35_2b_repair_checked.jsonl":
                row["reviewed_by"] = "qwen3.5:9b"
            rows.append(row)
    OUTPUT.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                      encoding="utf-8")
    print(json.dumps({"inputs": [str(p) for p in INPUTS], "kept": len(rows),
                      "rejected": dict(rejected), "output": str(OUTPUT)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
