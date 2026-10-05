"""Small held-out factual and multi-turn smoke test for an Ollama candidate."""
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.core.conversation_style import STYLE_GUIDE  # noqa: E402
from backend.core.banking_fact_precheck import banking_fact_precheck, direct_condition_answer  # noqa: E402

SYSTEM = (
    "Bạn là nhân viên tư vấn ngân hàng đang nói chuyện điện thoại. Xưng em, "
    "gọi khách là anh/chị. Chỉ dùng dữ kiện của khách và THÔNG TIN THAM KHẢO. "
    "Đối chiếu điều kiện; không hứa duyệt hồ sơ. Trả lời thẳng trong 1-2 câu, "
    "tối đa 35 từ.\n\n" + STYLE_GUIDE
)

CASES = [
    ("vay_mua_nha.md", ["Anh 21 tuổi, lương 18 triệu, có nhà thế chấp. Riêng tuổi đã đạt điều kiện vay nhà chưa?"], r"(?i)(chưa|không).*(22|tuổi)"),
    ("vay_tin_chap.md", ["Nợ xấu của chị đã tất toán 8 tháng. Vậy đã qua mốc để được xem xét chưa?"], r"(?i)(chưa|không).*(1 năm|một năm|12 tháng)"),
    ("vay_mua_nha.md", ["Em 23 tuổi, lương 10 triệu nhưng chưa có tài sản bảo đảm. Có thể kết luận đủ điều kiện vay nhà không?"], r"(?i)(chưa|không).*(tài sản|bảo đảm)"),
    ("the_tin_dung.md", ["Con tôi 17 tuổi, thu nhập 5 triệu. Riêng điều kiện tuổi mở thẻ có đạt không?"], r"(?i)(chưa|không).*(18|tuổi)"),
    ("vay_mua_nha.md", ["Anh mới 21 tuổi.", "Lương anh 18 triệu một tháng; vậy anh có đạt điều kiện tuổi vay nhà không?"], r"(?i)(chưa|không).*(22|tuổi)"),
    ("vay_mua_nha.md", ["Tôi 25 tuổi và có thu nhập ổn. Riêng độ tuổi vay mua nhà thì có đạt không?"], r"(?i)(?:đã|có|đủ|đạt|nằm trong).*(?:22|65|tuổi)"),
    ("vay_mua_nha.md", ["Bác 67 tuổi nhưng thu nhập tốt. Riêng tuổi vay nhà có đáp ứng không?"], r"(?i)(chưa|không|quá).*(65|tuổi)"),
]


def chat(url: str, model: str, messages: list[dict]) -> str:
    payload = json.dumps({"model": model, "messages": messages, "stream": False,
                          "think": False, "options": {"temperature": 0, "num_ctx": 4096,
                                                       "num_predict": 130}}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url.rstrip("/") + "/api/chat", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as response:
        return str((json.load(response).get("message") or {}).get("content") or "").strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--url", default="http://127.0.0.1:11434")
    ap.add_argument("--output", type=Path)
    ap.add_argument("--precheck", action="store_true")
    ap.add_argument("--direct", action="store_true")
    args = ap.parse_args()
    results = []
    for filename, questions, required in CASES:
        path = next(ROOT.joinpath("knowledge").rglob(filename))
        source = path.read_text(encoding="utf-8-sig")
        messages = [{"role": "system", "content": SYSTEM + "\n\nTHÔNG TIN THAM KHẢO:\n" + source}]
        for question in questions:
            messages.append({"role": "user", "content": question})
            direct = direct_condition_answer(messages[1:], messages[0]["content"]) if args.direct else ""
            if direct:
                messages.append({"role": "assistant", "content": direct})
                continue
            current = messages
            if args.precheck:
                note = banking_fact_precheck(messages[1:], messages[0]["content"])
                if note:
                    current = [{"role": "system", "content": messages[0]["content"] +
                               "\n\nĐỐI CHIẾU ĐIỀU KIỆN VỪA TÍNH TỪ NGUỒN VÀ LỜI KHÁCH:\n" + note}] + messages[1:]
            answer = chat(args.url, args.model, current)
            messages.append({"role": "assistant", "content": answer})
        answer = messages[-1]["content"]
        if len(questions) > 1:
            print("Previous turn:", messages[-3]["content"], flush=True)
        factual = bool(re.search(required, answer))
        if filename == "vay_mua_nha.md" and any(re.search(rf"\b{age}\s*tuổi\b", " ".join(questions)) for age in (21, 67)):
            factual = factual and not bool(re.search(r"\b(?:đã|vẫn)\s+(?:đạt|đủ)\b", answer, re.I))
        if filename == "the_tin_dung.md" and re.search(r"\b17\s*tuổi\b", " ".join(questions)):
            factual = factual and not bool(re.search(r"\b(?:đã|vẫn)\s+(?:đạt|đủ)\b", answer, re.I))
        concise = len(answer.split()) <= 35 and "\n" not in answer
        results.append({"source": filename, "questions": questions, "answer": answer,
                        "messages": messages,
                        "factual_pattern": factual, "concise": concise})
        print(f"{'PASS' if factual and concise else 'FAIL'} | {questions[-1]} | {answer}", flush=True)
    summary = {"model": args.model, "passed": sum(r["factual_pattern"] and r["concise"] for r in results),
               "total": len(results), "results": results}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{summary['passed']}/{summary['total']} passed", flush=True)


if __name__ == "__main__":
    main()
