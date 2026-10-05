#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
import json
import sys
import unicodedata
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


BANKING_KEYWORDS = (
    "ngân hàng",
    "tài khoản",
    "chuyển khoản",
    "giao dịch",
    "thanh toán",
    "thẻ tín dụng",
    "thẻ ghi nợ",
    "atm",
    "otp",
    "kyc",
    "cic",
    "khoản vay",
    "vay vốn",
    "lãi suất",
    "tiền gửi",
    "tiết kiệm",
    "tín dụng",
    "dư nợ",
    "nợ xấu",
    "hạn mức",
    "thế chấp",
    "bảo lãnh",
    "ngoại hối",
    "tỷ giá",
)


def keyword_hits(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFC", text or "").lower()
    return [keyword for keyword in BANKING_KEYWORDS if keyword in normalized]


def is_banking_text(text: str, min_hits: int = 1) -> bool:
    return len(keyword_hits(text)) >= max(1, min_hits)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Lọc corpus tiếng Việt thành nguồn banking để Qwen teacher khai thác"
    )
    ap.add_argument("--input", default="data/bankvn/clean/corpus.jsonl")
    ap.add_argument("--output", default="data/bankvn/clean/banking_corpus.jsonl")
    ap.add_argument("--min-keyword-hits", type=int, default=1)
    args = ap.parse_args()

    src = Path(args.input)
    if not src.exists():
        raise SystemExit(f"[ERROR] Không thấy corpus: {src}")
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    total = kept = invalid = 0
    keyword_counts: Counter[str] = Counter()
    with src.open(encoding="utf-8", errors="ignore") as f, out.open(
            "w", encoding="utf-8") as dst:
        for line in f:
            if not line.strip():
                continue
            total += 1
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                invalid += 1
                continue
            text = str(obj.get("text") or "")
            hits = keyword_hits(text)
            if len(hits) < max(1, args.min_keyword_hits):
                continue
            keyword_counts.update(hits)
            dst.write(json.dumps(obj, ensure_ascii=False) + "\n")
            kept += 1

    print(json.dumps({
        "total": total,
        "kept": kept,
        "invalid_json": invalid,
        "kept_ratio": round(kept / total, 6) if total else 0.0,
        "top_keywords": keyword_counts.most_common(12),
        "output": str(out),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
