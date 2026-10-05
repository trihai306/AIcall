from backend.core.conversation_style import requested_address_note, requested_region_note


def test_latest_explicit_address_persists_across_turns():
    messages = [
        {"role": "user", "content": "Gọi tôi là cô nhé."},
        {"role": "assistant", "content": "Dạ cô."},
        {"role": "user", "content": "Thẻ Gold phí năm thứ hai bao nhiêu?"},
    ]
    assert '"cô"' in requested_address_note(messages)
    messages.append({"role": "user", "content": "À, cứ gọi tôi là bác."})
    assert '"bác"' in requested_address_note(messages)


def test_region_follows_latest_customer_preference():
    messages = [
        {"role": "user", "content": "Nói kiểu miền Bắc nhé."},
        {"role": "user", "content": "Giờ em nói theo cách miền Nam."},
    ]
    assert "MIỀN NAM" in requested_region_note(messages)


def test_no_address_inferred_without_explicit_request():
    assert not requested_address_note([{"role": "user", "content": "Cô ấy hỏi thẻ Gold."}])


def test_customer_self_reference_is_an_address_preference():
    assert '"bác"' in requested_address_note([{"role": "user", "content": "Bác hỏi phí năm sau."}])
    assert '"chú"' in requested_address_note([{"role": "user", "content": "Nói giúp chú nhé."}])
