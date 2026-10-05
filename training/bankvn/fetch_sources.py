#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from datasets import load_dataset


def main() -> None:
    ap = argparse.ArgumentParser(description="Tải/stream corpus Việt về định dạng JSONL BankVN")
    ap.add_argument("--dataset", default="hoanghai2110/vi-pretrain-clean")
    ap.add_argument("--split", default="train")
    ap.add_argument("--text-field", default="text")
    ap.add_argument("--output", default="data/bankvn/raw/vi_pretrain_clean.jsonl")
    ap.add_argument("--max-docs", type=int, default=0,
                    help="Số document mới tối đa trong lần chạy; 0 = lấy hết")
    ap.add_argument("--streaming", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--resume", action="store_true",
                    help="Append vào output và bỏ qua số dòng đã tải ở đầu dataset")
    args = ap.parse_args()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    existing = 0
    if args.resume and out.exists():
        with out.open(encoding="utf-8", errors="ignore") as old:
            existing = sum(1 for line in old if line.strip())

    ds = load_dataset(args.dataset, split=args.split, streaming=args.streaming)
    if existing:
        if hasattr(ds, "skip"):
            ds = ds.skip(existing)
        else:
            from itertools import islice
            ds = islice(ds, existing, None)

    added = 0
    source_index = existing
    mode = "a" if args.resume and out.exists() else "w"
    with out.open(mode, encoding="utf-8") as f:
        for row in ds:
            text = row.get(args.text_field)
            if not text:
                source_index += 1
                continue
            obj = {
                "text": str(text),
                "source": row.get("source") or args.dataset,
                "id": row.get("id") or f"{args.dataset}:{source_index}",
            }
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            added += 1
            source_index += 1
            if args.max_docs and added >= args.max_docs:
                break
    print(json.dumps({
        "dataset": args.dataset,
        "existing_documents": existing,
        "new_documents": added,
        "total_documents": existing + added,
        "resume": args.resume,
        "output": str(out),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
