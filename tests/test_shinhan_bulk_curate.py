import json
import sqlite3

import pytest

from training.llm import shinhan_bulk_curate as bulk
from training.llm import shinhan_large_teacher as teacher


def test_bulk_precheck_blocks_out_of_scope_and_machine_wording():
    card = {"id": "activate_card", "intent": "kích hoạt thẻ"}
    assert not bulk.precheck("Tôi vừa nhận thẻ Shinhan, có thể kích hoạt thẻ ở đâu?", card)
    assert bulk.precheck("Em hỏi xem kích hoạt thẻ ra sao nhé?", card)
    assert bulk.precheck("Tại sao tôi kích hoạt thẻ bị lỗi?", card)
    assert bulk.precheck("Bác dùng thẻ mới nhận có cần gọi số hotline không?", card)
    assert bulk.precheck(
        "Bảng sao kê có lãi suất vay tháng này không nhỉ?",
        {"id": "statement_contents", "intent": "sao kê|lãi suất"})
    assert bulk.precheck(
        "Chị có bật giao dịch nước ngoài cho thẻ này chưa?",
        {"id": "toggle_foreign_card", "intent": "giao dịch nước ngoài"})
    assert bulk.precheck(
        "Thanh toán thẻ.*thẻ người khác có dùng được không?",
        {"id": "pay_card_own_function", "intent": "Thanh toán thẻ.*thẻ người khác"})


@pytest.mark.parametrize(("fact_id", "question"), [
    ("set_pin", "Anh giúp mình đặt mã PIN cho thẻ mới được không?"),
    ("register_digital_card", "Tôi cần giúp gì khi muốn đăng ký thẻ điện tử ạ?"),
    ("minimum_payment", "Thanh toán tối thiểu của khoản vay tôi là bao nhiêu?"),
    ("manage_card_limits", "Bác biết mình cần thiết lập hạn mức thanh toán online ra sao?"),
    ("manage_card_limits", "Chị có cách nào để điều chỉnh hạn mức giao dịch không?"),
    ("pay_card_sol", "Tôi nên dùng thanh toán thẻ trên SOL hay chuyển khoản nội bộ để trả?"),
    ("toggle_online_card", "Anh ơi, mình có bật giao dịch trực tuyến trên thẻ Shinhan không?"),
    ("early_repayment", "Phí trả khoản vay sớm nếu có thì tính như thế nào theo hợp đồng?"),
    ("loan_repayment_obligation", "Có cần tôi thanh toán khoản vay đúng hạn ngay lập tức?"),
    ("pay_card_own_function", "Chị thắc mắc làm sao để dùng chức năng Thanh toán thẻ cho chính mình đây?"),
])
def test_bulk_precheck_rejects_reviewed_answer_mismatches(fact_id, question):
    cards = json.loads(bulk.CARDS.read_text(encoding="utf-8"))
    card = next(card for card in cards if card["id"] == fact_id)
    assert bulk.precheck(question, card)


@pytest.mark.parametrize(("fact_id", "question"), [
    ("statement_contents", "Sao kê có hiển thị ngày đến hạn thanh toán không anh?"),
    ("corporate_debit_pay_from_account",
     "Em muốn hỏi thẻ ghi nợ doanh nghiệp trả tiền dịch vụ được không?"),
])
def test_bulk_precheck_keeps_questions_answered_by_verified_card(fact_id, question):
    cards = json.loads(bulk.CARDS.read_text(encoding="utf-8"))
    card = next(card for card in cards if card["id"] == fact_id)
    assert not bulk.precheck(question, card)


def test_style_answer_changes_only_opening_and_duplicate_particle():
    answer = "Dạ, mình có thể trả thẻ tại quầy nhé ạ."
    variants = {bulk.style_answer(answer, f"Câu hỏi tự nhiên số {i} hông?")[0]
                for i in range(3)}
    assert variants == {"Dạ, mình có thể trả thẻ tại quầy nhé."}
    for i in range(20):
        styled, label = bulk.style_answer(answer, f"Tôi có thể trả thẻ tại quầy số {i}?")
        assert styled.removeprefix("Dạ, ").removeprefix("Vâng, ").casefold() == \
               "mình có thể trả thẻ tại quầy nhé."
        assert label in {"friendly_north", "friendly_south", "neutral"}


def test_bulk_shortlist_requires_current_source_and_fixed_answer(tmp_path, monkeypatch):
    db = teacher.db_open(tmp_path / "state.sqlite")
    bulk.ensure_table(db)
    rows = [
        ("activate_card", "one", "Tôi vừa nhận thẻ Shinhan, có thể kích hoạt thẻ ở đâu?",
         "Vào SOL để kích hoạt thẻ.", "https://shinhan.com.vn/a.pdf", "abc", "neutral"),
        ("activate_card", "two", "Tôi vừa nhận thẻ Shinhan, có thể kích hoạt thẻ ở đâu ạ?",
         "Đáp án cũ không còn đúng", "https://shinhan.com.vn/a.pdf", "abc", "neutral"),
    ]
    db.executemany("INSERT INTO questions(fact_id,normalized,question,answer,source_url,"
                   "source_sha256,persona) VALUES (?,?,?,?,?,?,?)", rows)
    db.execute("INSERT INTO bulk_reviews(question_id,status,reason) VALUES (1,'accepted','')")
    db.execute("INSERT INTO bulk_reviews(question_id,status,reason) VALUES (2,'accepted','')")
    db.commit()
    monkeypatch.setattr(bulk, "OUTPUT", tmp_path / "shortlist.jsonl")
    cards = {"activate_card": {"id": "activate_card", "source": "card_guide",
             "fact": "Sau khi nhận thẻ, kích hoạt trong SOL.", "intent": "kích hoạt thẻ",
             "answer": "Vào SOL để kích hoạt thẻ."}}
    manifest = {"card_guide": {"sha256": "abc", "url": "https://shinhan.com.vn/a.pdf"}}
    assert bulk.save_shortlist(db, cards, manifest) == 1
    item = json.loads(bulk.OUTPUT.read_text().splitlines()[0])
    assert item["messages"][-1]["content"] == "Vào SOL để kích hoạt thẻ."
    assert item["reviewed_by"] == "automated_candidate_review_not_manual"
