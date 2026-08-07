"""Khung giờ chạy chiến dịch (Điều 6: "Ngày bắt đầu chạy, khung giờ chạy").

Tách riêng khỏi bộ quay số vì đây là toán về thời gian thuần tuý: không cần
điện thoại, không cần CSDL, nên kiểm thử được đầy đủ mọi trường hợp biên (qua
nửa đêm, cuối tuần, đổi múi giờ) mà không phải gọi một cuộc nào.

Định dạng khung giờ lưu trong `campaigns.call_windows`, JSON:

    [{"days": [1,2,3,4,5], "from": "08:00", "to": "11:30"},
     {"days": [1,2,3,4,5], "from": "13:30", "to": "17:00"}]

`days` theo ISO: 1 = thứ Hai ... 7 = Chủ nhật.
Danh sách rỗng nghĩa là chạy mọi lúc — không giới hạn.
"""

import json
import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

MUI_GIO_MAC_DINH = "Asia/Ho_Chi_Minh"

# Giờ hành chính Việt Nam. Dùng làm mặc định khi tạo chiến dịch mới: gọi ngoài
# giờ hành chính là cách nhanh nhất để khách chặn số.
KHUNG_MAC_DINH = [
    {"days": [1, 2, 3, 4, 5], "from": "08:00", "to": "11:30"},
    {"days": [1, 2, 3, 4, 5], "from": "13:30", "to": "17:00"},
]

_THU = {1: "thứ Hai", 2: "thứ Ba", 3: "thứ Tư", 4: "thứ Năm",
        5: "thứ Sáu", 6: "thứ Bảy", 7: "Chủ nhật"}


class Khung:
    """Một khung giờ: các thứ trong tuần + giờ mở + giờ đóng."""

    __slots__ = ("days", "start", "end")

    def __init__(self, days: set[int], start: time, end: time):
        self.days = days
        self.start = start
        self.end = end

    def mo_trong_ngay(self, d: date) -> bool:
        return d.isoweekday() in self.days

    def __repr__(self) -> str:
        thu = ", ".join(_THU[x] for x in sorted(self.days))
        return f"<Khung {self.start:%H:%M}-{self.end:%H:%M} {thu}>"


def _doc_gio(raw) -> time | None:
    """'08:30' -> time(8, 30). Trả None nếu không đọc được."""
    if isinstance(raw, str) and ":" in raw:
        gio, _, phut = raw.strip().partition(":")
        try:
            h, m = int(gio), int(phut)
        except ValueError:
            return None
        if 0 <= h <= 23 and 0 <= m <= 59:
            return time(h, m)
    return None


def doc_khung(raw: str | list | None) -> list[Khung]:
    """Đọc `campaigns.call_windows`. Dữ liệu hỏng thì trả [] (= chạy mọi lúc).

    Không ném lỗi: cột này người dùng sửa được từ giao diện, một dấu phẩy thừa
    không được phép làm chết cả bộ quay số.
    """
    if not raw:
        return []
    data = raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            logger.warning("call_windows không phải JSON hợp lệ, coi như không giới hạn")
            return []
    if not isinstance(data, list):
        return []

    khung = []
    for item in data:
        if not isinstance(item, dict):
            continue
        start = _doc_gio(item.get("from"))
        end = _doc_gio(item.get("to"))
        if start is None or end is None or start >= end:
            # start >= end nghĩa là khung rỗng hoặc vắt qua nửa đêm. Không hỗ trợ
            # vắt qua nửa đêm: telesales không gọi lúc 1 giờ sáng, và cho phép nó
            # sẽ làm mọi phép tính "khung kế tiếp" ở dưới phức tạp gấp đôi.
            continue
        days = {
            int(d) for d in (item.get("days") or [])
            if isinstance(d, (int, float)) and 1 <= int(d) <= 7
        }
        khung.append(Khung(days or {1, 2, 3, 4, 5, 6, 7}, start, end))
    return khung


def mui_gio(ten: str | None):
    try:
        return ZoneInfo(ten or MUI_GIO_MAC_DINH)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning(f"Không biết múi giờ '{ten}', dùng {MUI_GIO_MAC_DINH}")
        return ZoneInfo(MUI_GIO_MAC_DINH)


def _doc_ngay(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw.strip())
    except (ValueError, AttributeError):
        return None


def trang_thai(
    bay_gio: datetime,
    khung: list[Khung],
    start_date: str = "",
    end_date: str = "",
) -> tuple[str, datetime | None, str]:
    """Bây giờ có được gọi không, và nếu không thì tới khi nào.

    Trả về (trạng thái, mốc mở kế tiếp, lý do bằng tiếng Việt):
      "chay"      - đang trong khung, gọi được
      "cho"       - chưa tới giờ / chưa tới ngày; mốc là lúc được gọi lại
      "het_han"   - đã quá end_date; mốc là None, chiến dịch nên dừng hẳn

    `bay_gio` phải là datetime CÓ múi giờ. Ranh giới lấy nửa mở [from, to):
    đúng giờ đóng là đã hết khung.
    """
    hom_nay = bay_gio.date()

    ngay_dau = _doc_ngay(start_date)
    ngay_cuoi = _doc_ngay(end_date)

    if ngay_cuoi and hom_nay > ngay_cuoi:
        return "het_han", None, f"Chiến dịch đã kết thúc ngày {ngay_cuoi:%d/%m/%Y}"

    if ngay_dau and hom_nay < ngay_dau:
        moc = _mo_dau_ngay(ngay_dau, khung, bay_gio.tzinfo)
        return "cho", moc, f"Chưa tới ngày bắt đầu ({ngay_dau:%d/%m/%Y})"

    if not khung:
        return "chay", None, "Không giới hạn khung giờ"

    gio = bay_gio.time()
    for k in khung:
        if k.mo_trong_ngay(hom_nay) and k.start <= gio < k.end:
            return "chay", None, f"Đang trong khung {k.start:%H:%M}-{k.end:%H:%M}"

    moc = moc_mo_ke_tiep(bay_gio, khung, ngay_cuoi)
    if moc is None:
        return "het_han", None, "Không còn khung giờ nào trước ngày kết thúc"
    return "cho", moc, f"Ngoài khung giờ, mở lại lúc {_mo_ta_moc(moc)}"


def _mo_dau_ngay(d: date, khung: list[Khung], tz) -> datetime:
    """Thời điểm sớm nhất trong ngày `d` mà chiến dịch được chạy."""
    if not khung:
        return datetime.combine(d, time(0, 0), tzinfo=tz)
    mo = [k.start for k in khung if k.mo_trong_ngay(d)]
    if mo:
        return datetime.combine(d, min(mo), tzinfo=tz)
    # Ngày đó không có khung nào - tìm ngày kế tiếp có khung.
    for i in range(1, 15):
        nd = d + timedelta(days=i)
        mo = [k.start for k in khung if k.mo_trong_ngay(nd)]
        if mo:
            return datetime.combine(nd, min(mo), tzinfo=tz)
    return datetime.combine(d, time(0, 0), tzinfo=tz)


def moc_mo_ke_tiep(
    bay_gio: datetime, khung: list[Khung], ngay_cuoi: date | None = None
) -> datetime | None:
    """Lần kế tiếp khung giờ mở ra, tính từ `bay_gio`. None nếu không còn.

    Quét tối đa 14 ngày: một khung chỉ chạy vài thứ trong tuần thì trong hai
    tuần chắc chắn gặp lại, còn nếu không gặp thì cấu hình đó không bao giờ mở
    và trả None là đúng.
    """
    if not khung:
        return None

    tz = bay_gio.tzinfo
    for i in range(0, 15):
        d = bay_gio.date() + timedelta(days=i)
        if ngay_cuoi and d > ngay_cuoi:
            return None
        ung_vien = sorted(
            datetime.combine(d, k.start, tzinfo=tz)
            for k in khung if k.mo_trong_ngay(d)
        )
        for moc in ung_vien:
            if moc > bay_gio:
                return moc
    return None


def _mo_ta_moc(moc: datetime) -> str:
    return f"{moc:%H:%M} {_THU[moc.isoweekday()]} {moc:%d/%m}"


def con_bao_lau(bay_gio: datetime, moc: datetime | None) -> float:
    """Số giây phải ngủ tới `moc`, tối thiểu 1 giây, tối đa 15 phút.

    Chặn trên là cố ý: người dùng có thể sửa khung giờ hoặc bấm Dừng trong lúc
    bộ quay số đang ngủ. Ngủ thẳng 14 tiếng tới sáng mai thì nút Dừng không ăn
    thua gì cho tới sáng — cứ 15 phút dậy nhìn lại một lần thì rẻ mà luôn đúng.
    """
    if moc is None:
        return 60.0
    return max(1.0, min(900.0, (moc - bay_gio).total_seconds()))
