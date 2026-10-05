"""Create a reproducible, balanced human-review sample of a bulk shortlist.

The output deliberately has no `errors` field. A reviewer must mark every
item before the train-cycle audit gate can accept it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "data/training/shinhan_bulk_shortlist.jsonl"
DEFAULT_OUTPUT = ROOT / "data/training/shinhan_bulk_audit.json"


def make_sample(source: Path, sample_size: int) -> dict:
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    rows = [json.loads(line) for line in raw.decode("utf-8-sig").splitlines()
            if line.strip()]
    if sample_size > len(rows):
        raise ValueError(f"Need {sample_size} rows, have {len(rows)}")
    groups: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    for index, row in enumerate(rows):
        groups[row.get("scenario_id", "unknown")].append((index, row))
    rng = random.Random(int(digest[:16], 16))
    for group in groups.values():
        rng.shuffle(group)
    chosen = []
    names = sorted(groups)
    while len(chosen) < sample_size:
        rng.shuffle(names)
        for name in names:
            if groups[name]:
                chosen.append(groups[name].pop())
                if len(chosen) == sample_size:
                    break
    chosen.sort(key=lambda item: item[0])
    return {
        "shortlist_sha256": digest,
        "sample_size": sample_size,
        "method": "balanced_by_scenario_seeded_by_shortlist_hash",
        "items": [{
            "index": index,
            "scenario_id": row.get("scenario_id"),
            "question": row["messages"][-2]["content"],
            "answer": row["messages"][-1]["content"],
            "decision": None,
            "reason": "",
        } for index, row in chosen],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--sample-size", type=int, default=120)
    args = parser.parse_args()
    if args.sample_size < 100:
        parser.error("sample-size must be at least 100")
    sample = make_sample(args.input, args.sample_size)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"sample_size": args.sample_size,
                      "shortlist_sha256": sample["shortlist_sha256"],
                      "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
