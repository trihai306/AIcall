"""Kho câu đệm: đọc, xác thực, và tính vân tay.

KHÔNG import torch (dù gián tiếp). Module này phải chạy được trên máy không
GPU để test - `backend.core.device` import torch ở tầng module, nên mọi thứ
chạm `tts_service` đều kéo theo nó.
"""
import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


class LoiKho(ValueError):
    """Dữ liệu kho câu đệm sai. Nêu rõ câu nào sai để còn sửa được file."""


@dataclass(frozen=True)
class ChuDe:
    id: str
    ten: str
    tu_khoa: tuple[str, ...]


@dataclass(frozen=True)
class CauDem:
    id: str
    text: str
    chu_de: str
    hop_cau_hoi: bool


@dataclass(frozen=True)
class Kho:
    chu_de: tuple[ChuDe, ...]
    cau: tuple[CauDem, ...]


# Tăng khi CÁCH sinh tiếng đổi mà tham số trong vân tay thì không đổi.
#   1 -> 2 : ép thời lượng theo âm tiết (2026-08-09)
#   2 -> 3 : bỏ dấu chấm/phẩy khỏi chữ đưa vào F5 (2026-08-09)
#   3 -> 4 : hạ HE_SO_BU_LANG 1.11 -> 0.85 (2026-08-12) - câu đệm cũ đọc chậm
#            hơn câu trả lời mới, nối vào nhau là nghe rõ hai nhịp
PHIEN_BAN = 4


def van_tay(text: str, giong: str, nfe: int, speed: float, ref_text: str) -> str:
    """Vân tay của MỘT bản tiếng câu đệm.

    Thiếu cái này là bẫy im lặng: đổi `nfe` hay `speed` trong cài đặt thì câu
    trả lời thật đọc theo tham số mới, còn câu đệm vẫn là tiếng cũ trên đĩa ->
    khách nghe hai chất giọng nối liền nhau ngay đầu mỗi lượt. Không có gì báo
    lỗi, log vẫn sạch.

    `speed` ép về chuỗi 3 số lẻ để 1.0 và 1.000 ra cùng một vân tay.

    `PHIEN_BAN` để buộc dựng lại khi CÁCH sinh tiếng đổi mà tham số thì không:
    2026-08-09 thêm ép thời lượng theo âm tiết (`thoi_luong_ep`), cùng text +
    giọng + nfe + speed + ref_text nhưng tiếng ra khác hẳn. Không tăng số này
    thì câu đệm cũ nằm nguyên trên đĩa và khách nghe hai nhịp đọc khác nhau nối
    liền nhau ngay đầu mỗi lượt - đúng cái bẫy im lặng mô tả ở trên.
    """
    mau = json.dumps([PHIEN_BAN, text, giong, nfe, f"{speed:.3f}", ref_text],
                     ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(mau.encode("utf-8")).hexdigest()[:12]


def nap(duong_dan: Path) -> Kho:
    """Đọc và xác thực `fillers.json`. Ném `LoiKho` nếu dữ liệu sai."""
    try:
        raw = json.loads(Path(duong_dan).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise LoiKho(f"không đọc được kho câu đệm {duong_dan}: {e}") from e

    chu_de = tuple(
        ChuDe(id=c["id"], ten=c.get("ten", c["id"]),
              tu_khoa=tuple(c.get("tu_khoa", [])))
        for c in raw.get("chu_de", [])
    )
    ten_chu_de = {c.id for c in chu_de}

    cau: list[CauDem] = []
    da_thay: set[str] = set()
    for c in raw.get("cau", []):
        cid = c["id"]
        if cid in da_thay:
            raise LoiKho(f"id câu đệm trùng: {cid!r}")
        da_thay.add(cid)
        text = (c.get("text") or "").strip()
        if not text:
            raise LoiKho(f"câu đệm {cid!r} có text rỗng")
        if c["chu_de"] not in ten_chu_de:
            raise LoiKho(f"câu đệm {cid!r} không có chủ đề {c['chu_de']!r}")
        cau.append(CauDem(id=cid, text=text, chu_de=c["chu_de"],
                          hop_cau_hoi=bool(c.get("hop_cau_hoi", True))))

    return Kho(chu_de=chu_de, cau=tuple(cau))


DUONG_DAN_MAC_DINH = Path("data/fillers.json")

_kho: Kho | None = None


def lay_kho() -> Kho:
    """Kho câu đệm dùng chung, nạp một lần.

    Singleton như `settings`: nạp file ở mỗi lượt gọi là đọc đĩa trên đường
    găng của cuộc gọi, mà nội dung thì chỉ đổi khi người dùng sửa file.
    """
    global _kho
    if _kho is None:
        _kho = nap(DUONG_DAN_MAC_DINH)
        logger.info("Đã nạp kho câu đệm: %d câu, %d chủ đề",
                    len(_kho.cau), len(_kho.chu_de))
    return _kho


def nap_lai() -> Kho:
    """Quên bản đang nhớ và đọc lại từ đĩa (dùng sau khi sửa file)."""
    global _kho
    _kho = None
    return lay_kho()
