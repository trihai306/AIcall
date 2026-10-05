"""Qwen 9B writes customer phrasings; verified rules write the training answers.

The teacher never supplies a banking fact or an approval promise as a target.
Rejected or duplicate phrasings are recorded in an audit file, not trained.
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path

from make_threshold_curriculum import BASE_SYSTEM, source

SCENARIOS = [
    ("card17", "the_tin_dung.md", 17, "riêng tuổi mở thẻ tín dụng", False,
     "Dạ, 17 tuổi chưa đạt điều kiện tuổi mở thẻ ạ; tài liệu yêu cầu từ 18 tuổi."),
    ("card20", "the_tin_dung.md", 20, "riêng tuổi mở thẻ tín dụng", False,
     "Dạ, 20 tuổi đã đạt riêng điều kiện tuổi mở thẻ từ 18 tuổi ạ. Các điều kiện khác cần xét riêng."),
    ("card18", "the_tin_dung.md", 18, "riêng tuổi mở thẻ tín dụng", False,
     "Dạ, 18 tuổi đã đạt riêng điều kiện tuổi mở thẻ ạ. Các điều kiện khác cần xét riêng."),
    ("home21", "vay_mua_nha.md", 21, "riêng tuổi vay mua nhà", False,
     "Dạ, 21 tuổi chưa đạt điều kiện tuổi vay nhà ạ; tài liệu yêu cầu từ 22 tuổi."),
    ("home22", "vay_mua_nha.md", 22, "riêng tuổi vay mua nhà", False,
     "Dạ, 22 tuổi đã đạt riêng ngưỡng tuổi vay nhà ạ. Các điều kiện khác vẫn cần xét riêng."),
    ("home21-followup", "vay_mua_nha.md", 21, "hỏi lại về tuổi vay nhà sau khi bổ sung thu nhập 18 triệu", True,
     "Dạ, dù thu nhập 18 triệu, 21 tuổi vẫn chưa đạt điều kiện tuổi vay nhà từ 22 tuổi ạ."),
]


def ask(url: str, model: str, scenario: str, age: int, topic: str,
        followup: bool, round_id: str) -> list[str]:
    instruction = (
        "Viết 6 cách khách hàng Việt hỏi tư vấn viên về tình huống sau. "
        "Chỉ viết CÂU HỎI của khách về RIÊNG ĐIỀU KIỆN TUỔI, không trả lời, "
        "không hỏi quy trình, giấy tờ, ưu đãi, xác suất duyệt hay điều kiện khác. "
        "Không thêm dữ kiện mới. "
        "Mỗi câu dùng từ tự nhiên khác nhau, có dấu hỏi, giữ đúng chủ đề "
        f"{topic}. "
        + ("Đây là LƯỢT SAU: trước đó khách đã nói tuổi, nay bổ sung lương "
           "18 triệu/tháng và hỏi lại riêng điều kiện tuổi; không nhắc lại tuổi trong lượt sau. "
           if followup else f"Mỗi câu phải ghi rõ tuổi {age} bằng chữ số. ")
        + f"Mã đợt {round_id}; tránh lặp câu trong đợt trước. "
        "Trả JSON đúng dạng {\"questions\":[\"...\"]}."
    )
    payload = json.dumps({"model": model, "messages": [
        {"role": "system", "content": "Bạn chỉ biên tập lời khách bằng tiếng Việt; không tư vấn nghiệp vụ."},
        {"role": "user", "content": instruction},
    ], "stream": False, "think": False, "format": "json",
        "options": {"temperature": 0.35, "num_ctx": 2048, "num_predict": 480}},
        ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url.rstrip("/") + "/api/chat", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as response:
        outer = json.load(response)
    inner = json.loads((outer.get("message") or {}).get("content") or "{}")
    return [str(q).strip() for q in inner.get("questions", []) if isinstance(q, str)]


def accepted_question(question: str, age: int, followup: bool,
                      scenario_id: str = "") -> bool:
    if not 8 <= len(question.split()) <= 45 or "?" not in question:
        return False
    if re.search(r"quy trình|chuẩn bị|giấy tờ|hồ sơ|chính sách|ưu tiên|cơ hội|"
                 r"thẩm định|khả năng|phê duyệt|được duyệt|bao nhiêu tiền|"
                 r"ngân hàng chấp nhận|chấp nhận cho vay|ai trong độ tuổi", question, re.I):
        return False
    if scenario_id.startswith("card") and not re.search(r"mở thẻ|thẻ tín dụng", question, re.I):
        return False
    if scenario_id.startswith("home") and not followup and not re.search(
        r"vay (?:mua )?nhà|gói vay nhà", question, re.I
    ):
        return False
    if not re.search(r"riêng.{0,20}tuổi|đủ tuổi|điều kiện tuổi|"
                     r"tuổi.{0,25}(?:đủ|đạt|phù hợp)|ngưỡng tuổi|tuổi tối thiểu", question, re.I):
        return False
    numbers = [int(x) for x in re.findall(r"\b\d+\b", question)]
    if followup:
        return age not in numbers and 18 in numbers and set(numbers) == {18}
    return age in numbers and set(numbers) == {age}


def build_row(filename: str, age: int, followup: bool, question: str,
              answer: str, model: str, scenario_id: str) -> dict:
    content, source_id = source(filename)
    messages = [{"role": "system", "content": BASE_SYSTEM + "\n\nTHÔNG TIN THAM KHẢO:\n" + content}]
    if followup:
        messages.extend([
            {"role": "user", "content": f"Tôi {age} tuổi."},
            {"role": "assistant", "content": "Dạ, em nghe rồi ạ. Anh/chị muốn hỏi điều kiện nào của gói vay nhà?"},
        ])
    messages.extend([{"role": "user", "content": question},
                     {"role": "assistant", "content": answer}])
    return {"messages": messages, "source_id": source_id,
            "source_file": filename, "teacher": f"{model}-question-only",
            "answer_source": "deterministic-source-rule", "reviewed_by": "numeric-filter",
            "scenario_id": scenario_id}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--audit", type=Path, required=True)
    ap.add_argument("--round-id", required=True)
    ap.add_argument("--model", default="qwen3.5:9b")
    ap.add_argument("--url", default="http://127.0.0.1:11434")
    args = ap.parse_args()
    base = [json.loads(s) for s in args.base.read_text(encoding="utf-8").splitlines() if s.strip()]
    seen = {re.sub(r"\s+", " ", row["messages"][-2]["content"].lower().strip()) for row in base}
    rows, audit = [], []
    for scenario_id, filename, age, topic, followup, answer in SCENARIOS:
        try:
            questions = ask(args.url, args.model, scenario_id, age, topic, followup, args.round_id)
        except Exception as exc:
            audit.append({"scenario": scenario_id, "error": f"{type(exc).__name__}: {exc}"})
            continue
        for question in questions[:6]:
            key = re.sub(r"\s+", " ", question.lower().strip())
            good = accepted_question(question, age, followup, scenario_id) and key not in seen
            audit.append({"scenario": scenario_id, "question": question, "accepted": good})
            if good:
                rows.append(build_row(filename, age, followup, question, answer,
                                      args.model, scenario_id))
                seen.add(key)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in base + rows), encoding="utf-8")
    args.audit.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"9B proposed {len(audit)} questions; accepted {len(rows)}; "
          f"combined {len(base)+len(rows)} rows -> {args.output}")


if __name__ == "__main__":
    main()
