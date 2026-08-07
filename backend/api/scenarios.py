"""REST API for call scenarios (kịch bản).

Điều 6 của hợp đồng: "B1: Chọn kịch bản" và "Có thể train kịch bản đầu vào,
thống nhất 1 form train => dễ mở rộng sang các ngành khác". Cái form thống nhất
đó là JSON trả về bởi `/template`, nhận lại bởi `/import`.
"""

import json
import logging

from fastapi import APIRouter, File, Response, UploadFile
from pydantic import BaseModel

from backend.models import scenarios_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])


class Example(BaseModel):
    khach: str = ""
    tu_van: str = ""


class ScenarioRequest(BaseModel):
    name: str = "Kịch bản mới"
    industry: str = ""
    org_name: str = ""
    agent_name: str = ""
    opening_line: str = ""
    rules: str = ""
    examples: list[Example] = []
    knowledge_tag: str = ""
    max_turns: int = 20
    transfer_number: str = ""
    transfer_on: list[str] = []
    transfer_message: str = "Dạ em xin phép nối máy cho chuyên viên ạ"
    direction: str = "outbound"
    note: str = ""


class ScenarioUpdate(BaseModel):
    name: str | None = None
    industry: str | None = None
    org_name: str | None = None
    agent_name: str | None = None
    opening_line: str | None = None
    rules: str | None = None
    examples: list[Example] | None = None
    knowledge_tag: str | None = None
    max_turns: int | None = None
    transfer_number: str | None = None
    transfer_on: list[str] | None = None
    transfer_message: str | None = None
    direction: str | None = None
    note: str | None = None


class TestRequest(BaseModel):
    cau_khach: str = "Lãi suất bao nhiêu?"
    customer_name: str = "Anh Nam"
    product: str = ""
    dung_rag: bool = True


def _payload(req: BaseModel) -> dict:
    """Pydantic model -> plain dict, with examples flattened to dicts."""
    data = req.model_dump(exclude_none=True)
    if "examples" in data:
        data["examples"] = [
            e for e in data["examples"] if e.get("khach") and e.get("tu_van")
        ]
    if "transfer_on" in data:
        data["transfer_on"] = [
            t for t in data["transfer_on"] if t in scenarios_db.TRANSFER_TRIGGERS
        ]
    return data


# --- CRUD --------------------------------------------------------------------

@router.get("")
async def list_scenarios(direction: str = ""):
    return {
        "scenarios": await scenarios_db.list_scenarios(direction or None),
        "directions": scenarios_db.DIRECTIONS,
        "transfer_triggers": scenarios_db.TRANSFER_TRIGGERS,
    }


@router.post("")
async def create_scenario(req: ScenarioRequest):
    scenario = await scenarios_db.create_scenario(**_payload(req))
    if scenario is None:
        return {"error": "Không tạo được kịch bản — database chưa sẵn sàng"}
    return {"scenario": scenario}


@router.get("/template")
async def download_template():
    """The unified train form: an empty scenario with every field commented.

    Filling this in and posting it back to /import is how a new industry gets
    added without touching code.
    """
    template = {
        "_huong_dan": {
            "name": "Tên kịch bản, hiện trong danh sách chọn của chiến dịch",
            "industry": "Ngành: ngân hàng / bảo hiểm / bất động sản / giáo dục ...",
            "org_name": "Tên tổ chức bot xưng danh",
            "agent_name": "Tên nhân viên bot tự xưng",
            "opening_line": "Câu chào đọc ngay khi khách bắt máy",
            "rules": "Luật riêng của ngành, MỖI DÒNG MỘT LUẬT. "
                     "Các luật chung (độ dài câu, cấm bịa số, cấm liệt kê) đã cố định "
                     "trong hệ thống, không cần và không sửa được ở đây.",
            "examples": "Ví dụ hỏi-đáp để mô hình học ĐỘ DÀI câu trả lời. "
                        "TUYỆT ĐỐI không đặt con số thật vào đây — mô hình sẽ chép "
                        "nguyên con số đó ra trả lời khách.",
            "knowledge_tag": "Chỉ tra tài liệu có nhãn này. Để trống là tra tất cả.",
            "max_turns": "Quá số lượt này thì chuyển tiếp sang người thật",
            "transfer_number": "Số điện thoại của chuyên viên",
            "transfer_on": list(scenarios_db.TRANSFER_TRIGGERS),
            "transfer_message": "Câu bot nói trước khi nối máy",
            "direction": list(scenarios_db.DIRECTIONS),
        },
        "name": "",
        "industry": "",
        "org_name": "",
        "agent_name": "",
        "opening_line": "",
        "rules": "",
        "examples": [{"khach": "", "tu_van": ""}],
        "knowledge_tag": "",
        "max_turns": 20,
        "transfer_number": "",
        "transfer_on": ["khach_yeu_cau", "het_luot"],
        "transfer_message": "Dạ em xin phép nối máy cho chuyên viên ạ",
        "direction": "outbound",
        "note": "",
    }
    return Response(
        content=json.dumps(template, ensure_ascii=False, indent=2).encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="mau_kich_ban.json"'},
    )


@router.get("/{scenario_id}")
async def get_scenario(scenario_id: str):
    scenario = await scenarios_db.get_scenario(scenario_id)
    if scenario is None:
        return {"error": "Kịch bản không tồn tại"}
    return {"scenario": scenario}


@router.patch("/{scenario_id}")
async def update_scenario(scenario_id: str, req: ScenarioUpdate):
    scenario = await scenarios_db.update_scenario(scenario_id, **_payload(req))
    if scenario is None:
        return {"error": "Kịch bản không tồn tại"}
    return {"scenario": scenario}


@router.delete("/{scenario_id}")
async def delete_scenario(scenario_id: str):
    """Chiến dịch đang dùng kịch bản này sẽ quay về kịch bản mặc định."""
    if not await scenarios_db.delete_scenario(scenario_id):
        return {"error": "Kịch bản không tồn tại"}
    return {"deleted": scenario_id}


@router.post("/{scenario_id}/default")
async def set_default(scenario_id: str):
    if not await scenarios_db.set_default(scenario_id):
        return {"error": "Kịch bản không tồn tại"}
    return {"scenario": await scenarios_db.get_scenario(scenario_id)}


# --- import / export ----------------------------------------------------------

@router.get("/{scenario_id}/export")
async def export_scenario(scenario_id: str):
    scenario = await scenarios_db.get_scenario(scenario_id)
    if scenario is None:
        return {"error": "Kịch bản không tồn tại"}

    # Bỏ id và mốc thời gian: file này dùng để mang sang máy khác, mang theo id
    # thì lần nhập nào cũng đè lên đúng một dòng.
    payload = {k: v for k, v in scenario.items()
               if k not in ("scenario_id", "created_at", "is_default")}
    name = scenario_id.replace("/", "_")
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="kich_ban_{name}.json"'},
    )


@router.post("/import")
async def import_scenario(file: UploadFile = File(...)):
    """Nhận file JSON theo form của /template."""
    try:
        raw = (await file.read()).decode("utf-8-sig", errors="replace")
        data = json.loads(raw)
    except ValueError as e:
        return {"error": f"File không phải JSON hợp lệ: {e}"}

    if not isinstance(data, dict):
        return {"error": "File phải chứa một đối tượng JSON, không phải danh sách"}

    data.pop("_huong_dan", None)   # phần chú thích trong file mẫu
    fields = {k: v for k, v in data.items() if k in scenarios_db.EDITABLE_FIELDS}
    if not fields.get("name"):
        return {"error": "Thiếu trường 'name' — kịch bản phải có tên"}

    scenario = await scenarios_db.create_scenario(**fields)
    if scenario is None:
        return {"error": "Không tạo được kịch bản — database chưa sẵn sàng"}
    logger.info(f"Đã nhập kịch bản: {scenario['name']}")
    return {"scenario": scenario}


# --- chạy thử -----------------------------------------------------------------

@router.post("/{scenario_id}/test")
async def test_scenario(scenario_id: str, req: TestRequest):
    """Dựng prompt từ kịch bản rồi chạy đúng một lượt, trả về cả hai.

    Trả prompt ra để soi được kịch bản đã biến thành gì trước khi đem gọi thật —
    phần lớn lỗi "bot trả lời sai" nhìn prompt là thấy ngay.
    """
    from backend.main import app_state

    scenario = await scenarios_db.get_scenario(scenario_id)
    if scenario is None:
        return {"error": "Kịch bản không tồn tại"}

    rag_context = ""
    if req.dung_rag:
        try:
            rag_context = await app_state.rag.retrieve(
                req.cau_khach, san_pham=req.product or ""
            )
        except Exception as e:
            logger.warning(f"RAG lỗi khi chạy thử kịch bản: {e}")

    prompt = app_state.llm.build_system_prompt(
        customer_name=req.customer_name,
        product=req.product,
        rag_context=rag_context,
        scenario=scenario,
    )

    tra_loi = ""
    loi = ""
    try:
        async for token in app_state.llm.stream_response(
            [{"role": "user", "content": req.cau_khach}], prompt
        ):
            tra_loi += token
    except Exception as e:
        loi = f"Không gọi được LLM: {e}"
        logger.warning(loi)

    return {
        "system_prompt": prompt,
        "cau_khach": req.cau_khach,
        "tra_loi": tra_loi.strip(),
        "rag_context": rag_context,
        "so_tu": len(tra_loi.split()),
        "error": loi or None,
    }
