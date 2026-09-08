"""Phần khách chưa kịp nghe được PHÁT LẠI, không tổng hợp lại.

Tiếng đó đã sinh xong và đang nằm trong hàng đợi lúc bị cắt. Sinh lại bằng TTS
tốn thêm 300-700ms TTFA, tốn GPU, và ra một tông khác với đoạn khách vừa nghe
(cao độ F5 phụ thuộc nội dung chữ - xem memory `chat-ai-tong-lech-giua-cac-manh`).
"""
import asyncio

from backend.pipeline.session_manager import CallSession
from backend.services.phone_call_service import FRAME_BYTES_XUONG, PhoneCallBridge  # noqa: E501


def _bridge() -> PhoneCallBridge:
    return PhoneCallBridge(pipeline=None, session=CallSession(customer_name="Khách"))


def test_bo_hang_doi_thi_giu_lai_khung_chua_phat():
    b = _bridge()
    for _ in range(30):
        b._out.put_nowait(b"\x01" * FRAME_BYTES_XUONG)
    b.drop_pending_audio()
    assert len(b._khung_con_do) == 30


def test_phat_lai_dua_dung_nhung_khung_do_tro_lai_hang_doi():
    b = _bridge()
    for _ in range(30):
        b._out.put_nowait(b"\x01" * FRAME_BYTES_XUONG)
    b.drop_pending_audio()
    while not b._out.empty():          # dọn khung vuốt nhỏ dần
        b._out.get_nowait()
    assert b.phat_lai_phan_do() == 30
    assert b._out.qsize() == 30


def test_phat_lai_mot_lan_roi_thoi():
    b = _bridge()
    for _ in range(30):
        b._out.put_nowait(b"\x01" * FRAME_BYTES_XUONG)
    b.drop_pending_audio()
    b.phat_lai_phan_do()
    assert b.phat_lai_phan_do() == 0, "lượt sau nữa không được phát lại lần hai"


def test_khong_bi_cat_thi_khong_co_gi_de_phat_lai():
    assert _bridge().phat_lai_phan_do() == 0


class PipelineGia:
    async def process_turn(self, *a, **k):
        pass


def _bridge_bi_cat(cau: str, giay: float) -> PhoneCallBridge:
    """Bridge ở trạng thái vừa bị khách cắt lời, còn phần dở chưa phát."""
    b = PhoneCallBridge(pipeline=PipelineGia(),
                        session=CallSession(customer_name="Khách"))
    b._khung_con_do = [b"\x01" * FRAME_BYTES_XUONG] * 30
    b.session.cau_ai_con_do = cau
    b.session.giay_ai_con_do = giay
    return b


def test_luot_moi_phat_lai_phan_do_truoc_khi_dap():
    b = _bridge_bi_cat("không cần thế chấp", 1.2)
    b.session.spec_stt = (0, "thế còn thủ tục thì sao")
    asyncio.run(b._handle_turn(b"\x00" * 320))
    assert b._out.qsize() == 30, "phần dở phải được phát lại"
    assert b.session.da_doc_not is True, "đã đọc nốt thì bỏ câu đệm lượt này"


def test_khach_phu_dinh_thi_khong_phat_lai_va_don_sach():
    b = _bridge_bi_cat("không cần thế chấp", 1.2)
    b.session.spec_stt = (0, "không, ý em là vay thế chấp")
    asyncio.run(b._handle_turn(b"\x00" * 320))
    assert b._out.qsize() == 0, "khách cắt vì AI nói lạc - đừng đọc nốt đoạn lạc"
    assert b._khung_con_do == [], "và phải dọn, không để treo sang lượt sau"


def test_so_giay_phan_do_dung_bang_tieng_thuc_su_con_lai():
    # Sổ mảnh tính TRỌN mảnh, còn hàng đợi chỉ giữ phần CHƯA phát của mảnh đang
    # dở. Lấy số của sổ thì luật chặn 3 giây đo bằng thước rộng hơn thực tế và
    # chặn oan. Cuộc gọi 47475e87 (06-09-2026) ghi "còn dở 3.0s" nhưng chỉ phát
    # lại 103 khung = 2,06s.
    b = _bridge()
    for _ in range(30):                       # 30 khung = 0,6s còn trong hàng đợi
        b._out.put_nowait(b"\x01" * FRAME_BYTES_XUONG)
    b._so_manh.them("một mảnh dài đã phát gần hết", 200)   # sổ ghi trọn 4,0s
    b.drop_pending_audio()
    assert b.session.giay_ai_con_do == 0.6, (
        "phải đo bằng tiếng THỰC SỰ còn lại, không phải độ dài trọn mảnh")
