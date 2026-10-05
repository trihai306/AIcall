from training.llm.shinhan_fact_miner import chunks_from_text, valid_proposal


def test_miner_requires_exact_source_quote_and_excludes_variable_terms():
    text = ("Khách hàng có thể tra cứu lịch sử giao dịch thẻ qua Internet Banking "
            "để kiểm tra các khoản thanh toán đã ghi nhận trong kỳ.")
    assert chunks_from_text(text) == [text]
    good = {"quote": text, "fact": "Khách có thể xem lịch sử giao dịch thẻ qua Internet Banking.",
            "answer": "Dạ, mình xem lịch sử giao dịch thẻ trong Internet Banking ạ."}
    assert valid_proposal(good, text)
    assert not valid_proposal({**good, "quote": "Nguồn không hề nói câu này"}, text)
    assert not valid_proposal({**good, "fact": "Lãi suất cố định là 8%"}, text)
