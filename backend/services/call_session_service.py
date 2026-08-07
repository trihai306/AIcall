"""Mở và chốt một phiên gọi — dùng chung cho MỌI đường gọi.

Có bốn đường tạo ra một cuộc gọi trong hệ thống này:

    1. Bộ quay số tự động            services/campaign_runner.py
    2. Bấm nút "Gọi" ở trang Danh bạ  api/phones.py
    3. Bật đường tiếng ở trang Thiết bị api/devices.py
    4. Bot nhận cuộc gọi đến          services/inbound_service.py
    (+ khung chat trên trình duyệt, dùng để thử)

Trước khi có file này, mỗi đường tự dựng phiên theo cách riêng — và chỉ đường
(1) gắn đủ số điện thoại, kịch bản, hồ sơ khách, ghi âm, chấm chất lượng, tóm
tắt. Ba đường còn lại đẻ ra phiên trống: báo cáo không lọc được, không có bản
ghi âm, không có tóm tắt. Người dùng bấm "Gọi" bằng tay thì mất sạch.

Gom vào một chỗ để bốn đường KHÔNG THỂ lệch nhau nữa: thêm một trường vào phiên
là cả bốn cùng có.
"""

import logging

from backend.models import contacts_db, db, scenarios_db

logger = logging.getLogger(__name__)


async def mo_phien(
    app_state,
    *,
    contact: dict | None = None,
    campaign: dict | None = None,
    phone: str = "",
    customer_name: str = "",
    product: str = "",
    voice_name: str = "",
    direction: str = "outbound",
    caller_number: str = "",
    scenario_id: str = "",
):
    """Dựng một CallSession đã gắn đủ nguồn gốc, kịch bản và hồ sơ khách.

    `contact` và `campaign` là dict lấy từ CSDL (có thể None). Thiếu cái nào thì
    hàm tự suy từ cái còn lại; thiếu cả hai vẫn chạy được — đó là trường hợp gọi
    thử từ trang Thiết bị.
    """
    contact = contact or {}
    campaign = campaign or {}

    # Chiến dịch của contact, nếu người gọi không truyền sẵn. Cần nó để lấy đúng
    # kịch bản và giọng mà chiến dịch đó đã cấu hình.
    if not campaign and contact.get("campaign_id"):
        campaign = await contacts_db.get_campaign(contact["campaign_id"]) or {}

    so = contacts_db.normalize_phone(phone or contact.get("phone", "") or caller_number)
    scenario = await scenarios_db.resolve(
        scenario_id or campaign.get("scenario_id", ""), direction
    )

    session = app_state.sessions.create(
        customer_name=customer_name or contact.get("name") or "Anh/Chị",
        product=product or contact.get("product") or campaign.get("product") or "",
        voice_name=voice_name or campaign.get("voice_name") or "default",
        campaign_id=campaign.get("campaign_id", "") or contact.get("campaign_id", "") or "",
        contact_id=contact.get("contact_id", ""),
        phone=so,
        direction=direction,
        caller_number=caller_number,
        scenario=scenario,
        fields={k: contact.get(k, "") for k in ("field1", "field2", "field3")},
    )

    # Hồ sơ khách từ nguồn dữ liệu ngoài. Tra MỘT LẦN lúc mở phiên: tra lại mỗi
    # lượt là đọc file Excel ngay giữa đường găng của độ trễ.
    if so:
        try:
            from backend.services import data_source_service
            ho_so = await data_source_service.tra_cuu_tat_ca(so)
            session.ngu_canh_khach = data_source_service.dung_ngu_canh(ho_so)
            # Giữ CẢ BẢN THÔ dạng bảng, không chỉ đoạn văn: `tra_loi_ho_so` cần
            # đọc thẳng từng trường để đáp câu hỏi về số mà không qua mô hình.
            # Gộp nhiều nguồn vào một từ điển, nguồn sau ghi đè nguồn trước.
            gop: dict = {}
            for m in ho_so:
                gop.update(m.get("du_lieu") or {})
            session.ho_so_khach = gop
            if ho_so:
                logger.info(f"[{so}] tra được hồ sơ từ {len(ho_so)} nguồn dữ liệu")
        except Exception as e:
            logger.debug(f"[{so}] không tra được nguồn dữ liệu ngoài: {e}")

    return session


async def chot_phien(app_state, session, ket_qua: str = "") -> dict:
    """Đóng một phiên: lưu lịch sử, chốt báo cáo, xếp hàng tóm tắt.

    Gọi ở MỌI chỗ kết thúc cuộc gọi. Bỏ sót một chỗ là các cuộc đi qua đó không
    có kết quả, không có chất lượng, không có tóm tắt — và biến mất khỏi mọi bộ
    lọc của trang Báo cáo.

    Không bao giờ ném lỗi ra ngoài: đây là bước dọn dẹp, hỏng ở đây không được
    phép làm hỏng luồng gọi.
    """
    if ket_qua:
        session.outcome = ket_qua

    ket = {}
    try:
        await db.save_session(session, ended=True)
    except Exception as e:
        logger.warning(f"Không lưu được phiên {session.session_id}: {e}")

    try:
        from backend.models import reports_db
        ket = await reports_db.finalize_session(session)
    except Exception as e:
        logger.warning(f"Không chốt được báo cáo phiên {session.session_id}: {e}")

    try:
        # Xếp hàng chứ không chạy ngay: tóm tắt cần LLM, mà LLM có thể đang phục
        # vụ cuộc gọi kế tiếp.
        from backend.services.summarizer import bo_tom_tat
        bo_tom_tat.xep_hang(session.session_id)
    except Exception as e:
        logger.debug(f"Không xếp hàng tóm tắt được: {e}")

    app_state.sessions.remove(session.session_id)
    return ket


async def dong_duong_tieng(device: dict, app_state, session=None, ket_qua: str = "") -> dict:
    """Dừng cầu tiếng của một máy RỒI mới chốt phiên.

    Thứ tự bắt buộc: bộ ghi âm chốt file trong `phone_calls.stop()` và mới gán
    `session.recording_path` ở đó. Chốt phiên trước thì báo cáo ghi nhận cuộc gọi
    không có bản ghi âm, dù file vẫn nằm trên đĩa.
    """
    from backend.services.phone_call_service import phone_calls

    serial = (device or {}).get("address", "")
    if serial and phone_calls.get(serial) is not None:
        try:
            await phone_calls.stop(serial)
        except Exception as e:
            logger.warning(f"Không dừng gọn được đường tiếng {serial}: {e}")

    if session is not None:
        return await chot_phien(app_state, session, ket_qua)
    return {}
