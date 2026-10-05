from backend.core.training_guard import busy_reason, live_service_busy_reason
from backend.core.service_priority import reserve_customer_turn, release_customer_turn


def test_voice_call_blocks_training():
    assert "cuộc gọi" in busy_reason([{"running": True}], [], [])


def test_campaign_and_inbound_listener_block_training():
    assert "Chiến dịch" in busy_reason([], [{"trang_thai": "dang_chay"}], [])
    assert "tự nhận" in busy_reason([], [], [{"dang_nghe": True}])


def test_idle_services_allow_training():
    assert busy_reason([{"running": False}], [{"trang_thai": "tam_dung"}],
                       [{"dang_nghe": False}]) == ""


def test_web_turn_blocks_training_without_phone_call():
    token = object()
    reserve_customer_turn(token)
    try:
        assert "web" in live_service_busy_reason()
    finally:
        release_customer_turn(token)


def test_recent_customer_activity_has_cooldown():
    token = object()
    reserve_customer_turn(token)
    release_customer_turn(token)
    assert "hai phút" in live_service_busy_reason()
