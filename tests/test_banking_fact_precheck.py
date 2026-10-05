from backend.core.banking_fact_precheck import banking_fact_precheck, direct_condition_answer
from backend.core.conversation_style import requested_region_note


MORTGAGE = "THÔNG TIN THAM KHẢO:\n- Công dân Việt Nam, từ 22 - 65 tuổi\n- Có tài sản đảm bảo"
CARD = "THÔNG TIN THAM KHẢO:\n- Từ 18 tuổi trở lên"
DEBT = "THÔNG TIN THAM KHẢO:\n- Nợ đã tất toán trên 1 năm: có thể xem xét"


def user(text):
    return {"role": "user", "content": text}


def test_age_threshold_and_history():
    messages = [user("Anh 21 tuổi"), user("Lương 18 triệu, điều kiện tuổi vay nhà đã đạt chưa?")]
    assert "21 tuổi chưa đạt" in direct_condition_answer(messages, MORTGAGE)
    assert "22 tuổi" in direct_condition_answer(messages, MORTGAGE)
    assert "66 tuổi chưa đạt" in direct_condition_answer(
        [user("Tôi 66 tuổi, riêng điều kiện tuổi vay nhà đã đạt chưa?")], MORTGAGE
    )


def test_card_age_and_no_source():
    messages = [user("Con tôi 17 tuổi, điều kiện tuổi mở thẻ đã đạt chưa?")]
    assert "17 tuổi chưa đạt" in direct_condition_answer(messages, CARD)
    assert not direct_condition_answer(messages, "Không có nguồn")


def test_settled_debt_requires_strictly_more_than_one_year():
    for months in (8, 12):
        answer = direct_condition_answer(
            [user(f"Nợ xấu đã tất toán {months} tháng, đã qua mốc để được xem xét chưa?")], DEBT
        )
        assert "chưa qua mốc trên 1 năm" in answer
    assert "CÓ THỂ xem xét" in banking_fact_precheck(
        [user("Nợ xấu đã tất toán 14 tháng, có được xem xét không?")], DEBT
    )
    assert "chưa thể khẳng định được duyệt" in direct_condition_answer(
        [user("Nợ xấu đã tất toán 14 tháng, có chắc được duyệt không?")], DEBT
    )
    assert "chưa qua mốc trên 1 năm" in direct_condition_answer(
        [user("Tôi trả hết nợ xấu 9 tháng rồi, đã qua mốc để được xem xét chưa?")], DEBT
    )


def test_collateral_and_ambiguous_threshold():
    assert "chưa thể kết luận đủ điều kiện" in direct_condition_answer(
        [user("Tôi chưa có tài sản bảo đảm, có thể kết luận đủ điều kiện vay được không?")], MORTGAGE
    )
    assert not direct_condition_answer(
        [user("Tôi 17 tuổi, điều kiện tuổi đã đạt chưa?")], MORTGAGE + "\n- Từ 18 tuổi trở lên"
    )


def test_customer_region_preference_persists_across_turns():
    assert "MIỀN NAM" in requested_region_note(
        [user("Em nói theo cách miền Nam nhé"), {"role": "assistant", "content": "Dạ"}, user("Thẻ Gold sao em?")]
    )
    assert "MIỀN BẮC" in requested_region_note(
        [user("Nói kiểu miền Nam"), user("Đổi sang miền Bắc giúp anh")]
    )


def test_source_grounded_fee_and_online_rate():
    card_source = ("THÔNG TIN THAM KHẢO:\n- Miễn phí thường niên năm đầu tiên\n"
                   "2. Thẻ Gold: Hạn mức 30-200 triệu, phí thường niên 400.000đ/năm")
    fee = direct_condition_answer(
        [user("Thẻ Gold miễn phí năm đầu, từ năm thứ hai phí bao nhiêu một năm?")], card_source
    )
    assert "400.000đ/năm" in fee
    savings = ("THÔNG TIN THAM KHẢO:\n- Kỳ hạn 12 tháng: lãi suất 5.5%/năm\n"
               "- Lãi suất cộng thêm 0.2%/năm so với gửi tại quầy")
    answer = direct_condition_answer(
        [user("Gửi online kỳ hạn 12 tháng thì cộng lên bao nhiêu?")], savings
    )
    assert "5.7%/năm" in answer
