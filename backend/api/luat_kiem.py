"""Luật kiểm chứng: bảng thuộc tính sửa được trên trang quản lý.

Bảng này là thứ lưới chặn bịa dùng để biết "lãi suất", "hạn mức"... nhận đơn vị
nào và nhận ra bằng từ khoá nào. Bản gốc nằm trong code
(`pipeline/thuoc_tinh.THUOC_TINH_MAC_DINH`) và được gieo vào DB lần đầu, nên
người dùng sửa hỏng vẫn có nút khôi phục.

Đi qua `models/luat_kiem_db` chứ không đụng SQLite thẳng - cùng lối với
`scenarios_db`, để dùng chung kết nối và khoá ghi của `models/db.py`.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from backend.models import luat_kiem_db

router = APIRouter(prefix="/api/luat-kiem", tags=["luat-kiem"])


class SuaThuocTinh(BaseModel):
    ten: str
    tu_khoa: list[str] | None = None
    don_vi: list[str] | None = None
    bat: bool | None = None


@router.get("/thuoc-tinh")
async def danh_sach():
    """Các thuộc tính ĐANG BẬT. Tắt một cái thì nó biến khỏi danh sách này."""
    bang = await luat_kiem_db.doc_bang()
    return {"thuoc_tinh": [
        {"ten": ten, "tu_khoa": list(d["khoa"]), "don_vi": list(d["dvi"]), "bat": True}
        for ten, d in sorted(bang.items())]}


@router.post("/thuoc-tinh")
async def sua_thuoc_tinh(req: SuaThuocTinh):
    """Sửa một thuộc tính. Tên không có thì BÁO LỖI chứ không im lặng bỏ qua."""
    ok = await luat_kiem_db.sua(req.ten, req.tu_khoa, req.don_vi, req.bat)
    return {"ok": True} if ok else {"error": f"Không có thuộc tính {req.ten!r}"}


@router.post("/thuoc-tinh/khoi-phuc")
async def khoi_phuc_mac_dinh():
    """Xoá sạch rồi gieo lại bản gốc trong code."""
    return {"ok": True, "da_gieo": await luat_kiem_db.khoi_phuc()}
