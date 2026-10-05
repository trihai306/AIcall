"""Generate varied, source-grounded banking examples for a second 2B run."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from distill_qwen35_2b import ROOT, REVIEWER, SYSTEM, ask, safe_numbers, sections

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GENERATOR = (
    "Chỉ dựa vào đoạn MD được đưa, viết ĐÚNG 4 cặp hỏi đáp NGÂN HÀNG đa dạng. "
    "Ưu tiên câu khách nói tự nhiên, hỏi thiếu một phần thông tin, đã có một "
    "giấy tờ/điều kiện, hỏi về con số, hoặc hỏi trường hợp ngoại lệ. "
    "Câu đáp phải dùng dữ kiện liên quan trong MD để giải quyết đúng câu hỏi, "
    "nhắc ví dụ cụ thể khi khách hỏi mức tiền mà MD có ví dụ; không bỏ qua "
    "điều kiện quan trọng, không liệt kê thứ không liên quan. Nếu MD không có "
    "thông tin để kết luận thì nói rõ giới hạn và hỏi một ý cần thiết. "
    "Không chế thêm chính sách, không hứa kiểm tra/hồ sơ được duyệt. "
    "Mỗi câu đáp tối đa 2 câu, giọng tư vấn viên tự nhiên. "
    'Chỉ xuất JSON {"cases":[{"user":"...","answer":"..."}]}.'
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--knowledge", type=Path, default=ROOT / "knowledge")
    ap.add_argument("--output", type=Path,
                    default=ROOT / "data/training/qwen35_2b_augmented.jsonl")
    ap.add_argument("--audit", type=Path,
                    default=ROOT / "data/training/qwen35_2b_augmented_audit.jsonl")
    ap.add_argument("--model", default="qwen3.5:9b")
    ap.add_argument("--url", default="http://127.0.0.1:11434")
    args = ap.parse_args()
    groups = [(label, source) for path in sorted(args.knowledge.rglob("*.md"))
              for label, source in sections(path)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if args.audit.exists():
        for line in args.audit.read_text(encoding="utf-8").splitlines():
            try:
                previous = json.loads(line)
                if len(previous.get("cases") or []) >= 4:
                    done.add(previous["section_id"])
            except (KeyError, json.JSONDecodeError):
                pass
    with args.output.open("a", encoding="utf-8") as out, args.audit.open("a", encoding="utf-8") as audit:
        for index, (label, source) in enumerate(groups, 1):
            section_id = hashlib.sha256((label + source).encode()).hexdigest()[:16]
            if section_id in done:
                continue
            try:
                result = ask(args.url, args.model, GENERATOR,
                             f"NGUỒN: {label}\n{source}", 2200)
                cases = result.get("cases") or []
                if not isinstance(cases, list):
                    cases = []
                audit_rows = []
                for case in cases[:4]:
                    if not isinstance(case, dict):
                        continue
                    user = str(case.get("user") or "").strip()
                    answer = str(case.get("answer") or "").strip()
                    if len(user) < 8 or len(answer) < 8 or len(answer.split()) > 65:
                        verdict = {"accept": False, "reason": "invalid length"}
                    elif not safe_numbers(user, answer, source):
                        verdict = {"accept": False, "reason": "unsupported number"}
                    else:
                        verdict = ask(args.url, args.model, REVIEWER,
                                      f"NGUỒN: {label}\n{source}\n\nKHÁCH: {user}\nTRẢ LỜI: {answer}",
                                      260)
                    audit_rows.append({"user": user, "answer": answer,
                                       "verdict": verdict})
                    if verdict.get("accept") is True:
                        row = {
                            "messages": [
                                {"role": "system", "content": SYSTEM + "\n\nTHÔNG TIN THAM KHẢO:\n" + source},
                                {"role": "user", "content": user},
                                {"role": "assistant", "content": answer},
                            ],
                            "source_id": section_id,
                            "source_file": label,
                            "teacher": args.model,
                            "reviewed_by": args.model,
                        }
                        out.write(json.dumps(row, ensure_ascii=False) + "\n")
                        out.flush()
                audit.write(json.dumps({"section_id": section_id, "source": label,
                                        "cases": audit_rows}, ensure_ascii=False) + "\n")
                audit.flush()
                print(f"[{index}/{len(groups)}] {label}: "
                      f"{sum(x['verdict'].get('accept') is True for x in audit_rows)}/{len(audit_rows)}",
                      flush=True)
            except Exception as exc:
                print(f"[WARN] {label}: {type(exc).__name__}: {exc}", flush=True)


if __name__ == "__main__":
    main()
