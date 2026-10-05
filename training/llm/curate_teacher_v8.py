"""Record the human source/topic review of the 9B question-only audit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ACCEPTED_QUESTIONS = {
    "Quy định về giới hạn tuổi tối thiểu để mở thẻ là bao nhiêu, có bắt buộc phải 18 tuổi không?",
    "Nếu tôi chỉ vừa tròn 22 tuổi thì quy định về giới hạn tuổi tối thiểu để vay mua nhà là thế nào?",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--teacher", type=Path, required=True)
    ap.add_argument("--audit", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--review", type=Path, required=True)
    args = ap.parse_args()
    base = [json.loads(s) for s in args.base.read_text(encoding="utf-8").splitlines() if s.strip()]
    proposed = [json.loads(s) for s in args.teacher.read_text(encoding="utf-8").splitlines() if s.strip()]
    new = proposed[len(base):]
    if proposed[:len(base)] != base:
        raise ValueError("Teacher input does not start with the expected base dataset")
    kept = []
    for item in new:
        question = item["messages"][-2]["content"]
        if question in ACCEPTED_QUESTIONS:
            item["reviewed_by"] = "manual-source-and-topic-review"
            kept.append(item)
    if {item["messages"][-2]["content"] for item in kept} != ACCEPTED_QUESTIONS:
        raise ValueError("Expected vetted questions missing from teacher output")
    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    for entry in audit:
        if entry.get("accepted"):
            entry["manual_accepted"] = entry["question"] in ACCEPTED_QUESTIONS
            if not entry["manual_accepted"]:
                entry["manual_reason"] = "ambiguous approval or off-topic age question"
    args.output.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in base + kept), encoding="utf-8")
    args.review.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(kept)}/{len(new)} automatically accepted questions passed manual review")


if __name__ == "__main__":
    main()
