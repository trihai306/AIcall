import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "training" / "llm"))
from teacher_threshold_questions import accepted_question


def test_accepts_only_age_question_with_preserved_number():
    assert accepted_question("Tôi đã 17 tuổi, riêng điều kiện tuổi mở thẻ đã đạt chưa?", 17, False)
    assert not accepted_question("Tôi 17 tuổi, cần chuẩn bị giấy tờ gì để mở thẻ?", 17, False)
    assert not accepted_question("Tôi 17 tuổi, riêng tuổi 18 mới được mở thẻ sao?", 17, False)


def test_followup_must_ask_about_age_without_repeating_it():
    assert accepted_question("Lương tôi 18 triệu, riêng điều kiện tuổi của tôi đã đạt chưa?", 21, True)
    assert not accepted_question("Tôi 21 tuổi, lương 18 triệu, riêng tuổi đã đạt chưa?", 21, True)


def test_rejects_approval_and_unrelated_product():
    assert not accepted_question("Với độ tuổi 22, tôi có đủ điều kiện để được ngân hàng chấp nhận cho vay hay không?", 22, False, "home22")
    assert not accepted_question("Bổ sung 18 triệu vào thu nhập thì ai trong độ tuổi bao nhiêu là đủ điều kiện?", 21, True, "home21-followup")
    assert accepted_question("Nếu tôi vừa tròn 22 tuổi thì giới hạn tuổi tối thiểu để vay mua nhà là thế nào?", 22, False, "home22")
