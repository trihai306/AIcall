from training.llm.evaluate_natural_dialogue import score_answer


def test_natural_dialogue_blocks_approval_promise_and_role_reversal():
    assert not score_answer("Có đủ hồ sơ thì mới được duyệt ạ.", [], [])["ok"]
    assert not score_answer("Em gửi được 1 triệu rồi ạ.", [], [])["ok"]
    assert not score_answer("7,9% là mức chắc chắn cho hồ sơ anh.", [],
                            [r"mức chắc chắn"])["ok"]
