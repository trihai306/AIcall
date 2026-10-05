import json
from pathlib import Path

from training.llm.shinhan_large_teacher import valid_question


CARDS = Path(__file__).resolve().parents[1] / "data/training/shinhan_verified_fact_cards.json"


def test_pin_questions_must_match_documented_answer():
    card = next(x for x in json.loads(CARDS.read_text(encoding="utf-8")) if x["id"] == "set_pin")
    for bad in (
        "Chị cho biết cần làm gì để thiết lập PIN tại chi nhánh ngân hàng?",
        "Em xin hỏi làm sao để nhập mã PIN sau khi nhận thẻ Shinhan online?",
        "Em cần đến chi nhánh Shinhan để thiết lập mã PIN như thế nào ạ?",
        "Chú ơi, mình có thể đổi PIN trực tuyến ngay sau khi kích hoạt thẻ không?",
    ):
        assert not valid_question(bad, card), bad
    for good in (
        "Anh ơi, sau khi kích hoạt thẻ thì mình làm sao để thiết lập PIN?",
        "Chị có thể hướng dẫn em đặt mã PIN qua Internet Banking không?",
    ):
        assert valid_question(good, card), good
