import csv
import io
import asyncio
import logging

from fastapi import APIRouter, File, Form, Response, UploadFile
from pydantic import BaseModel

from backend.models import contacts_db, db, devices_db
from backend.services import dialer_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/phones", tags=["phones"])

# Header aliases accepted by the CSV importer, so a list exported from Excel in
# Vietnamese imports without the user having to rename columns.
_COLUMN_ALIASES = {
    "phone": ("phone", "sdt", "so dien thoai", "số điện thoại", "sđt", "số", "mobile", "number"),
    "name": ("name", "ten", "tên", "ho ten", "họ tên", "khach hang", "khách hàng", "customer"),
    "product": ("product", "san pham", "sản phẩm", "nhu cau", "nhu cầu"),
    "note": ("note", "ghi chu", "ghi chú", "notes", "comment"),
}


class ContactRequest(BaseModel):
    phone: str
    name: str = ""
    product: str = ""
    campaign_id: str = ""
    note: str = ""
    field1: str = ""
    field2: str = ""
    field3: str = ""


class ContactUpdate(BaseModel):
    phone: str | None = None
    name: str | None = None
    product: str | None = None
    campaign_id: str | None = None
    status: str | None = None
    note: str | None = None
    field1: str | None = None
    field2: str | None = None
    field3: str | None = None


class BulkDeleteRequest(BaseModel):
    contact_ids: list[str]


class CallRequest(BaseModel):
    device_id: str = ""
    voice_name: str = "default"


class CallResultRequest(BaseModel):
    status: str          # done | no_answer | busy | refused | invalid | dnc | pending
    note: str = ""


class CampaignRequest(BaseModel):
    name: str = "Chiến dịch mới"
    product: str = ""
    status: str = "draft"
    note: str = ""
    scenario_id: str = ""
    voice_name: str = "default"


class CampaignUpdate(BaseModel):
    name: str | None = None
    product: str | None = None
    status: str | None = None
    note: str | None = None
    # B1: kịch bản + giọng
    scenario_id: str | None = None
    voice_name: str | None = None
    # nhãn cột tuỳ biến
    field1_label: str | None = None
    field2_label: str | None = None
    field3_label: str | None = None
    # B3 "Cài đặt khác": máy chạy song song
    device_ids: str | None = None      # JSON list, rỗng = dùng thiết bị mặc định
    concurrency: int | None = None
    # B3: gọi lại
    retry_no_answer: int | None = None
    retry_busy: int | None = None
    retry_voicemail: int | None = None
    retry_max: int | None = None
    retry_delay_min: int | None = None
    # B3: ngày bắt đầu, khung giờ
    start_date: str | None = None      # 'YYYY-MM-DD'
    end_date: str | None = None
    call_windows: str | None = None    # JSON, xem campaign_runner
    timezone: str | None = None
    # B3: hành vi trong cuộc gọi
    on_voicemail: str | None = None    # hangup | continue
    detect_gender: int | None = None
    record_calls: int | None = None


class ImportFromCampaign(BaseModel):
    source_campaign_id: str
    statuses: list[str] = ["busy", "no_answer"]
    min_attempts: int = 0
    max_attempts: int = 99
    reset_status: bool = True


# --- contacts ----------------------------------------------------------------

@router.get("/contacts")
async def list_contacts(
    campaign_id: str = "",
    status: str = "",
    search: str = "",
    field1: str = "",
    field2: str = "",
    field3: str = "",
    page: int = 1,
    limit: int = 50,
):
    result = await contacts_db.list_contacts(
        campaign_id=campaign_id or None,
        status=status or None,
        search=search.strip() or None,
        page=page,
        limit=limit,
        fields={"field1": field1, "field2": field2, "field3": field3},
    )
    # Nhãn cột do chiến dịch quyết định, nên bảng ở giao diện hiện đúng tiêu đề
    # của file khách vừa nạp chứ không phải "field1".
    labels = {}
    if campaign_id:
        campaign = await contacts_db.get_campaign(campaign_id)
        if campaign:
            labels = {
                k: campaign.get(k, "")
                for k in ("field1_label", "field2_label", "field3_label")
                if campaign.get(k)
            }
    return {
        **result,
        "page": page,
        "limit": limit,
        "has_more": page * limit < result["total"],
        "statuses": contacts_db.CONTACT_STATUSES,
        "field_labels": labels,
    }


@router.post("/contacts")
async def create_contact(req: ContactRequest):
    result = await contacts_db.create_contact(**req.model_dump())
    if isinstance(result, str):
        return {"error": result}
    return {"contact": result}


@router.post("/contacts/import/preview")
async def preview_import(
    file: UploadFile | None = File(None),
    text: str = Form(""),
):
    """Show how the columns will be mapped, without writing anything.

    Worth a round trip: the mapping of unknown headings onto field1..3 is
    positional, and finding out it went to the wrong column AFTER importing
    twenty thousand leads is expensive to undo.
    """
    raw = (await file.read()).decode("utf-8-sig", errors="replace") if file else text
    rows, labels = _parse_contacts(raw)
    if not rows:
        return {"error": "Không đọc được số nào từ dữ liệu gửi lên"}
    return {
        "so_dong": len(rows),
        "nhan_cot": {k: v for k, v in labels.items() if k != "_bo_qua"},
        "cot_bo_qua": labels.get("_bo_qua", []),
        "xem_truoc": rows[:10],
    }


@router.post("/contacts/import")
async def import_contacts(
    file: UploadFile | None = File(None),
    text: str = Form(""),
    campaign_id: str = Form(""),
):
    """Import a CSV file, or a pasted list of numbers (one per line)."""
    if file is not None:
        raw = (await file.read()).decode("utf-8-sig", errors="replace")
    else:
        raw = text

    rows, labels = _parse_contacts(raw)
    if not rows:
        return {"error": "Không đọc được số nào từ dữ liệu gửi lên"}

    result = await contacts_db.import_contacts(rows, campaign_id or None)

    # Ghi nhãn cột lên chiến dịch. Chỉ ghi khi chiến dịch chưa có nhãn: nạp thêm
    # một file có tiêu đề khác không được đổi tên cột của dữ liệu đã nạp trước.
    nhan = {k: v for k, v in labels.items() if k != "_bo_qua"}
    if campaign_id and nhan:
        campaign = await contacts_db.get_campaign(campaign_id)
        if campaign:
            moi = {k: v for k, v in nhan.items() if not campaign.get(k)}
            if moi:
                await contacts_db.update_campaign(campaign_id, **moi)
                result["nhan_cot"] = moi

    if labels.get("_bo_qua"):
        result["canh_bao"] = (
            "Chỉ nhận được 3 cột tuỳ biến. Các cột bị bỏ qua: "
            + ", ".join(labels["_bo_qua"])
        )
    logger.info(f"Contacts imported: {result}")
    return result


@router.get("/contacts/export")
async def export_contacts(campaign_id: str = "", status: str = ""):
    """Download the current list as CSV (all rows, not just the visible page)."""
    result = await contacts_db.list_contacts(
        campaign_id=campaign_id or None,
        status=status or None,
        page=1,
        limit=100_000,
    )

    campaign = await contacts_db.get_campaign(campaign_id) if campaign_id else None
    # Xuất ra dùng đúng tiêu đề của file gốc, để nhập lại là khớp cột ngay.
    header_custom = [
        (campaign or {}).get(f"field{i}_label") or f"field{i}" for i in (1, 2, 3)
    ]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["phone", "name", "product", "status", "attempts", "note", *header_custom]
    )
    for c in result["contacts"]:
        writer.writerow([
            c["phone"], c["name"], c["product"], c["status"], c["attempts"], c["note"],
            c.get("field1", ""), c.get("field2", ""), c.get("field3", ""),
        ])

    # utf-8-sig so Excel on Windows shows Vietnamese correctly.
    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="danh_ba.csv"'},
    )


@router.post("/contacts/bulk-delete")
async def bulk_delete(req: BulkDeleteRequest):
    return {"deleted": await contacts_db.delete_contacts(req.contact_ids)}


@router.patch("/contacts/{contact_id}")
async def update_contact(contact_id: str, req: ContactUpdate):
    if req.status is not None and req.status not in contacts_db.CONTACT_STATUSES:
        return {"error": f"Trạng thái không hợp lệ: {req.status}"}
    contact = await contacts_db.update_contact(contact_id, **req.model_dump())
    if contact is None:
        return {"error": "Số điện thoại không tồn tại"}
    return {"contact": contact}


@router.delete("/contacts/{contact_id}")
async def delete_contact(contact_id: str):
    if not await contacts_db.delete_contact(contact_id):
        return {"error": "Số điện thoại không tồn tại"}
    return {"deleted": contact_id}


@router.get("/contacts/{contact_id}/attempts")
async def list_attempts(contact_id: str, limit: int = 20):
    return {"attempts": await contacts_db.list_attempts(contact_id, limit)}


@router.post("/contacts/{contact_id}/call")
async def call_contact(contact_id: str, req: CallRequest):
    """Open an AI session for this lead and ask the device to dial the number."""
    contact = await contacts_db.get_contact(contact_id)
    if contact is None:
        return {"error": "Số điện thoại không tồn tại"}

    device = (
        await devices_db.get_device(req.device_id)
        if req.device_id
        else await devices_db.get_default_device()
    )
    if device is None:
        return {"error": "Chưa có thiết bị nào — thêm thiết bị ở trang Thiết bị trước"}

    return await _dial_contact(contact, device, req.voice_name)


@router.post("/contacts/{contact_id}/result")
async def set_call_result(contact_id: str, req: CallResultRequest):
    """Chốt một cuộc gọi tay: dừng đường tiếng, ghi kết quả, đẩy vào báo cáo.

    Đây là chỗ nút "Đã tư vấn xong / Không nghe máy / ..." ở trang Danh bạ gọi
    tới. Phải làm ĐỦ ba việc, đúng thứ tự: dừng cầu tiếng (để bộ ghi âm chốt
    file và gán đường dẫn vào phiên), chốt báo cáo (kết quả + chất lượng + tóm
    tắt), rồi mới cập nhật trạng thái số. Bỏ bước giữa thì cuộc gọi tay không
    bao giờ hiện đúng trong trang Báo cáo.
    """
    if req.status not in contacts_db.CONTACT_STATUSES:
        return {"error": f"Trạng thái không hợp lệ: {req.status}"}

    contact = await contacts_db.get_contact(contact_id)
    if contact is None:
        return {"error": "Số điện thoại không tồn tại"}

    from backend.main import app_state
    from backend.services import call_session_service as css

    # Kết quả người dùng bấm là trạng thái của SỐ; báo cáo cần kết quả của CUỘC
    # GỌI. "refused" / "invalid" / "dnc" đều là đã nói chuyện được với khách.
    ket_qua = {
        "done": "done", "no_answer": "no_answer", "busy": "busy",
        "voicemail": "voicemail", "refused": "done", "invalid": "failed",
        "dnc": "done", "pending": "no_answer", "calling": "done",
    }.get(req.status, "done")

    chot = {}
    session_id = contact.get("last_session_id")
    if session_id:
        session = app_state.sessions.get(session_id)
        if session:
            device = None
            attempts = await contacts_db.list_attempts(contact_id, limit=1)
            if attempts and attempts[0].get("device_id"):
                device = await devices_db.get_device(attempts[0]["device_id"])
            chot = await css.dong_duong_tieng(device or {}, app_state, session, ket_qua)

    # Áp chính sách gọi lại của chiến dịch, giống hệt bộ quay số tự động: bấm
    # "Máy bận" bằng tay cũng phải được xếp lịch gọi lại.
    campaign = (
        await contacts_db.get_campaign(contact["campaign_id"])
        if contact.get("campaign_id") else None
    )
    if campaign and ket_qua in contacts_db.RETRYABLE:
        updated = await contacts_db.finish_attempt(contact_id, ket_qua, campaign, req.note)
    else:
        fields = {"status": req.status}
        if req.note:
            fields["note"] = req.note
        updated = await contacts_db.update_contact(contact_id, **fields)

    return {"contact": updated, "bao_cao": chot}


@router.post("/call-next")
async def call_next(req: CallRequest, campaign_id: str = ""):
    """Dial the oldest not-yet-called number - the campaign 'gọi tiếp' button."""
    contact = await contacts_db.next_pending(campaign_id or None)
    if contact is None:
        return {"error": "Không còn số nào chưa gọi trong danh sách"}

    device = (
        await devices_db.get_device(req.device_id)
        if req.device_id
        else await devices_db.get_default_device()
    )
    if device is None:
        return {"error": "Chưa có thiết bị nào — thêm thiết bị ở trang Thiết bị trước"}

    return await _dial_contact(contact, device, req.voice_name)


@router.get("/stats")
async def stats(campaign_id: str = ""):
    devices = await devices_db.list_devices()
    return {
        **await contacts_db.contact_stats(campaign_id or None),
        "devices": len(devices),
        "devices_online": sum(1 for d in devices if d["status"] == "online"),
    }


# --- campaigns ---------------------------------------------------------------

@router.get("/campaigns")
async def list_campaigns():
    return {
        "campaigns": await contacts_db.list_campaigns(),
        "statuses": contacts_db.CAMPAIGN_STATUSES,
    }


@router.post("/campaigns")
async def create_campaign(req: CampaignRequest):
    if req.status not in contacts_db.CAMPAIGN_STATUSES:
        return {"error": f"Trạng thái không hợp lệ: {req.status}"}
    return {"campaign": await contacts_db.create_campaign(**req.model_dump())}


@router.patch("/campaigns/{campaign_id}")
async def update_campaign(campaign_id: str, req: CampaignUpdate):
    if req.status is not None and req.status not in contacts_db.CAMPAIGN_STATUSES:
        return {"error": f"Trạng thái không hợp lệ: {req.status}"}
    campaign = await contacts_db.update_campaign(campaign_id, **req.model_dump())
    if campaign is None:
        return {"error": "Chiến dịch không tồn tại"}
    return {"campaign": campaign}


@router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str):
    campaign = await contacts_db.get_campaign(campaign_id)
    if campaign is None:
        return {"error": "Chiến dịch không tồn tại"}
    return {
        "campaign": campaign,
        **await contacts_db.pending_summary(campaign_id),
    }


@router.post("/campaigns/{campaign_id}/import-from")
async def import_from_campaign(campaign_id: str, req: ImportFromCampaign):
    """Kéo số từ một chiến dịch khác sang, lọc theo trạng thái và số lần đã gọi.

    Vì `contacts.phone` là UNIQUE, đây là CHUYỂN số chứ không nhân bản: một số
    chỉ nằm ở một chiến dịch tại một thời điểm. Lịch sử các lần gọi cũ vẫn tra
    được đầy đủ ở /contacts/{id}/attempts.
    """
    result = await contacts_db.import_from_campaign(
        target_campaign_id=campaign_id,
        source_campaign_id=req.source_campaign_id,
        statuses=req.statuses,
        min_attempts=req.min_attempts,
        max_attempts=req.max_attempts,
        reset_status=req.reset_status,
    )
    if result.get("error"):
        return result
    logger.info(
        f"Chuyển {result['imported']} số từ {req.source_campaign_id} sang {campaign_id}"
    )
    return {
        **result,
        "ghi_chu": "Số đã được CHUYỂN sang chiến dịch mới, không còn ở chiến dịch cũ",
    }


# --- chạy chiến dịch tự động --------------------------------------------------

@router.post("/campaigns/{campaign_id}/start")
async def start_campaign(campaign_id: str):
    """Bắt đầu quay số tự động. Tôn trọng khung giờ: ngoài giờ thì nó đợi."""
    from backend.main import app_state
    from backend.services.campaign_runner import campaigns

    ok, detail = await campaigns.start(campaign_id, app_state)
    if not ok:
        return {"error": detail}
    return {"started": True, "detail": detail, **(campaigns.progress(campaign_id) or {})}


@router.post("/campaigns/{campaign_id}/pause")
async def pause_campaign(campaign_id: str):
    from backend.services.campaign_runner import campaigns

    ok, detail = await campaigns.pause(campaign_id)
    return {"paused": ok, "detail": detail} if ok else {"error": detail}


@router.post("/campaigns/{campaign_id}/resume")
async def resume_campaign(campaign_id: str):
    from backend.main import app_state
    from backend.services.campaign_runner import campaigns

    ok, detail = await campaigns.resume(campaign_id, app_state)
    return {"resumed": ok, "detail": detail} if ok else {"error": detail}


@router.post("/campaigns/{campaign_id}/stop")
async def stop_campaign(campaign_id: str):
    from backend.services.campaign_runner import campaigns

    ok, detail = await campaigns.stop(campaign_id)
    return {"stopped": ok, "detail": detail} if ok else {"error": detail}


@router.get("/campaigns/{campaign_id}/progress")
async def campaign_progress(campaign_id: str):
    from backend.services.campaign_runner import campaigns

    tien_do = campaigns.progress(campaign_id)
    thong_ke = await contacts_db.contact_stats(campaign_id)
    cho = await contacts_db.pending_summary(campaign_id)
    return {
        "dang_chay": tien_do is not None,
        "tien_do": tien_do or {},
        "thong_ke": thong_ke,
        **cho,
    }


@router.get("/running")
async def running_campaigns():
    """Mọi chiến dịch đang chạy — dùng cho màn hình tổng quan."""
    from backend.services.campaign_runner import campaigns

    return {"campaigns": campaigns.all_progress()}


@router.delete("/campaigns/{campaign_id}")
async def delete_campaign(campaign_id: str):
    """Deleting a campaign keeps its numbers - they go back to the unassigned pool."""
    if not await contacts_db.delete_campaign(campaign_id):
        return {"error": "Chiến dịch không tồn tại"}
    return {"deleted": campaign_id}


# --- helpers -----------------------------------------------------------------

async def _dial_contact(contact: dict, device: dict, voice_name: str) -> dict:
    """Gọi một số bằng tay (nút "Gọi" ở trang Danh bạ).

    Đi qua ĐÚNG đường mà bộ quay số tự động dùng: phiên mang đủ số điện thoại,
    kịch bản, hồ sơ khách; máy ADB thì mở luôn cầu tiếng để có ghi âm, nhận diện
    giới tính và dò hộp thư thoại. Trước đây đường này dựng phiên trống, nên gọi
    tay xong là không có bản ghi âm lẫn dòng nào tra được trong Báo cáo.
    """
    from backend.main import app_state
    from backend.services import call_session_service as css
    from backend.services.phone_call_service import phone_calls

    campaign = (
        await contacts_db.get_campaign(contact["campaign_id"])
        if contact.get("campaign_id") else None
    )
    session = await css.mo_phien(
        app_state, contact=contact, campaign=campaign,
        voice_name=voice_name, direction="outbound",
    )

    ok, detail = await dialer_service.dial(device, contact["phone"])
    await devices_db.mark_status(
        device["device_id"], "online" if ok else "error", "" if ok else detail
    )

    # The session is opened either way: when the device has no click-to-call
    # hook the operator dials by hand and the AI still handles the conversation.
    updated = await contacts_db.record_attempt(
        contact["contact_id"],
        device_id=device["device_id"],
        session_id=session.session_id,
        status="dialed" if ok else "failed",
        detail=detail,
        contact_status="calling",
    )

    # Máy phone farm: nối đường tiếng ngay để AI nói được và để bộ ghi âm chạy.
    # Máy khác (gateway HTTP, tổng đài) thì tiếng đi đường riêng, chỉ mở phiên.
    tieng, canh_bao = False, ""
    if device.get("kind") == "adb" and device.get("address"):
        ghi = bool((campaign or {}).get("record_calls", 1))
        tieng, canh_bao = await phone_calls.start(
            device["address"], app_state.pipeline, session, ghi_am=ghi,
            cho_bat_may=True,
        )
        # Chào ngay khi khách bắt máy. Chạy NỀN chứ không await: hàm đó chờ tới
        # 45 giây cho người ta nhấc máy, mà đây là handler HTTP - giữ nó lại thì
        # giao diện treo suốt quãng đổ chuông.
        if tieng:
            asyncio.create_task(
                phone_calls.chao_khi_bat_may(device["address"]))
        if not tieng:
            logger.warning(f"[{contact['phone']}] không nối được đường tiếng: {canh_bao}")

    return {
        "contact": updated,
        "session_id": session.session_id,
        "device": device,
        "dialed": ok,
        "detail": detail,
        "duong_tieng": tieng,
        "canh_bao": "" if tieng else canh_bao,
    }


def _normalize_header(h: str) -> str:
    key = (h or "").strip().lower()
    for field, aliases in _COLUMN_ALIASES.items():
        if key in aliases:
            return field
    return key


def _parse_contacts(raw: str) -> tuple[list[dict], dict]:
    """Read CSV text, or a bare list of numbers (one per line).

    Returns (rows, labels). `labels` maps field1..3 to the heading the file used
    for that column, e.g. {"field1_label": "Chi nhánh"} - the contract asks for
    "thêm 1 2 trường nữa để ... dễ dàng lọc thông tin", and a column called
    "field1" in the report would not help anyone filter anything.

    Any heading that is not a known alias becomes the next free custom column,
    in the order it appears. Past the third one the column is dropped, and the
    caller says so instead of silently losing data.
    """
    text = (raw or "").strip()
    if not text:
        return [], {}

    first_line = text.splitlines()[0]
    has_header = any(
        _normalize_header(cell) in _COLUMN_ALIASES
        for cell in next(csv.reader([first_line]), [])
    )

    if not has_header:
        # No header row: treat column 1 as the number, column 2 as the name.
        rows = []
        for cells in csv.reader(io.StringIO(text)):
            if not cells or not cells[0].strip():
                continue
            rows.append({
                "phone": cells[0],
                "name": cells[1].strip() if len(cells) > 1 else "",
                "product": cells[2].strip() if len(cells) > 2 else "",
                "note": cells[3].strip() if len(cells) > 3 else "",
            })
        return rows, {}

    reader = csv.DictReader(io.StringIO(text))
    raw_headers = list(reader.fieldnames or [])

    mapping: dict[str, str] = {}   # tiêu đề gốc -> tên cột trong CSDL
    labels: dict[str, str] = {}
    du_cot: list[str] = []
    custom_slots = iter(("field1", "field2", "field3"))
    for header in raw_headers:
        known = _normalize_header(header)
        if known in _COLUMN_ALIASES:
            mapping[header] = known
            continue
        if not (header or "").strip():
            continue
        slot = next(custom_slots, None)
        if slot is None:
            du_cot.append(header)
            continue
        mapping[header] = slot
        labels[f"{slot}_label"] = header.strip()

    rows = []
    for r in reader:
        phone = ""
        row: dict = {}
        for header, column in mapping.items():
            value = (r.get(header) or "").strip()
            if column == "phone":
                phone = value
            else:
                row[column] = value
        if phone:
            rows.append({"phone": phone, **row})

    if du_cot:
        labels["_bo_qua"] = du_cot
    return rows, labels
