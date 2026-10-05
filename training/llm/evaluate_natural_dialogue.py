"""Held-out conversational checks; inspect responses as well as rule scores."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

if __package__:
    from .evaluate_banking_style import ROOT, SYSTEM, chat
else:
    from evaluate_banking_style import ROOT, SYSTEM, chat
from backend.core.conversation_style import requested_region_note, requested_address_note

CASES = [
    ("tiet_kiem.md", [], "Gọi tôi là cô. Nếu gửi kỳ hạn ba tháng thì lãi ra sao?", [r"cô", r"3[,.]8"], [r"\banh\b", r"\bchú\b"]),
    ("the_tin_dung.md", [], "Bác hỏi thẻ Gold, sang năm thứ hai phải trả phí bao nhiêu?", [r"bác", r"400[.,]000"], [r"\banh\b", r"\bchị\b"]),
    ("the_tin_dung.md", [], "Em 20 tuổi, cứ gọi em là em. Riêng tuổi mở thẻ có đạt chưa?", [r"18", r"đạt|đủ"], [r"chưa đạt|không đạt|chưa đủ", r"\banh\b", r"\bchị\b"]),
    ("tiet_kiem.md", [], "Nói kiểu miền Bắc giúp cô nhé. Gửi trên ứng dụng có thêm lãi không?", [r"^vâng", r"0[,.]2"], [r"\banh\b", r"\bchị\b", r"0[,.]5%? tại quầy"]),
    ("tiet_kiem.md", [], "Nói kiểu miền Nam giúp chú nhé. Gửi tiết kiệm có cần chứng minh thu nhập không?", [r"^dạ", r"không", r"thu nhập"], [r"\banh\b", r"\bchị\b"]),
    ("tiet_kiem.md", [("user", "Nói theo cách miền Nam và gọi tôi là cô nhé."), ("assistant", "Dạ cô, em nghe rồi ạ.")], "Gửi ba tháng thì lãi suất tại quầy bao nhiêu?", [r"^dạ", r"cô", r"3[,.]8"], [r"\banh\b", r"\bchị\b"]),
    ("the_tin_dung.md", [("user", "Năm đầu thẻ Gold có mất phí không?"), ("assistant", "Năm đầu được miễn phí thường niên ạ.")], "Tôi đang hỏi phí năm thứ hai, bao nhiêu?", [r"400[.,]000"], [r"miễn phí năm thứ hai"]),
    ("vay_tin_chap.md", [], "Tôi không vay nữa, đừng hỏi thêm.", [r"cảm ơn|hiểu|dừng|kết thúc"], [r"\?", r"đã được duyệt|được duyệt|đã phê duyệt"]),
    ("vay_tin_chap.md", [], "Đừng quảng cáo. Lãi suất từ 7,9% là mức chắc chắn cho hồ sơ tôi à?", [r"chưa|không", r"7[,.]9"], [r"mức chắc chắn|chắc chắn cho hồ sơ|chắc chắn được|đảm bảo mức", r"đã duyệt", r"hồ sơ (?:của tôi |mình )?chưa được duyệt"]),
    ("tiet_kiem.md", [("user", "Tôi tính gửi 12 tháng."), ("assistant", "Kỳ hạn 12 tháng tại quầy có lãi suất 5,5% một năm ạ.")], "Nếu chuyển qua ứng dụng thì mức cuối cùng là bao nhiêu?", [r"5[,.]7"], []),
]

GLOBAL_FORBIDDEN = [r"(?:mới|sẽ|chắc chắn) được duyệt", r"em gửi được"]


def score_answer(answer: str, required: list[str], forbidden: list[str]) -> dict:
    missing = [pattern for pattern in required if not re.search(pattern, answer, re.I)]
    unwanted = [pattern for pattern in forbidden + GLOBAL_FORBIDDEN
                if re.search(pattern, answer, re.I)]
    unwanted.extend(word for word in (r"\bonline\b", r"\bcashback\b")
                    if re.search(word, answer, re.I))
    concise = len(answer.split()) <= 35 and "\n" not in answer
    return {"ok": not missing and not unwanted and concise,
            "missing": missing, "unwanted": unwanted, "concise": concise}


def evaluate(model: str, url: str) -> dict:
    results = []
    for filename, history, question, required, forbidden in CASES:
        source = (ROOT / "knowledge/products" / filename).read_text(encoding="utf-8-sig")
        turns = [{"role": role, "content": content} for role, content in history]
        turns.append({"role": "user", "content": question})
        prompt = SYSTEM + "\n\nTHÔNG TIN THAM KHẢO:\n" + source
        note = requested_region_note(turns)
        if note:
            prompt += "\n\n" + note
        address = requested_address_note(turns)
        if address:
            prompt += "\n\n" + address
        answer = chat(url, model, [{"role": "system", "content": prompt}] + turns)
        score = score_answer(answer, required, forbidden)
        results.append({"question": question, "answer": answer, **score})
        ok = score["ok"]
        print(f"{'PASS' if ok else 'FAIL'} | {question} | {answer}", flush=True)
    score = sum(row["ok"] for row in results)
    print(f"{model}: {score}/{len(results)} checks passed; review wording manually.", flush=True)
    return {"model": model, "passed": score, "total": len(results), "results": results}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model")
    parser.add_argument("--url", default="http://127.0.0.1:11434")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--rescore-report", type=Path,
                        help="Re-score saved answers after a rule fix; does not call Ollama")
    args = parser.parse_args()
    if args.rescore_report:
        report = json.loads(args.rescore_report.read_text(encoding="utf-8-sig"))
        if len(report.get("results", [])) != len(CASES):
            raise SystemExit("Saved report does not match current natural dialogue cases")
        for row, (_, _, question, required, forbidden) in zip(report["results"], CASES):
            if row.get("question") != question:
                raise SystemExit("Saved report question mismatch; refusing stale rescore")
            row.update(score_answer(row["answer"], required, forbidden))
        report["passed"] = sum(row["ok"] for row in report["results"])
        args.rescore_report.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
        print(f"{report['passed']}/{report['total']} rescored without GPU", flush=True)
        return
    if not args.model:
        parser.error("--model is required unless --rescore-report is provided")
    report = evaluate(args.model, args.url)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
