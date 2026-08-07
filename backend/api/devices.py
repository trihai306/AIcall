import logging

from fastapi import APIRouter
from pydantic import BaseModel

from backend.models import devices_db
from backend.services import adb_service, dialer_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/devices", tags=["devices"])


class DeviceRequest(BaseModel):
    name: str = ""
    kind: str = "phone_link"        # adb | phone_link | usb_modem | sip | audio
    address: str = ""               # host:port, http url, /dev/tty..., MAC or SIP uri
    dial_url: str = ""              # click-to-call hook, {number} placeholder
    phone_number: str = ""          # SIM number on this device
    note: str = ""


class DeviceUpdate(BaseModel):
    name: str | None = None
    kind: str | None = None
    address: str | None = None
    dial_url: str | None = None
    phone_number: str | None = None
    note: str | None = None


class TestCallRequest(BaseModel):
    number: str


@router.get("")
async def list_devices():
    devices = await devices_db.list_devices()
    return {
        "devices": devices,
        "kinds": devices_db.KINDS,
        "online": sum(1 for d in devices if d["status"] == "online"),
    }


@router.get("/suggestions")
async def suggest_devices():
    """Serial ports on this machine that look like a modem - not yet saved."""
    return {"suggestions": dialer_service.suggest_devices()}


@router.get("/scan/adb")
async def scan_adb():
    """Handsets visible over ADB (the phone farm), flagged if already saved."""
    handsets, error = await adb_service.list_handsets()
    saved = {d["address"] for d in await devices_db.list_devices() if d["kind"] == "adb"}

    found = []
    for h in handsets:
        item = {
            "name": h["model"],
            "kind": "adb",
            "address": h["serial"],
            "state": h["state"],
            "saved": h["serial"] in saved,
        }
        # Chi tiết chỉ lấy được khi máy đã cho phép gỡ lỗi USB.
        if h["state"] == "device":
            info = await adb_service.describe(h["serial"])
            item["name"] = f"{info.get('brand', '')} {info.get('model', '')}".strip() or h["model"]
            item["operator"] = info.get("operator", "")
            item["android"] = info.get("android", "")
            item["battery"] = info.get("battery")
        found.append(item)

    return {
        "devices": found,
        "error": error,
        "adb_installed": adb_service.adb_available(),
    }


class ImportRequest(BaseModel):
    devices: list[DeviceRequest]


@router.post("/import")
async def import_devices(req: ImportRequest):
    """Save several scanned devices at once. Skips addresses already stored."""
    existing = {
        (d["kind"], d["address"]) for d in await devices_db.list_devices() if d["address"]
    }

    added, skipped = [], 0
    for item in req.devices:
        if item.kind not in devices_db.KINDS:
            continue
        if item.address and (item.kind, item.address) in existing:
            skipped += 1
            continue
        device = await devices_db.create_device(**item.model_dump())
        if device:
            added.append(device)
            existing.add((item.kind, item.address))

    logger.info(f"Imported {len(added)} device(s), skipped {skipped} duplicate(s)")
    return {"added": added, "added_count": len(added), "skipped": skipped}


@router.post("")
async def create_device(req: DeviceRequest):
    if not req.name.strip():
        return {"error": "Chưa nhập tên thiết bị"}
    if req.kind not in devices_db.KINDS:
        return {"error": f"Loại thiết bị không hợp lệ: {req.kind}"}

    device = await devices_db.create_device(**req.model_dump())
    if device is None:
        return {"error": "Không lưu được thiết bị"}
    logger.info(f"Device added: {device['name']} ({device['kind']})")
    return {"device": device}


@router.patch("/{device_id}")
async def update_device(device_id: str, req: DeviceUpdate):
    if req.kind is not None and req.kind not in devices_db.KINDS:
        return {"error": f"Loại thiết bị không hợp lệ: {req.kind}"}
    device = await devices_db.update_device(device_id, **req.model_dump())
    if device is None:
        return {"error": "Thiết bị không tồn tại"}
    return {"device": device}


@router.delete("/{device_id}")
async def delete_device(device_id: str):
    if not await devices_db.delete_device(device_id):
        return {"error": "Thiết bị không tồn tại"}
    return {"deleted": device_id}


@router.post("/{device_id}/default")
async def set_default_device(device_id: str):
    device = await devices_db.set_default(device_id)
    if device is None:
        return {"error": "Thiết bị không tồn tại"}
    return {"device": device}


@router.post("/{device_id}/check")
async def check_device(device_id: str):
    """Probe the device and store the result as its status."""
    device = await devices_db.get_device(device_id)
    if device is None:
        return {"error": "Thiết bị không tồn tại"}

    status, detail = await dialer_service.check_device(device)
    updated = await devices_db.mark_status(
        device_id, status, "" if status == "online" else detail
    )
    return {"device": updated, "status": status, "detail": detail}


@router.post("/check-all")
async def check_all_devices():
    """Probe every device - what the 'Kiểm tra tất cả' button calls."""
    results = []
    for device in await devices_db.list_devices():
        status, detail = await dialer_service.check_device(device)
        await devices_db.mark_status(
            device["device_id"], status, "" if status == "online" else detail
        )
        results.append({"device_id": device["device_id"], "status": status, "detail": detail})
    return {"results": results, "devices": await devices_db.list_devices()}


@router.get("/diagnose/{serial}")
async def diagnose_serial(serial: str):
    """Kiểm tra trọn vẹn một handset vừa cắm vào, theo serial ADB.

    Dùng ngay sau khi quét, trước cả khi lưu thiết bị: cắm máy vào mà không gọi
    được thì nguyên nhân nằm rải rác (chưa bật gỡ lỗi USB, máy đang khoá, chưa
    có SIM, mất sóng...) nên trả về từng mục thay vì một chữ online/offline.
    """
    return await adb_service.diagnose(serial)


@router.post("/{device_id}/diagnose")
async def diagnose_device(device_id: str):
    """Như trên nhưng cho thiết bị đã lưu. Chỉ máy trong phone farm mới có."""
    device = await devices_db.get_device(device_id)
    if device is None:
        return {"error": "Thiết bị không tồn tại"}
    if device["kind"] != "adb":
        return {"error": "Chỉ máy trong phone farm (ADB) mới kiểm tra được chi tiết"}

    result = await adb_service.diagnose(device["address"])

    # Kết quả chẩn đoán cũng là một lần kiểm tra kết nối - cập nhật luôn cột
    # trạng thái để danh sách không hiện thông tin cũ.
    status = "online" if result.get("connected") else "offline"
    detail = next((c["detail"] for c in result["checks"] if c["status"] == "fail"), "")
    await devices_db.mark_status(device_id, status, detail)

    result["device"] = await devices_db.get_device(device_id)
    return result


@router.post("/{device_id}/test-call")
async def test_call(device_id: str, req: TestCallRequest):
    """Place a real call through the device, without touching the contact list."""
    device = await devices_db.get_device(device_id)
    if device is None:
        return {"error": "Thiết bị không tồn tại"}
    if not req.number.strip():
        return {"error": "Chưa nhập số cần gọi thử"}

    ok, detail = await dialer_service.dial(device, req.number.strip())
    if not ok:
        await devices_db.mark_status(device_id, "error", detail)
    else:
        await devices_db.mark_status(device_id, "online")
    return {"dialed": ok, "detail": detail, "device": await devices_db.get_device(device_id)}


@router.post("/{device_id}/hangup")
async def hangup_device(device_id: str):
    """End the call in progress on this device (ADB handsets only)."""
    device = await devices_db.get_device(device_id)
    if device is None:
        return {"error": "Thiết bị không tồn tại"}
    ok, detail = await dialer_service.hangup(device)
    return {"hungup": ok, "detail": detail}


@router.post("/{device_id}/inbound/enable")
async def enable_inbound(device_id: str, scenario_id: str = "", delay_s: float = 2.0):
    """Bật tự nhận cuộc gọi đến trên máy này (Điều 6: bot tiếp nhận cuộc gọi vào)."""
    from backend.main import app_state
    from backend.services.inbound_service import goi_vao

    if scenario_id or delay_s != 2.0:
        await devices_db.update_device(
            device_id,
            inbound_scenario_id=scenario_id or None,
            inbound_delay_s=max(0.0, delay_s),
        )
    ok, detail = await goi_vao.bat(device_id, app_state)
    return {"enabled": ok, "detail": detail} if ok else {"error": detail}


@router.post("/{device_id}/inbound/disable")
async def disable_inbound(device_id: str):
    from backend.services.inbound_service import goi_vao

    ok, detail = await goi_vao.tat(device_id)
    return {"disabled": ok, "detail": detail} if ok else {"error": detail}


@router.get("/inbound/status")
async def inbound_status():
    from backend.services.inbound_service import goi_vao

    return {"devices": goi_vao.trang_thai()}


@router.get("/{device_id}/call-state")
async def device_call_state(device_id: str):
    """Live call state of an ADB handset: idle | ringing | offhook."""
    device = await devices_db.get_device(device_id)
    if device is None:
        return {"error": "Thiết bị không tồn tại"}
    if device["kind"] != "adb":
        return {"state": "unknown", "detail": "Chỉ máy ADB mới đọc được trạng thái cuộc gọi"}
    state, detail = await adb_service.call_state(device["address"])
    return {"state": state, "detail": detail}


# --- đường tiếng: nối cuộc gọi trên máy vào pipeline hội thoại ------------------

class VoiceStartRequest(BaseModel):
    src: int = 4                    # 4 = tiếng cuộc gọi thật, 1 = mic (chạy thử)
    port: int = 8123
    inject: bool = True             # tiêm tiếng AI vào đường lên cho khách nghe
    customer_name: str = "Khách hàng"
    product: str = ""
    # Khai số điện thoại thì phiên tra được trong Báo cáo và hệ thống tự lấy
    # tên khách + hồ sơ từ danh bạ / nguồn dữ liệu ngoài.
    phone: str = ""
    voice_name: str = ""
    scenario_id: str = ""
    ghi_am: bool = True


@router.get("/voice/status")
async def voice_status():
    from backend.services.phone_call_service import phone_calls
    return {"calls": phone_calls.status()}


@router.post("/{device_id}/voice/start")
async def voice_start(device_id: str, req: VoiceStartRequest):
    """Mở đường tiếng hai chiều giữa máy và pipeline.

    Sau lệnh này, tiếng khách nói đi thẳng vào STT còn tiếng AI đi ra đường lên
    của cuộc gọi — không qua trình duyệt. Dùng `src=1` để chạy thử bằng micro
    của máy khi chưa có SIM.
    """
    from backend.main import app_state
    from backend.services.phone_call_service import phone_calls

    device = await devices_db.get_device(device_id)
    if device is None:
        return {"error": "Thiết bị không tồn tại"}
    if device["kind"] != "adb":
        return {"error": "Chỉ máy trong phone farm (ADB) mới mở được đường tiếng"}

    from backend.models import contacts_db
    from backend.services import call_session_service as css

    # Số điện thoại / khách hàng nếu người dùng khai — để phiên này cũng tra
    # được trong Báo cáo chứ không thành một dòng trống.
    contact = None
    if req.phone:
        got = await contacts_db.list_contacts(
            search=contacts_db.normalize_phone(req.phone), limit=1)
        contact = (got.get("contacts") or [None])[0]

    session = await css.mo_phien(
        app_state,
        contact=contact,
        phone=req.phone,
        customer_name=req.customer_name or "Khách hàng",
        product=req.product or "",
        voice_name=req.voice_name,
        scenario_id=req.scenario_id,
        direction="outbound",
    )
    ok, msg = await phone_calls.start(
        device["address"], app_state.pipeline, session,
        port=req.port, src=req.src, inject=req.inject, ghi_am=req.ghi_am,
    )
    if not ok:
        app_state.sessions.remove(session.session_id)
        return {"error": msg}
    return {"started": True, "detail": msg, "session_id": session.session_id,
            "serial": device["address"], "ghi_am": req.ghi_am}


@router.post("/{device_id}/voice/stop")
async def voice_stop(device_id: str, ket_qua: str = "done"):
    """Dừng đường tiếng VÀ chốt phiên vào báo cáo.

    Trước đây chỉ dừng cầu tiếng: phiên nằm lại trong bộ nhớ, không có kết quả,
    không có chất lượng, không có tóm tắt, và bản ghi âm tuy đã nằm trên đĩa
    nhưng không dòng nào trong Báo cáo trỏ tới nó.
    """
    from backend.main import app_state
    from backend.services import call_session_service as css
    from backend.services.phone_call_service import phone_calls

    device = await devices_db.get_device(device_id)
    if device is None:
        return {"error": "Thiết bị không tồn tại"}

    # Lấy phiên TRƯỚC khi dừng: `phone_calls.stop()` gỡ cầu tiếng khỏi bảng nên
    # sau đó không còn đường nào lần ra phiên nữa.
    bridge = phone_calls.get(device["address"])
    session = getattr(bridge, "session", None) if bridge else None

    ok, msg = await phone_calls.stop(device["address"])
    chot = {}
    if session is not None:
        chot = await css.chot_phien(app_state, session, ket_qua)
    return {"stopped": ok, "detail": msg, "bao_cao": chot}


class VoiceSayRequest(BaseModel):
    text: str
    xu_ly: bool = True     # False = gửi tiếng gốc, chỉ dùng khi so sánh A/B


@router.post("/{device_id}/voice/say")
async def voice_say(device_id: str, req: VoiceSayRequest):
    """Cho AI đọc một câu NGAY vào cuộc gọi, không đợi khách mở lời.

    Cầu tiếng vốn chỉ phản ứng khi nghe thấy khách nói. Với cuộc gọi RA thì
    chính AI phải chào trước, nên thiếu đường này là đầu bên kia nhấc máy lên
    chỉ nghe im lặng — đúng triệu chứng đã gặp: `turns=0` suốt cuộc gọi trong
    khi đường tiêm vẫn thông.

    Cũng là cách duy nhất nghe thử giọng qua điện thoại thật: tiếng bíp đo được
    độ trễ nhưng không nói lên gì về chất giọng, vì bộ mã thoại dựng cho tiếng
    NÓI luôn làm méo tông thuần.
    """
    from backend.main import app_state
    from backend.services.phone_call_service import phone_calls

    device = await devices_db.get_device(device_id)
    if device is None:
        return {"error": "Thiết bị không tồn tại"}
    if not req.text.strip():
        return {"error": "Chưa có câu nào để đọc"}

    bridge = phone_calls.get(device["address"])
    if bridge is None:
        return {"error": "Máy này chưa mở đường tiếng — gọi /voice/start trước"}
    if not bridge.running:
        return {"error": "Cầu tiếng đã đóng (cuộc gọi kết thúc?) — mở lại trước"}

    # Giọng lấy từ phiên của chính cuộc gọi này, không lấy mặc định: mỗi máy
    # trong phone farm có thể đang chạy một giọng khác nhau.
    giong = getattr(bridge.session, "voice_name", None) or "default"
    wav = await app_state.tts.synthesize(req.text, voice=giong)
    await bridge.play(wav, xu_ly=req.xu_ly)
    return {"da_doc": req.text, "giong": giong, "bytes": len(wav)}


class VoiceProbeRequest(BaseModel):
    burst_ms: int = 300
    freq: float = 1000.0
    amp: int = 14000


@router.post("/{device_id}/voice/probe")
async def voice_probe(device_id: str, req: VoiceProbeRequest):
    """Đo độ trễ tiếng đi từ hệ thống xuống điện thoại.

    Trả về hai con số tách bạch: `hang_doi_ms` là phần code này chịu trách
    nhiệm (pipeline giao tiếng -> khung đầu ra socket), `vong_ms` là đo âm học
    trọn vòng nếu micro nghe được tiếng loa vọng lại.
    """
    from backend.services.phone_call_service import phone_calls

    device = await devices_db.get_device(device_id)
    if device is None:
        return {"error": "Thiết bị không tồn tại"}
    bridge = phone_calls.get(device["address"])
    if bridge is None:
        return {"error": "Máy này chưa mở đường tiếng"}

    return await bridge.probe(freq=req.freq, burst_ms=req.burst_ms, amp=req.amp)
