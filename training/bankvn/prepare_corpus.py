#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import (clean_text, is_strict_vietnamese, is_vietnamese, iter_input_files,
                    read_documents, stable_hash, vietnamese_score)


def main() -> None:
    ap = argparse.ArgumentParser(description="Làm sạch/dedupe corpus tiếng Việt cho BankVN")
    ap.add_argument("inputs", nargs="+", help="File hoặc thư mục .txt/.md/.jsonl/.json")
    ap.add_argument("--output", default="data/bankvn/clean/corpus.jsonl")
    ap.add_argument("--min-score", type=float, default=0.18)
    ap.add_argument("--min-chars", type=int, default=80)
    ap.add_argument("--strict-vietnamese", action="store_true",
                    help="Bắt câu chữ tự nhiên là tiếng Việt; vẫn cho OTP/KYC/CIC/API/JSON")
    ap.add_argument("--max-docs", type=int, default=0)
    args = ap.parse_args()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    total = kept = foreign = dup = 0
    score_sum = 0.0

    with out.open("w", encoding="utf-8") as dst:
        for path in iter_input_files(args.inputs):
            for doc in read_documents(path):
                total += 1
                text = clean_text(doc["text"])
                valid = (is_strict_vietnamese(text, args.min_score, args.min_chars)
                         if args.strict_vietnamese
                         else is_vietnamese(text, args.min_score, args.min_chars))
                if not valid:
                    foreign += 1
                    continue
                score_sum += vietnamese_score(text)
                h = stable_hash(text)
                if h in seen:
                    dup += 1
                    continue
                seen.add(h)
                row = {"text": text, "source": doc.get("source", ""),
                       "id": doc.get("id", h[:16]), "sha256": h}
                dst.write(json.dumps(row, ensure_ascii=False) + "\n")
                kept += 1
                if args.max_docs and kept >= args.max_docs:
                    break
            if args.max_docs and kept >= args.max_docs:
                break

    print(json.dumps({"total": total, "kept": kept, "foreign_or_low_vi": foreign,
                      "duplicates": dup,
                      "avg_vietnamese_score": round(score_sum / kept, 4) if kept else 0.0,
                      "strict_vietnamese": args.strict_vietnamese,
                      "output": str(out)}, ensure_ascii=False))
    if kept == 0:
        raise SystemExit("[ERROR] Không còn document nào sau bộ lọc")


if __name__ == "__main__":
    main()
