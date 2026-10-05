from training.llm.train_lora import conversation_group_key


def test_same_document_different_questions_are_separate_groups():
    a = {"source_id": "card.md", "messages": [{"role": "user", "content": "Tôi 17 tuổi."}]}
    b = {"source_id": "card.md", "messages": [{"role": "user", "content": "Tôi 20 tuổi."}]}
    assert conversation_group_key(a) != conversation_group_key(b)


def test_prefixes_of_same_conversation_stay_together():
    first = {"source_id": "card.md", "messages": [{"role": "user", "content": "Tôi 17 tuổi."}]}
    second = {"source_id": "card.md", "messages": [
        {"role": "user", "content": "Tôi 17 tuổi."},
        {"role": "assistant", "content": "Em nghe rồi ạ."},
        {"role": "user", "content": "Thế đã đủ tuổi chưa?"},
    ]}
    assert conversation_group_key(first) == conversation_group_key(second)
