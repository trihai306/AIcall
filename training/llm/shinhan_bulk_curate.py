"""Second-pass Qwen review for a large experimental Shinhan SFT shortlist.

This writes a separate `bulk_reviews` table. It never marks a question as
manually approved and never deploys a model. Canonical answers remain those
from source-checked fact cards; Qwen only judges whether they fit each question.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

if __package__:
    from .shinhan_large_teacher import (CARDS, MANIFEST, STATE_DIR, CustomerBusy,
                                        allowed, exclusive_worker, free_gib,
                                        valid_question)
else:
    from shinhan_large_teacher import (CARDS, MANIFEST, STATE_DIR, CustomerBusy,
                                       allowed, exclusive_worker, free_gib,
                                       valid_question)

ROOT = Path(__file__).resolve().parents[2]
DB = STATE_DIR / "pending.sqlite"
OUTPUT = ROOT / "data/training/shinhan_bulk_shortlist.jsonl"
CARD_EXCLUSIONS = {
    "activate_card": r"cần gọi.*hotline|hotline.*cần gọi|cách dùng thẻ mới|"
                     r"mở thẻ mới nhận|anh bảo mình",
    "activate_digital_card": r"sau khi gửi mã xác thực|đúng định dạng|kích hoạt.*thành công|"
                             r"hoàn tất xác thực",
    "loan_documents_truthful": r".*",  # Current question pool mostly asks for an absent document list.
    "loan_repayment_obligation": r"làm sao|làm thế nào|cách nào|như thế nào|"
                                 r"bằng cách nào|hướng dẫn.*thanh toán|đảm bảo|"
                                 r"trả.*ra sao|cách trả|ngay lập tức",
    "card_online_security": r".*",  # Source states purpose, not enrollment or procedure.
    "early_repayment": r"phí.*cố định|cố định.*phí|mức phí|phí.*tính|quy trình|điều kiện|chấp thuận|"
                       r"duyệt|đồng ý ra sao|chi phí.*quy định thế nào|có phí.*thật chứ|"
                       r"(?:điều kiện|chấp thuận).*như thế nào|"
                       r"(?:điều kiện|chuẩn bị|đáp ứng).*gì|trả nợ trước hạn khi nào",
    "cash_advance_interest": r"(?:phải|cần) trả ngay|trả lãi ngay|phí|"
                             r"số tiền.*lãi|lãi suất bao nhiêu|"
                             r"(?:lãi|tính lãi).*?(?:thế nào|như thế nào)",
    "cash_withdrawal_vs_advance": r"cách rút|làm sao để rút|có được rút|"
                                  r"mất phí|lãi suất|có được phân biệt|hoạt động thế nào|"
                                  r"ứng tiền.*rút từ hạn mức|rút từ hạn mức.*ra sao",
    "internal_transfer_pay_other_card": r"hướng dẫn ghi chức năng|"
                                        r"làm thế nào|làm cách nào|cách thực hiện|"
                                        r"hướng dẫn|chỉ giúp|giúp.*thanh toán|cách thanh toán|"
                                        r"chức năng này|dịch vụ này|làm sao|"
                                        r"(?:anh|chị|bác).*thanh toán.*cho tôi",
    "manage_card_limits": r"tăng hạn mức|được duyệt hạn mức|hạn mức bao nhiêu|"
                          r"giúp.*(?:xem|đặt)|xem hạn mức|(?:điều chỉnh|đặt).*thế nào|"
                          r"điều chỉnh.*ra sao|làm sao|làm cách nào|thế nào là đặt|"
                          r"chỉ cách|cách nào|cách thiết lập|cách đặt|cách điều chỉnh|hướng dẫn|"
                          r"thiết lập.*(?:như thế nào|ra sao)|thế nào là thiết lập|"
                          r"làm thế nào|cách thay đổi|giúp.*điều chỉnh|"
                          r"giúp.*hạn mức|hạn mức thẻ(?!\s+(?:giao dịch|thanh toán))",
    "corporate_credit_sign_card": r"quy trình ký|làm gì để ký|cách ký|ký.*như thế nào",
    "partial_early_repayment_allocation": r"được phép|có được|chấp nhận|bác hãy|cho tôi biết|"
                                          r"gốc còn lại|kỳ sau sẽ giảm|lịch.*giảm|"
                                          r"nghĩa của trả nợ|thầy|đã.*(?:trừ|bù)|(?:trừ|bù).*chưa",
    "register_digital_card": r"cần giúp gì|thỏa thuận ra sao|xác nhận thỏa thuận.*(?:ra sao|như thế nào)|"
                             r"tại đây|ứng dụng này|quy trình.*ở đây|"
                             r"cần làm gì để xác thực|hoàn tất xác thực",
    "statement_contents": r"lãi suất|nạp tiền|liệt kê đủ|cho.*xem|giao dịch nào|"
                          r"phí nào|phí dịch vụ nào|đã hiển thị|đã bao gồm|đầy đủ|phí phạt|"
                          r"giao dịch.*số tiền.*trả|ngày đến hạn.*(?:chỗ nào|ở đâu)|"
                          r"cung cấp sao kê",
    "statement_discrepancy": r"kiểm tra xem có|xem.*sai lệch|không đúng ý chị|"
                             r"giúp kiểm tra.*khoản này",
    "toggle_foreign_card": r"(?:bật|tắt).*cho (?:tôi|mình|em)|giúp.*(?:bật|tắt)|"
                           r"đã (?:bật|tắt)|thẻ này|\bapp\b|làm sao|làm thế nào|"
                           r"trực tuyến|hướng dẫn|tránh phí|an tâm hơn|an toàn hơn|"
                           r"trạng thái.*(?:bật|tắt)|"
                           r"(?:anh|chị|bác).*có thể.*(?:bật|tắt)|"
                           r"(?:anh|chị|bác).*tắt.*cho.*thẻ",
    "toggle_online_card": r"(?:bật|tắt).*cho (?:tôi|mình|em|thẻ này)|"
                          r"giúp.*(?:bật|tắt)|đã (?:bật|tắt)|thẻ này|làm sao|làm thế nào|"
                          r"tôi có bật|mình có bật|tôi bật.*chưa|nên tắt|tránh mất tiền|"
                          r"\bứng dụng\b|"
                          r"(?:anh|chị|bác).*có thể bật|"
                          r"(?:anh|chị|bác).*có khóa|"
                          r"(?:anh|chị|bác).*giúp.*mở|giúp.*(?:mở|khóa)|"
                          r"hướng dẫn|được chưa",
    "pay_card_branch": r"chi nhánh này|quầy này|dùng hướng dẫn thẻ|hướng dẫn|"
                       r"làm thế nào|làm sao|nộp tiền.*thế nào|cách.*(?:trả|nộp)|"
                       r"giờ này|được chưa|lúc nào.*được không",
    "pay_card_auto": r"kích hoạt khi nào|làm sao.*tự động trả|cách.*đăng ký|"
                     r"hoạt động.*cho tôi",
    "pay_card_sol": r"làm thế nào|làm cách nào|cách thanh toán|hướng dẫn|"
                    r"nhanh thế nào|giải đáp làm sao|như thế nào|làm sao|"
                    r"hoạt động ra sao|chỉ giúp|cần làm gì|phải làm gì|"
                    r"bằng cách nào|phải trả.*ra sao|nên dùng|menu nào|"
                    r"có cách nào.*cho mình",
    "suspicious_email": r"thư lạ gửi.*có đề nghị|OTP|phân biệt.*lừa đảo",
    "set_pin": r"hướng dẫn|làm sao|làm thế nào|làm cách nào|cách đặt|"
               r"thiết lập PIN.*(?:thế nào|như thế nào)|"
               r"giúp.*(?:đặt|thiết lập)|kích hoạt mã PIN|đổi.*mã PIN|"
               r"cách nào khác",
    "statement_online_lookup": r"\bapp\b|\bứng dụng\b|làm sao|làm cách nào|"
                               r"như thế nào|hướng dẫn|chỉ giúp|cách xem|lịch sử.*ra",
    "corporate_debit_pay_from_account": r"chi dịch vụ|trực tuyến|online|dùng dịch vụ chưa|"
                                           r"thanh toán hàng hóa thế nào|dịch vụ thế nào|dịch vụ gì",
    "minimum_payment": r"đủ để tránh phí|đủ.*tránh.*phí|"
                       r"(?:tránh|không).*phạt|khoản vay",
    "pay_card_own_function": r"làm sao|làm thế nào|cách.*dùng|cách.*sử dụng",
    "card_online_otp": r"giao dịch này|thẻ của tôi.*yêu cầu|Mastercard SecureCode\.\*OTP|"
                       r"vì sao|tại sao|sao.*phải nhập|mã xác thực.*là gì|"
                       r"nhập.*ra sao|"
                       r"trên thẻ của tôi",
    "corporate_credit_limit_not_guarantee": r"^(?!.*(?:doanh nghiệp|công ty|corporate)).*",
}


def ensure_table(db: sqlite3.Connection) -> None:
    db.execute("CREATE TABLE IF NOT EXISTS bulk_reviews ("
               "question_id INTEGER PRIMARY KEY, status TEXT NOT NULL, "
               "reason TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, "
               "reviewed_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    db.commit()


def style_answer(answer: str, question: str) -> tuple[str, str]:
    """Vary only the opening particle; never alter a verified factual claim."""
    answer = answer.replace("nhé ạ.", "nhé.")
    if not answer.startswith("Dạ, "):
        return answer, "neutral"
    if re.search(r"\bhông\b|\bhen\b", question, re.I):
        return answer, "friendly_south"
    choice = int(hashlib.sha256(question.encode("utf-8")).hexdigest()[:2], 16) % 3
    if choice == 0:
        return answer, "friendly_south"
    if choice == 1:
        return "Vâng, " + answer[4:], "friendly_north"
    plain = answer[4:]
    return plain[:1].upper() + plain[1:], "neutral"


def precheck(question: str, card: dict) -> str:
    if not valid_question(question, card):
        return "topic_or_format"
    # Generated role reversals and vague half-questions survived both 9B passes.
    if re.search(r"^(?:anh|chị|bác|bà|thầy)\b(?!\s+ơi\b)|"
                 r"^bao gồm\b|^em làm sao\b|\bbị lấy thẻ\b|"
                 r"\bsao kê sai giao dịch lạ\b|\bgiữa rút và ứng\b|"
                 r"\bkhác nhau giữa\b|\bđược chưa\b|\bnhé\s*\?$|"
                 r"\bthế nào nếu\b|\bem đang lo lắng làm sao\b|"
                 r"\btiết lộ chi khoản\b|\bkêu gì hotline\b|"
                 r"\bnhư vậy nào\b|\bNói giúp tôi\b|"
                 r"\bđúng luật chưa\b|\bcó hiểu đúng chưa\b|"
                 r"\bemail lạ.*email yêu cầu giả mạo\b|"
                 r"\bnằm ở đâu sao kê\b|\s+\?|"
                 r"\bkhông rõ đó có phải email yêu cầu\b|"
                 r"^cái tôi muốn biết\b|^bạn nói rõ\b|"
                 r"\bthẻ tín dụng của anh\b|\bquy trình này\b|"
                 r"^bên trang nào\b|\bđây ạ\?|"
                 r"\bmình muốn đăng ký thẻ điện tử sao\b",
                 question, re.I):
        return "unnatural_wording"
    if (card["id"] == "internal_transfer_pay_other_card" and
            not re.search(r"chuyển khoản|chuyển tiền", question, re.I)):
        return "payment_method_not_internal_transfer"
    if (card["id"] == "corporate_debit_pay_from_account" and
            not re.search(r"ghi nợ doanh nghiệp", question, re.I)):
        return "corporate_card_type_ambiguous"
    if (card["id"] == "corporate_credit_sign_card" and
            not re.search(r"tín dụng doanh nghiệp", question, re.I)):
        return "corporate_card_type_ambiguous"
    if card["id"] == "internal_transfer_pay_other_card" and re.search(
            r"\bthẻ khác\b(?!.*tín dụng)|\bchức năng gì\b", question, re.I):
        return "other_card_type_or_method_ambiguous"
    if card["id"] == "pay_card_auto" and re.search(
            r"đang tham gia|áp dụng.*(?:tài khoản|cho tôi)", question, re.I):
        return "asks_personal_enrollment"
    if card["id"] == "partial_early_repayment_allocation" and re.search(
            r"áp dụng.*hợp đồng của tôi", question, re.I):
        return "asks_personal_contract"
    if card["id"] == "corporate_credit_sign_card" and re.search(
            r"mới được kích hoạt|để kích hoạt", question, re.I):
        return "unsupported_activation_condition"
    if card["id"] == "toggle_foreign_card" and re.search(
            r"\bcần bật\b|\bphải bật\b", question, re.I):
        return "asks_recommendation_not_in_source"
    if (card["id"] == "card_online_otp" and
            not re.search(r"Verified by Visa|Mastercard SecureCode|Mastercard Secured Code",
                          question, re.I)):
        return "otp_source_condition_missing"
    if re.search(r"\*|hỏi xem|\b(?:anh|chị|bác|cô|chú)\s+giải\s+thích\s+xem|"
                 r"\b(?:anh|chị|bác|cô|chú)\s+cho\s+biết\b|"
                 r"\bđúng\s+không\s+ạ\s*\?|\bthế\s+nào\s+nhé\s*\?|"
                 r"hỏi thử xem|tôi hỏi xem|hướng dẫn ghi chức năng|anh bạn ơi|"
                 r"chị hỏi mình|chị hỏi về|chị thắc mắc|chị nói mình|chị cần biết.*của em|"
                 r"anh lo lắng|anh bảo tôi|anh nói sao|bác hãy|bác giúp anh|"
                 r"bác nói gì về|bác bảo mã xác thực|"
                 r"chị cần ai hỗ trợ|chị cần tư vấn xem|bác nào biết|"
                 r"bác nói|anh gặp email|hỏi anh xem|"
                 r"bác cần hướng dẫn em|mọi người ơi|"
                 r"^em có thể giải thích|em chào.*bác.*cháu|"
                 r"(?:đặt|điều chỉnh).*sao\s*\?|"
                 r"^(?:chị|anh|bác|cô|chú)\s+(?:có thể hỏi|giải thích)|"
                 r"^(?:bà|bác|anh|chị|chú|cô)\s+(?:kích hoạt|rút|trả|nhận|thấy|định|muốn)",
                 question, re.I):
        return "unnatural_wording"
    if re.search(r"tại sao|vì sao|nguyên nhân|sao lại|bao lâu|ngay bây giờ|"
                 r"nhanh nhất|chắc chắn|cam kết|phê duyệt|lãi suất cụ thể|"
                 r"lãi suất hiện tại|mức phí cụ thể|mất bao nhiêu phí|"
                 r"thủ tục chi tiết|điều kiện cụ thể|giấy tờ gì|cần chuẩn bị gì", question, re.I):
        return "asks_unsupported_detail"
    if re.search(r"\bbao nhiêu\b|\bmấy tiền\b", question, re.I) and card["id"] not in {
            "minimum_payment", "activate_card", "lost_card", "statement_discrepancy"}:
        return "asks_number"
    if len(question.split()) < 8 or len(question.split()) > 29:
        return "too_short_or_long"
    if re.search(CARD_EXCLUSIONS.get(card["id"], r"(?!)"), question, re.I):
        return "answer_does_not_cover_detail"
    return ""


def next_batch(db: sqlite3.Connection, cards: dict, cap: int) -> tuple[dict, list[tuple[int, str]]] | None:
    counts = dict(db.execute("SELECT q.fact_id,count(*) FROM bulk_reviews b "
                             "JOIN questions q ON q.id=b.question_id "
                             "WHERE b.status='accepted' GROUP BY q.fact_id"))
    for fact_id in sorted(cards, key=lambda key: (counts.get(key, 0), key)):
        if CARD_EXCLUSIONS.get(fact_id) == r".*":
            continue
        if counts.get(fact_id, 0) >= cap:
            continue
        rows = db.execute("SELECT q.id,q.question FROM questions q "
                          "LEFT JOIN bulk_reviews b ON b.question_id=q.id "
                          "WHERE q.fact_id=? AND q.status='teacher_pass' "
                          "AND (b.question_id IS NULL OR "
                          "(b.status='retry' AND b.attempts<3)) AND q.answer=? "
                          "ORDER BY q.id LIMIT 64", (fact_id, cards[fact_id]["answer"])).fetchall()
        if rows:
            return cards[fact_id], rows
    return None


def ask_critic(card: dict, rows: list[tuple[int, str]], ollama_url: str) -> dict[int, tuple[bool, str]]:
    prompt = (
        "Bạn là người kiểm tra chất lượng dữ liệu tư vấn Shinhan Bank. "
        "Chỉ chấm từng CÂU HỎI; tuyệt đối không thêm dữ kiện mới.\n"
        "DỮ KIỆN ĐÃ ĐỐI CHIẾU PDF: " + card["fact"] + "\n"
        "CÂU TRẢ LỜI CỐ ĐỊNH: " + card["answer"] + "\n"
        "Chỉ accept=true nếu câu hỏi là lời khách thật, tự nhiên, đúng một ý, "
        "và câu trả lời cố định nói trực tiếp ĐẦY ĐỦ điều khách hỏi. "
        "Loại khi khách hỏi mức phí/lãi/ngày/điều kiện cá nhân, lý do lỗi, "
        "các bước chi tiết hoặc tình trạng tài khoản mà đáp án không có. "
        "Loại câu đảo vai, lặp từ, vô nghĩa, cụt, mang giọng máy, "
        "hoặc hỏi chủ đề thẻ cá nhân bằng nguồn thẻ doanh nghiệp. "
        "VÍ DỤ PHẢI LOẠI: hỏi 'cần giấy tờ vay gì' khi đáp án chỉ nói 'cung cấp giấy tờ đầy đủ'; "
        "hỏi 'cách đăng ký Verified by Visa' khi đáp án chỉ nói dịch vụ tăng bảo mật; "
        "hỏi 'phí trả trước hạn cố định không' khi đáp án chỉ nói đối chiếu phí hợp đồng; "
        "hỏi 'cách được chấp thuận vay' khi đáp án chỉ nói ngân hàng kiểm tra; "
        "hỏi 'ứng tiền mặt có phải trả ngay' khi đáp án chỉ nói thời điểm tính lãi; "
        "hỏi 'thẻ tôi bị lỗi vì sao' khi đáp án chỉ nói chức năng có thể dùng; "
        "hỏi 'đã bật giao dịch nước ngoài cho thẻ tôi chưa' khi đáp án chỉ nêu nơi bật; "
        "hỏi 'trong sao kê có lãi suất vay không' khi đáp án chỉ nêu tiền lãi; "
        "hỏi 'cần gọi hotline để kích hoạt không' khi hotline chỉ là lựa chọn; "
        "hỏi 'làm thế nào chuyển khoản' khi đáp án chỉ nói có thể dùng chức năng đó. "
        "Không tự suy ra quy trình hoặc điều kiện từ đáp án. Nếu không chắc, loại. "
        'Trả JSON {"reviews":[{"id":1,"accept":false,"reason":"..."}]}, '
        "mỗi ID đúng một lần; reason tối đa 8 từ, accept=true thì reason rỗng.\n"
        + json.dumps([{"id": row_id, "question": question} for row_id, question in rows],
                     ensure_ascii=False)
    )
    body = {"model": "qwen3.5:9b", "messages": [
        {"role": "system", "content": "Chấm nghiêm ngặt độ khớp câu hỏi và đáp án; không suy đoán."},
        {"role": "user", "content": prompt}], "stream": True, "think": False,
        "format": "json", "keep_alive": -1,
        "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 1000}}
    req = urllib.request.Request(ollama_url.rstrip("/") + "/api/chat",
                                 data=json.dumps(body, ensure_ascii=False).encode(),
                                 headers={"Content-Type": "application/json"})
    fragments = []
    next_check = time.monotonic()
    with urllib.request.urlopen(req, timeout=120) as response:
        for line in response:
            if time.monotonic() >= next_check:
                if not allowed("", dedicated=True):
                    raise CustomerBusy("customer backend started")
                next_check = time.monotonic() + 0.3
            if line.strip():
                fragments.append((json.loads(line).get("message") or {}).get("content") or "")
    raw = json.loads("".join(fragments) or "{}").get("reviews")
    expected = {i for i, _ in rows}
    if (not isinstance(raw, list) or len(raw) != len(rows) or
            {x.get("id") for x in raw if isinstance(x, dict)} != expected or
            any(type(x.get("accept")) is not bool for x in raw)):
        raise ValueError("Incomplete bulk critic response")
    return {x["id"]: (x["accept"], str(x.get("reason", ""))[:160]) for x in raw}


def save_shortlist(db: sqlite3.Connection, cards: dict, manifest: dict) -> int:
    rows = []
    for fact_id, question, answer, source_sha, url in db.execute(
            "SELECT q.fact_id,q.question,q.answer,q.source_sha256,q.source_url "
            "FROM questions q JOIN bulk_reviews b ON b.question_id=q.id "
            "WHERE b.status='accepted' ORDER BY q.id"):
        card = cards.get(fact_id)
        source = manifest.get(card["source"]) if card else None
        if not source or source["sha256"] != source_sha or source["url"] != url:
            continue
        if answer != card["answer"] or precheck(question, card):
            continue
        styled_answer, answer_style = style_answer(answer, question)
        rows.append({"messages": [
            {"role": "system", "content": (
                "Bạn là tư vấn viên Shinhan Bank Việt Nam. Trả lời tiếng Việt tự nhiên, "
                "chỉ theo nguồn tham khảo và không tự nhận đã xem tài khoản khách.\n\n"
                "THÔNG TIN THAM KHẢO:\n" + card["fact"])},
            {"role": "user", "content": question},
            {"role": "assistant", "content": styled_answer}],
            "source_id": source_sha[:16], "source_file": card["source"] + ".pdf",
            "source_url": url, "source_sha256": source_sha,
            "teacher": "qwen3.5:9b-question+two_critic_passes",
            "reviewed_by": "automated_candidate_review_not_manual",
            "answer_style": answer_style,
            "scenario_id": "shinhan-" + fact_id})
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUT.with_suffix(".jsonl.tmp")
    tmp.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows),
                   encoding="utf-8")
    tmp.replace(OUTPUT)
    return len(rows)


def revalidate_accepted(db: sqlite3.Connection, cards: dict) -> int:
    """Free per-fact capacity when stricter rules reject older critic passes."""
    changed = 0
    for row_id, fact_id, question in db.execute(
            "SELECT q.id,q.fact_id,q.question FROM questions q "
            "JOIN bulk_reviews b ON b.question_id=q.id WHERE b.status='accepted'"):
        card = cards.get(fact_id)
        reason = precheck(question, card) if card else "fact_card_withdrawn"
        if reason:
            db.execute("UPDATE bulk_reviews SET status='rejected',reason=? "
                       "WHERE question_id=?", ("revalidated:" + reason, row_id))
            changed += 1
    db.commit()
    if changed:
        print(f"bulk_review revalidated={changed}", flush=True)
    return changed


def run(args: argparse.Namespace) -> None:
    cards = {x["id"]: x for x in json.loads(CARDS.read_text(encoding="utf-8"))}
    manifest = {x["name"]: x for x in json.loads(MANIFEST.read_text(encoding="utf-8"))
                if x.get("status") == "downloaded" and x.get("use") == "review"}
    with sqlite3.connect(DB) as db:
        ensure_table(db)
        revalidate_accepted(db, cards)
        processed = 0
        for batch_index in range(args.max_batches):
            if batch_index % 20 == 0 and save_shortlist(db, cards, manifest) >= args.target:
                break
            if free_gib() < args.min_free_gib or not allowed("", dedicated=True):
                print("bulk_review_paused: disk_low_or_customer_backend", flush=True)
                break
            batch = next_batch(db, cards, args.max_per_fact)
            if batch is None:
                print("bulk_review_exhausted: need more verified facts/questions", flush=True)
                break
            card, candidate_rows = batch
            good = []
            for row_id, question in candidate_rows:
                reason = precheck(question, card)
                if reason:
                    db.execute("INSERT INTO bulk_reviews(question_id,status,reason) VALUES (?,?,?) "
                               "ON CONFLICT(question_id) DO UPDATE SET "
                               "status='rejected',reason=excluded.reason",
                               (row_id, "rejected", reason))
                else:
                    good.append((row_id, question))
            db.commit()
            good = good[:4]
            if not good:
                continue
            try:
                verdicts = ask_critic(card, good, args.ollama_url)
            except CustomerBusy:
                print("bulk_review_paused: customer_backend", flush=True)
                break
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                print(f"bulk_critic_error {type(exc).__name__}: {exc}", flush=True)
                for row_id, _ in good:
                    db.execute("INSERT INTO bulk_reviews(question_id,status,reason,attempts) "
                               "VALUES (?,'retry','critic_error',1) "
                               "ON CONFLICT(question_id) DO UPDATE SET attempts=attempts+1,"
                               "status=CASE WHEN attempts>=2 THEN 'uncertain' ELSE 'retry' END",
                               (row_id,))
                db.commit()
                continue
            for row_id, _ in good:
                passed, reason = verdicts[row_id]
                db.execute("INSERT INTO bulk_reviews(question_id,status,reason) VALUES (?,?,?) "
                           "ON CONFLICT(question_id) DO UPDATE SET "
                           "status=excluded.status,reason=excluded.reason",
                           (row_id, "accepted" if passed else "rejected", reason))
            db.commit()
            processed += len(good)
            if processed % 50 < len(good):
                total = db.execute("SELECT count(*) FROM bulk_reviews WHERE status='accepted'").fetchone()[0]
                print(f"bulk_review processed={processed} accepted={total}", flush=True)
        count = save_shortlist(db, cards, manifest)
        print(json.dumps({"bulk_shortlist": count, "target": args.target,
                          "processed_this_run": processed,
                          "path": str(OUTPUT)}, ensure_ascii=False), flush=True)


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=1200)
    ap.add_argument("--max-per-fact", type=int, default=90)
    ap.add_argument("--max-batches", type=int, default=80)
    ap.add_argument("--min-free-gib", type=float, default=11)
    ap.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    args = ap.parse_args()
    try:
        with exclusive_worker(STATE_DIR / "worker.lock"):
            run(args)
    except SystemExit as exc:
        print(str(exc), flush=True)


if __name__ == "__main__":
    main()
