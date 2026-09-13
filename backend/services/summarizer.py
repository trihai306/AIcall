"""Tổng hợp ý chính từng cuộc gọi (Điều 6: "tổng hợp ý chính của từng cuộc gọi").

CHẠY SAU KHI CUỘC GỌI KẾT THÚC, không chạy trong lúc gọi. Tóm tắt không cần
thời gian thực, còn GPU lúc đó đang phục vụ cuộc gọi tiếp theo — chen vào giữa
là tự làm chậm chính sản phẩm.

Xếp hàng và chạy TUẦN TỰ một việc một lúc: chiến dịch nhiều máy kết thúc nhiều
cuộc gần như đồng thời, thả hết vào Ollama cùng lúc thì hàng đợi của nó phình
ra và cuộc gọi đang sống phải chờ sau chúng.

Dùng lại đúng model Ollama đã có, không thêm phụ thuộc — giữ ràng buộc "chạy
offline 100%" của hợp đồng.
"""

import asyncio
import json
import logging
import re

from backend.models import db, reports_db

logger = logging.getLogger(__name__)

# Nhãn LLM được phép đề xuất. Nó chỉ ĐỀ XUẤT: nhãn chính thức do người dùng bấm.
# Để mô hình tự gán nhãn cuối thì người bán hàng lọc "quan tâm" ra một danh sách
# có lẫn khách đã từ chối, và họ sẽ thôi tin cả cột nhãn.
NHAN_HOP_LE = ("quan_tam", "khong_quan_tam", "follow")
PHAN_HOI_HOP_LE = ("tich_cuc", "trung_tinh", "tu_choi")

# Tên tổ chức là dữ kiện định danh, sai một chữ cũng làm báo cáo mất tin cậy.
# Prompt không đủ giữ qwen khỏi tự đổi "Ngân hàng Quân đội" thành "VCB", nên
# kiểm chứng đầu ra theo chính bản ghi. Alias cùng một tổ chức được coi là một
# nhóm; alias thuộc nhóm khác sẽ được thay bằng tên xuất hiện thật trong cuộc.
_NHOM_TO_CHUC = {
    "mb": ("Ngân hàng Quân đội", "MBBank", "MB Bank", "MB"),
    "vcb": ("Ngân hàng Ngoại thương", "Vietcombank", "VCB"),
    "bidv": ("Ngân hàng Đầu tư và Phát triển", "BIDV"),
    "vietinbank": ("Ngân hàng Công Thương", "VietinBank"),
    "techcombank": ("Techcombank", "TCB"),
    "vpbank": ("VPBank", "VPB"),
    "tpbank": ("TPBank", "TPB"),
    "acb": ("ACB",),
    "vib": ("VIB",),
    "sacombank": ("Sacombank",),
    "agribank": ("Agribank",),
    "hdbank": ("HDBank",),
    "shb": ("SHB",),
    "ocb": ("OCB",),
}

_PROMPT = """Đọc bản ghi cuộc gọi tư vấn dưới đây và tóm tắt.

CHỈ TRẢ VỀ JSON, không thêm lời dẫn, không dùng markdown:
{{
  "tom_tat": "2-3 câu kể lại cuộc gọi",
  "nhu_cau": "sản phẩm hoặc nhu cầu khách nói ra, để trống nếu không có",
  "phan_hoi": "tich_cuc hoặc trung_tinh hoặc tu_choi",
  "ly_do_tu_choi": "lý do khách từ chối, để trống nếu khách không từ chối",
  "can_goi_lai": true hoặc false,
  "nhan_de_xuat": "quan_tam hoặc khong_quan_tam hoặc follow"
}}

Chỉ dựa vào những gì có trong bản ghi. Không suy diễn thêm thông tin khách
không nói. Bản ghi là văn bản tự động từ đường thoại nên có thể sai chính tả.

BẢN GHI:
{ban_ghi}"""


def _doc_json(raw: str) -> dict | None:
    """Bóc JSON ra khỏi câu trả lời của mô hình.

    Mô hình hay bọc JSON trong ```json ... ``` hoặc thêm một câu dẫn phía trước
    dù đã dặn là đừng. Bắt lỗi ở đây rẻ hơn nhiều so với thử ép nó bằng prompt.
    """
    if not raw:
        return None
    text = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except ValueError:
        pass
    # Lấy khối ngoặc nhọn ngoài cùng
    dau, cuoi = text.find("{"), text.rfind("}")
    if dau == -1 or cuoi <= dau:
        return None
    try:
        data = json.loads(text[dau:cuoi + 1])
        return data if isinstance(data, dict) else None
    except ValueError:
        return None


def _lam_sach(data: dict) -> dict:
    """Ép câu trả lời về đúng khuôn, giá trị lạ thì rơi về mặc định an toàn."""
    phan_hoi = str(data.get("phan_hoi", "")).strip().lower()
    nhan = str(data.get("nhan_de_xuat", "")).strip().lower()
    return {
        "tom_tat": str(data.get("tom_tat", "")).strip(),
        "nhu_cau": str(data.get("nhu_cau", "")).strip(),
        "phan_hoi": phan_hoi if phan_hoi in PHAN_HOI_HOP_LE else "trung_tinh",
        "ly_do_tu_choi": str(data.get("ly_do_tu_choi", "")).strip(),
        "can_goi_lai": bool(data.get("can_goi_lai", False)),
        "nhan_de_xuat": nhan if nhan in NHAN_HOP_LE else "",
    }


def _dung_ban_ghi(history: list[dict]) -> str:
    dong = []
    for turn in history:
        ai = "Khách" if turn.get("role") == "user" else "Tư vấn"
        noi_dung = (turn.get("content") or "").strip()
        if noi_dung:
            dong.append(f"{ai}: {noi_dung}")
    return "\n".join(dong)


def _tim_to_chuc(text: str) -> list[tuple[str, str]]:
    """Trả về ``(nhóm, chữ xuất hiện thật)`` theo thứ tự trong văn bản."""
    ket: list[tuple[int, str, str]] = []
    for nhom, aliases in _NHOM_TO_CHUC.items():
        for alias in aliases:
            m = re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", text or "", re.I)
            if m:
                ket.append((m.start(), nhom, m.group(0)))
                break
    return [(nhom, chu) for _, nhom, chu in sorted(ket)]


def _neo_to_chuc_vao_ban_ghi(tom_tat: str, ban_ghi: str) -> tuple[str, list[str]]:
    """Sửa alias tổ chức do model tự thêm bằng tên có thật trong bản ghi.

    Trả cả danh sách alias sai để log/test nhìn thấy hàng rào đã can thiệp.
    Nếu bản ghi không hề có tổ chức nào thì xoá câu chứa tên bịa sẽ dễ làm câu
    hỏng ngữ pháp; trường hợp đó để caller dùng bản tóm tắt trích xuất an toàn.
    """
    trong_ban_ghi = _tim_to_chuc(ban_ghi)
    trong_tom_tat = _tim_to_chuc(tom_tat)
    nhom_that = {nhom for nhom, _ in trong_ban_ghi}
    sai = [chu for nhom, chu in trong_tom_tat if nhom not in nhom_that]
    if not sai:
        return tom_tat, []
    if len(nhom_that) != 1:
        return "", sai

    ten_that = trong_ban_ghi[0][1]
    da_sua = tom_tat
    for chu in sai:
        # Model hay viết cả "VCB Bank" hoặc "Ngân hàng VCB". Chỉ thay ba chữ
        # VCB sẽ tạo câu lai "Ngân hàng Quân đội Bank"; thay trọn cụm định danh
        # để đầu ra đúng nguyên văn tên có trong bản ghi.
        da_sua = re.sub(
            rf"(?<!\w)(?:Ngân hàng\s+)?{re.escape(chu)}(?:\s+Bank)?(?!\w)",
            ten_that, da_sua,
            flags=re.I,
        )
    return da_sua, sai


def _tom_tat_trich_xuat(history: list[dict]) -> str:
    """Bản dự phòng chỉ ghép chữ đã có, tuyệt đối không phát minh thực thể."""
    khach = [
        (turn.get("content") or "").strip().rstrip(".?!")
        for turn in history if turn.get("role") == "user"
        and (turn.get("content") or "").strip()
    ]
    tu_van = [
        (turn.get("content") or "").strip().rstrip(".?!")
        for turn in history if turn.get("role") == "assistant"
        and (turn.get("content") or "").strip()
    ]
    cac = []
    if khach:
        cac.append("Khách đã trao đổi: " + "; ".join(khach[-3:]) + ".")
    if tu_van:
        cac.append("Tư vấn đã trả lời: " + "; ".join(tu_van[-3:]) + ".")
    return " ".join(cac)


async def tom_tat_phien(session_id: str, llm) -> dict | None:
    """Tóm tắt một phiên đã lưu. Trả về dict đã lưu, hoặc None nếu bỏ qua."""
    phien = await db.get_session(session_id)
    if phien is None:
        return None

    ban_ghi = _dung_ban_ghi(phien.get("history") or [])
    if len(ban_ghi) < 40:
        # Cuộc gọi chưa nói được gì thì không có ý chính nào để tổng hợp, mà
        # gọi LLM cho nó thì nó sẽ bịa ra một cái.
        logger.debug(f"[tóm tắt] bỏ qua {session_id}: bản ghi quá ngắn")
        return None

    try:
        # 400 token: JSON 4-5 trường tiếng Việt dài ~350 ký tự; mặc định 100 của
        # `generate_simple` cắt cụt giữa trường thứ hai - đo được ngày 06-09-2026,
        # 326 ký tự rồi đứt ở '"nhu_cau": "các sản phẩm v'.
        raw = await llm.generate_simple(_PROMPT.format(ban_ghi=ban_ghi), num_predict=400)
    except Exception as e:
        logger.warning(f"[tóm tắt] LLM lỗi cho {session_id}: {e}")
        return None

    data = _doc_json(raw)
    if data is None:
        logger.warning(f"[tóm tắt] {session_id}: mô hình không trả JSON hợp lệ")
        return None

    sach = _lam_sach(data)
    if not sach["tom_tat"]:
        return None

    tom_tat_da_neo, to_chuc_sai = _neo_to_chuc_vao_ban_ghi(
        sach["tom_tat"], ban_ghi)
    if to_chuc_sai:
        logger.warning(
            "[tóm tắt] %s: chặn tên tổ chức không có trong bản ghi: %s",
            session_id, ", ".join(to_chuc_sai),
        )
        sach["tom_tat"] = tom_tat_da_neo or _tom_tat_trich_xuat(
            phien.get("history") or [])
        sach["da_chan_to_chuc_bia"] = to_chuc_sai

    await reports_db.save_summary(session_id, sach["tom_tat"], sach)
    logger.info(f"[tóm tắt] {session_id}: {sach['phan_hoi']} — {sach['tom_tat'][:60]}")
    return sach


class BoTomTat:
    """Hàng đợi tóm tắt, chạy tuần tự một worker."""

    def __init__(self):
        self._hang: asyncio.Queue[str] = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._llm = None
        self.da_lam = 0
        self.that_bai = 0

    def khoi_dong(self, llm):
        self._llm = llm
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._chay(), name="tom-tat")

    def xep_hang(self, session_id: str):
        """Đưa một phiên vào hàng đợi. Không chặn, không ném lỗi."""
        if self._llm is None:
            return
        try:
            self._hang.put_nowait(session_id)
        except asyncio.QueueFull:
            logger.warning("[tóm tắt] hàng đợi đầy, bỏ qua %s", session_id)

    async def _chay(self):
        while True:
            session_id = await self._hang.get()
            try:
                ket_qua = await tom_tat_phien(session_id, self._llm)
                if ket_qua:
                    self.da_lam += 1
                else:
                    self.that_bai += 1
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.that_bai += 1
                logger.warning(f"[tóm tắt] hỏng ở {session_id}: {e}")
            finally:
                self._hang.task_done()

    async def dung(self):
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        self._task = None

    def trang_thai(self) -> dict:
        return {
            "dang_cho": self._hang.qsize(),
            "da_lam": self.da_lam,
            "that_bai": self.that_bai,
            "dang_chay": self._task is not None and not self._task.done(),
        }


bo_tom_tat = BoTomTat()


async def chay_bu(llm, limit: int = 50) -> dict:
    """Tóm tắt các phiên cũ chưa có tóm tắt (ví dụ sau khi nâng cấp)."""
    ids = await reports_db.chua_tom_tat(limit)
    for session_id in ids:
        bo_tom_tat.xep_hang(session_id)
    return {"da_xep_hang": len(ids)}
