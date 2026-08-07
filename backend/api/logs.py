"""Đọc log của máy chủ cho trang Logs.

Trang Logs trong giao diện trước đây là VỎ RỖNG: chỉ có `clearLogs()` xoá nội
dung, không có gì đổ dữ liệu vào, và không có endpoint nào để lấy. Nó hiển thị
"Đang chờ kết nối server..." mãi mãi. Người dùng báo "log cứ chuyển menu là mất"
- thật ra nó chưa bao giờ có gì để mất.

Đọc từ CUỐI tệp lên chứ không nạp cả tệp: `train_giong_giong_nam.log` đã 260 KB
và còn tăng, nạp hết vào bộ nhớ rồi cắt lấy 200 dòng cuối là phí.
"""

import logging
import os
from pathlib import Path

from fastapi import APIRouter

from backend.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/logs", tags=["logs"])

LOG_DIR = settings.project_dir / "logs"

# Chỉ cho đọc những tệp này. KHÔNG nhận đường dẫn tuỳ ý từ client: tham số tên
# tệp đi thẳng vào filesystem là lỗ đọc trộm tệp bất kỳ trên máy (../../.env).
TEP = {
    "backend": "backend.log",
    "whisper": "pho-server.log",
    "ollama": "ollama.log",
    "train_llm": "train_lora_moi.log",
    "train_giong": "train_f5.log",
}


def _doc_cuoi(p: Path, so_dong: int) -> list[str]:
    """Đọc `so_dong` dòng cuối mà không nạp cả tệp."""
    if not p.exists():
        return []
    khoi = 64 * 1024
    with p.open("rb") as f:
        f.seek(0, os.SEEK_END)
        cuoi = f.tell()
        doc = min(khoi * max(1, so_dong // 200 + 1), cuoi)
        f.seek(cuoi - doc)
        raw = f.read(doc)
    # errors="replace": log có tiếng Việt và cả byte thô từ tiến trình con; hỏng
    # một ký tự không được phép làm cả trang Logs trắng.
    dong = raw.decode("utf-8", errors="replace").splitlines()
    # Bỏ dòng đầu vì gần như chắc chắn bị cắt giữa chừng khi seek.
    if doc < cuoi and dong:
        dong = dong[1:]
    return dong[-so_dong:]


@router.get("")
async def doc_log(ten: str = "backend", so_dong: int = 300):
    if ten not in TEP:
        return {"error": f"Không có log '{ten}'", "co_the_chon": sorted(TEP)}
    so_dong = max(20, min(so_dong, 2000))
    p = LOG_DIR / TEP[ten]
    dong = _doc_cuoi(p, so_dong)
    return {
        "ten": ten,
        "tep": TEP[ten],
        "co_tep": p.exists(),
        "kich_thuoc": p.stat().st_size if p.exists() else 0,
        "so_dong": len(dong),
        "dong": dong,
        "danh_sach": sorted(TEP),
    }
