"""Kho câu đệm: đọc từ SQLite, xác thực, và tính vân tay.

KHÔNG import torch (dù gián tiếp). Module này phải chạy được trên máy không
GPU để test - `backend.core.device` import torch ở tầng module, nên mọi thứ
chạm `tts_service` đều kéo theo nó.
"""
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


# Thư mục clip câu đệm đã dựng sẵn. Đặt ở đây chứ không ở `tts_service`: trang
# quản lý cần đếm clip trên đĩa, mà import `tts_service` chỉ để lấy một đường dẫn
# là kéo cả soundfile lẫn torch theo - đúng thứ mà đầu tệp này dặn tránh.
THU_MUC_FILLER = Path("data/fillers_wav")


class LoiKho(ValueError):
    """Dữ liệu kho câu đệm sai. Nêu rõ câu nào sai để còn sửa được."""


@dataclass(frozen=True)
class TinhHuong:
    id: str
    ten: str
    vi_du: tuple[str, ...]
    tu_khoa: tuple[str, ...]
    mo_dau: tuple[str, ...]
    speed: float | None
    bat: bool


@dataclass(frozen=True)
class CauDuoi:
    id: str
    text: str
    hop_cau_hoi: bool
    bat: bool


@dataclass(frozen=True)
class Kho:
    tinh_huong: tuple[TinhHuong, ...]
    duoi: tuple[CauDuoi, ...]


# Tăng khi CÁCH sinh tiếng đổi mà tham số trong vân tay thì không đổi.
#   1 -> 2 : ép thời lượng theo âm tiết (2026-08-09)
#   2 -> 3 : bỏ dấu chấm/phẩy khỏi chữ đưa vào F5 (2026-08-09)
#   3 -> 4 : THÔI bỏ dấu câu, tức đảo lại đúng thay đổi 2->3 (2026-08-11).
#            Cùng text + giọng + nfe + speed + ref_text nhưng F5 nay nhìn thấy
#            dấu nên tiếng ra khác. Không tăng số này thì 42 tệp câu đệm cũ nằm
#            nguyên trên đĩa (log: "42 đọc từ đĩa, 0 dựng mới") còn câu trả lời
#            thật đọc theo cách mới - khách nghe hai nhịp nối liền nhau ngay đầu
#            mỗi lượt, và không có gì báo lỗi.
#   6 -> 7 : LÀM SẠCH tệp wav của đoạn mẫu `giong_heu` (2026-08-16). Vân tay
#            KHÔNG tính nội dung tệp wav - chỉ tính text/giọng/nfe/speed/ref_text
#            - nên thay clip mà không tăng số này thì câu đệm cũ nằm nguyên trên
#            đĩa với giọng THỀU THÀO cũ, nối thẳng vào câu trả lời giọng mới.
#            Khách nghe hai chất giọng liền nhau ngay đầu mỗi lượt.
PHIEN_BAN = 7


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


def _mang(s: str | None) -> tuple[str, ...]:
    if not s:
        return ()
    try:
        return tuple(str(x).strip() for x in json.loads(s) if str(x).strip())
    except json.JSONDecodeError as e:
        raise LoiKho(f"cột JSON không đọc được: {s[:60]!r}: {e}") from e


def nap_tu_db(conn) -> Kho:
    """Đọc và xác thực kho từ SQLite. Ném `LoiKho` nêu rõ mục sai.

    Chỉ lấy mục `bat = 1`: trang quản lý tắt một tình huống thì nó phải biến mất
    khỏi đường chạy ngay, không cần xoá dữ liệu.
    """
    ths: list[TinhHuong] = []
    for r in conn.execute(
            "SELECT id, ten, vi_du, tu_khoa, mo_dau, speed, bat "
            "FROM tinh_huong WHERE bat = 1 ORDER BY id"):
        id_th, ten, vi_du, tu_khoa, mo_dau, speed, bat = r
        vd = _mang(vi_du)
        if len(vd) < 2:
            raise LoiKho(
                f"tình huống {id_th!r} chỉ có {len(vd)} ví dụ, cần ít nhất 2 - "
                "một ví dụ thì điểm cosine dựa vào đúng một cách nói")
        md = _mang(mo_dau)
        for m in md:
            if not m.rstrip().endswith(","):
                raise LoiKho(
                    f"mẩu mở đầu của {id_th!r} không kết bằng dấu phẩy: {m!r} - "
                    "thiếu phẩy thì F5 hạ giọng kết câu ngay giữa lượt")
        ths.append(TinhHuong(id=id_th, ten=ten or id_th, vi_du=vd,
                             tu_khoa=_mang(tu_khoa), mo_dau=md,
                             speed=float(speed) if speed is not None else None,
                             bat=bool(bat)))

    duoi: list[CauDuoi] = []
    for r in conn.execute("SELECT id, text, hop_cau_hoi, bat FROM cau_duoi "
                          "WHERE bat = 1 ORDER BY id"):
        id_d, text, hop, bat = r
        if not (text or "").strip():
            raise LoiKho(f"câu đuôi {id_d!r} có text rỗng")
        duoi.append(CauDuoi(id=id_d, text=text.strip(),
                            hop_cau_hoi=bool(hop), bat=bool(bat)))

    if not duoi:
        # Raise cả khi bảng có dòng nhưng tất cả bat=0: tắt hết câu đuôi thì
        # khách nghe im lặng trọn quãng chờ, hỏng y hệt như bảng rỗng. Phải nổ
        # to lúc khởi động thay vì để lọt ra cuộc gọi thật mới biết.
        raise LoiKho(
            "không có câu đuôi nào đang bật - rổ đuôi là đường xuống cấp cuối "
            "cùng, rỗng nó là khách nghe im lặng trọn quãng chờ")
    return Kho(tinh_huong=tuple(ths), duoi=tuple(duoi))


def do_json_vao_db(conn, duong_dan: Path) -> int:
    """Đổ `fillers.json` vào bảng `cau_duoi` NẾU bảng đang rỗng. Trả số câu đã đổ.

    Chỉ chạy khi rỗng: gọi lại nhiều lần không được ghi đè thứ người dùng đã
    sửa trên trang quản lý. 42 câu cũ đều là câu đứng một mình nên vào rổ đuôi.
    """
    if conn.execute("SELECT 1 FROM cau_duoi LIMIT 1").fetchone():
        return 0
    raw = json.loads(Path(duong_dan).read_text(encoding="utf-8"))
    now = time.time()
    rows = [(c["id"], (c.get("text") or "").strip(),
             int(bool(c.get("hop_cau_hoi", True))), 1, now, now)
            for c in raw.get("cau", []) if (c.get("text") or "").strip()]
    conn.executemany(
        "INSERT INTO cau_duoi (id,text,hop_cau_hoi,bat,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?)", rows)
    conn.commit()
    return len(rows)


DUONG_DAN_MAC_DINH = Path("data/fillers.json")

_kho: Kho | None = None


def lay_kho() -> Kho:
    """Kho dùng chung, nạp một lần. Singleton như `settings`.

    Đổ từ `fillers.json` ở lần đầu để không mất 42 câu đang có trên đĩa.
    """
    global _kho
    if _kho is None:
        from backend.models.db import connection
        conn = connection()
        if conn is None:
            raise LoiKho("DB chưa mở - `init_db()` phải chạy trước `lay_kho()`")
        n = do_json_vao_db(conn, DUONG_DAN_MAC_DINH)
        if n:
            logger.info("Đã đổ %d câu đuôi từ %s vào DB", n, DUONG_DAN_MAC_DINH)
        _kho = nap_tu_db(conn)
        logger.info("Đã nạp kho câu đệm: %d tình huống, %d câu đuôi",
                    len(_kho.tinh_huong), len(_kho.duoi))
    return _kho


def nap_lai() -> Kho:
    """Quên bản đang nhớ và đọc lại từ DB (dùng sau khi sửa dữ liệu)."""
    global _kho
    _kho = None
    return lay_kho()
