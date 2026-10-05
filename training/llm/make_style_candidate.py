"""Rewrite reviewed banking answers into short, conversational speech with 9B.

The original answer and document remain the factual anchor. Rejected rewrites
keep their original answer; this is a style pass, not a source of new facts.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def numbers(value: str) -> set[str]:
    return set(re.findall(r"\d+(?:[.,]\d+)*", value))


def rewrite(url: str, model: str, row: dict) -> str:
    messages = row["messages"]
    question, answer = messages[-2]["content"], messages[-1]["content"]
    prompt = (
        "Viết lại đúng CÂU TRẢ LỜI dưới đây như nhân viên ngân hàng đang nói "
        "chuyện tự nhiên với khách qua điện thoại. Xưng em, gọi anh/chị nếu "
        "cần. Trả lời thẳng, gọn 1-2 câu; đừng lặp lời chào, đừng nói kiểu văn "
        "bản như 'quý khách', 'chúng tôi', 'theo quy định hiện hành'. "
        "GIỮ NGUYÊN kết luận, tất cả con số và điều kiện; không thêm thông tin, "
        "không hứa làm gì. Chỉ in câu viết lại, không giải thích.\n\n"
        f"KHÁCH: {question}\nCÂU TRẢ LỜI: {answer}"
    )
    payload = json.dumps({"model": model, "messages": [
        {"role": "system", "content": "Bạn là biên tập viên hội thoại tiếng Việt."},
        {"role": "user", "content": prompt},
    ], "stream": False, "think": False,
        "options": {"temperature": 0.2, "num_predict": 110}},
        ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url.rstrip("/") + "/api/chat", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as response:
        return str((json.load(response).get("message") or {}).get("content") or "").strip()


def acceptable(original: str, candidate: str) -> bool:
    if not candidate or len(candidate.split()) > 35 or "\n" in candidate:
        return False
    if numbers(original) != numbers(candidate):
        return False
    if re.search(r"(?i)quý khách|chúng tôi|theo quy định hiện hành|```|\*\*", candidate):
        return False
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--model", default="qwen3.5:9b")
    ap.add_argument("--url", default="http://127.0.0.1:11434")
    args = ap.parse_args()
    rows = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()]
    kept = rewritten = 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as output:
        for i, row in enumerate(rows, 1):
            original = row["messages"][-1]["content"]
            try:
                candidate = rewrite(args.url, args.model, row)
            except Exception as exc:
                print(f"[{i}/{len(rows)}] Lỗi biên tập: {exc}", flush=True)
                candidate = ""
            if acceptable(original, candidate):
                row["messages"][-1]["content"] = candidate
                rewritten += 1
            else:
                kept += 1
            row["style_rewrite"] = bool(acceptable(original, candidate))
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"[{i}/{len(rows)}] {'đổi' if row['style_rewrite'] else 'giữ gốc'}", flush=True)
    print(f"Đã biên tập {rewritten}, giữ gốc {kept} -> {args.output}")


if __name__ == "__main__":
    main()
