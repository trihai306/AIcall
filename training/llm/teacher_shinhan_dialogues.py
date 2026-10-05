"""Qwen 9B drafts Shinhan conversations; every row stays in audit until reviewed.

Never use this script's raw output directly as a training dataset.  The
approved facts below are from downloaded official PDFs and contain no rates.
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path

SOURCES = {
    "activate": ("card_user_guide_vi", "Sau khi nhận thẻ, có thể kích hoạt trong SOL/Internet Banking ở Thẻ > Kích hoạt thẻ; hoặc liên hệ 1900 1577.", "kích hoạt"),
    "pin": ("card_user_guide_vi", "Sau khi nhận và kích hoạt thẻ, có thể thiết lập PIN qua Internet Banking/Mobile Banking hoặc tại chi nhánh Shinhan.", "PIN"),
    "lost": ("card_user_guide_vi", "Khi mất thẻ, báo Shinhan để khóa ngay qua 1900 1577 hoặc trong SOL/Internet Banking ở Thẻ > Mở/Khóa Thẻ.", "khóa thẻ"),
    "minimum": ("card_user_guide_vi", "Thanh toán tối thiểu là số tiền tối thiểu cần trả trước hoặc vào ngày đến hạn để tránh phí do thanh toán trễ; xem số tiền cụ thể trên sao kê.", "tối thiểu"),
    "statement": ("card_user_guide_vi", "Sao kê ghi các giao dịch, phí, lãi (nếu có) trong chu kỳ và ngày đến hạn thanh toán.", "sao kê"),
    "digital": ("digital_card_guide", "Có thể đăng ký chức năng thẻ điện tử trong ứng dụng SOL qua mục Đăng ký thẻ điện tử, xác nhận thỏa thuận rồi làm theo các bước xác thực.", "thẻ điện tử"),
}
STYLES = {
    "bac": "thân thiện miền Bắc, xưng em với anh/chị, câu gọn, tự nhiên",
    "nam": "thân thiện miền Nam, xưng em với anh/chị, dùng từ tự nhiên miền Nam nhưng không suồng sã",
    "trung_tinh": "tiếng Việt trung tính, xưng em với anh/chị, chuyên nghiệp mà không máy móc",
}


def available(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return bool(json.load(response).get("can_use_gpu"))
    except Exception:
        return False


def draft(url: str, topic: str, fact: str, style: str) -> list[dict]:
    prompt = (
        "Tạo đúng 3 hội thoại ngắn giữa khách và tư vấn viên Shinhan Bank Việt Nam. "
        f"Chủ đề: {topic}. Sự thật duy nhất được phép dùng: {fact} "
        f"Văn phong tư vấn viên: {style}. Khách hỏi như người thật, mỗi câu một cách khác nhau. "
        "Tư vấn viên trả lời trực tiếp, 1-2 câu, đồng cảm khi khách mất thẻ. "
        "Chỉ nói về đúng chủ đề này: không đưa chuyện mất thẻ, hết hạn thẻ, "
        "mở tài khoản, được cấp thẻ mới hay thanh toán vào chủ đề khác. "
        "Không giả vờ đã xem tài khoản hoặc sao kê của khách. "
        "Khách xưng anh thì tư vấn viên gọi anh; khách xưng chị thì gọi chị; "
        "khách xưng em thì tư vấn viên gọi anh/chị hoặc bạn, không đảo vai. "
        "Không tự thêm lãi suất, phí, điều kiện, thời hạn, số điện thoại, lời hứa phê duyệt, "
        "không xin OTP/PIN/mật khẩu/số thẻ. Không chép nguyên văn sự thật. "
        'Chỉ xuất JSON {"dialogues":[{"customer":"...","assistant":"..."}]}.'
    )
    body = json.dumps({"model": "qwen3.5:9b", "messages": [
        {"role": "system", "content": "Bạn biên tập lời thoại tư vấn ngân hàng tiếng Việt, chỉ theo sự thật được cấp."},
        {"role": "user", "content": prompt},
    ], "stream": False, "think": False, "format": "json", "keep_alive": -1,
        "options": {"temperature": 0.5, "num_ctx": 2048, "num_predict": 550}},
        ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url.rstrip("/") + "/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as response:
        outer = json.load(response)
    inner = json.loads((outer.get("message") or {}).get("content") or "{}")
    return [x for x in inner.get("dialogues", []) if isinstance(x, dict)]


def likely_safe(topic: str, customer: str, assistant: str) -> bool:
    if not (12 <= len(customer) <= 240 and 25 <= len(assistant) <= 350):
        return False
    if not ("?" in customer or customer.endswith("ạ") or customer.endswith("em")):
        return False
    if topic != "lost" and re.search(r"mất thẻ|thẻ.*bị mất|hết hạn thẻ", customer, re.I):
        return False
    if re.search(r"em (?:đã )?(?:thấy|đánh dấu|kiểm tra) (?:trên|trong|sao kê)|"
                 r"hoàn toàn.*ngay lập tức|chắc chắn.*ngay", assistant, re.I):
        return False
    if re.search(r"chắc chắn (?:được )?duyệt|cam kết (?:duyệt|được vay)|bao đậu|"
                 r"cung cấp (?:OTP|PIN|mật khẩu)|đọc (?:OTP|PIN)|gửi (?:OTP|PIN)", assistant, re.I):
        return False
    if re.search(r"\b\d+(?:[.,]\d+)?\s*(?:%|triệu|tỷ|ngày|tháng)\b", assistant, re.I):
        return False
    if topic != "lost" and re.search(r"\b\d{4,}\b", assistant):
        return False
    if topic == "lost" and any(n != "1900 1577" for n in re.findall(r"\b\d{4}\s?\d{4}\b", assistant)):
        return False
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--availability-url", default="http://127.0.0.1:8100/api/training/availability")
    ap.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    args = ap.parse_args()
    audit: list[dict] = []
    for topic, (source, fact, required) in SOURCES.items():
        for region, style in STYLES.items():
            if not available(args.availability_url):
                audit.append({"status": "stopped_customer_busy", "topic": topic})
                break
            try:
                dialogues = draft(args.ollama_url, topic, fact, style)
            except Exception as exc:
                audit.append({"status": "error", "topic": topic, "region": region,
                              "error": f"{type(exc).__name__}: {exc}"})
                continue
            for d in dialogues[:3]:
                question, answer = str(d.get("customer", "")).strip(), str(d.get("assistant", "")).strip()
                passed = likely_safe(topic, question, answer) and (
                    required.lower() in (question + " " + answer).lower())
                audit.append({"status": "needs_human_review" if passed else "rejected",
                              "topic": topic, "region": region, "source": source,
                              "source_url": next((x["url"] for x in json.loads(
                                  (Path(__file__).resolve().parents[2] / "data/external/shinhan/manifest.json").read_text())
                                  if x["name"] == source), ""),
                              "approved_fact": fact, "customer": question, "assistant": answer})
        if audit and audit[-1].get("status") == "stopped_customer_busy":
            break
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"drafted": len(audit),
                      "needs_review": sum(x["status"] == "needs_human_review" for x in audit),
                      "rejected": sum(x["status"] == "rejected" for x in audit)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
