"""Nối lại phiên khi tải lại trang.

Server VỐN ĐÃ nối lại được: `websocket_call` lấy `app_state.sessions.get(id)` và
chỉ tạo mới khi không thấy. Chỗ hụt là trình duyệt - `sessionId` chỉ nằm trong
biến của trang, F5 là mất, nên nó xin phiên 'new' và server chiều theo.

Nối lại mà khung chat trống thì mới được nửa: bot nhớ, người dùng thì không
thấy gì, và họ không có cách nào biết bot còn nhớ hay không.
"""
from backend.pipeline.session_manager import CallSession


def test_phien_moi_bao_khong_phai_noi_lai():
    s = CallSession()
    assert s.payload_ket_noi(noi_lai=False)["noi_lai"] is False


def test_phien_moi_khong_gui_lich_su():
    assert CallSession().payload_ket_noi(noi_lai=False)["history"] == []


def test_noi_lai_thi_gui_kem_lich_su_de_ve_lai_khung_chat():
    s = CallSession()
    s.add_turn("user", "lãi suất bao nhiêu")
    s.add_turn("assistant", "Dạ từ 10.5% một năm ạ.")
    ra = s.payload_ket_noi(noi_lai=True)
    assert ra["noi_lai"] is True
    assert [t["content"] for t in ra["history"]] == [
        "lãi suất bao nhiêu", "Dạ từ 10.5% một năm ạ."]


def test_luon_kem_dung_ma_phien():
    s = CallSession()
    assert s.payload_ket_noi(noi_lai=True)["session_id"] == s.session_id


def test_lich_su_dai_chi_gui_phan_gan_nhat():
    # Cuộc dài không được đẩy vài trăm lượt qua WebSocket chỉ để vẽ lại màn hình.
    s = CallSession()
    for i in range(80):
        s.add_turn("user", f"câu {i}")
        s.add_turn("assistant", f"đáp {i}")
    ra = s.payload_ket_noi(noi_lai=True)
    assert len(ra["history"]) == CallSession.TOI_DA_LUOT_VE_LAI
    assert ra["history"][-1]["content"] == "đáp 79"


def test_type_van_la_connected_de_khong_pha_ban_frontend_cu():
    # Bản frontend cũ chỉ đọc `type` và `session_id`; thêm trường mới không được
    # làm nó hỏng.
    ra = CallSession().payload_ket_noi(noi_lai=False)
    assert ra["type"] == "connected"
