"""Gửi báo cáo qua Telegram (Điều 6: "Gửi báo cáo qua zalo hoặc telegram").

Hợp đồng cho chọn một trong hai; chốt Telegram. Zalo cần Official Account đã
duyệt và access token phải làm mới định kỳ — thời gian duyệt OA nằm ngoài tầm
kiểm soát của bên làm, nên không đưa vào phạm vi.

Đây là NGOẠI LỆ DUY NHẤT của ràng buộc "chạy offline 100%": nó là kênh thông
báo ra ngoài, không phải phụ thuộc để suy luận. Cuộc gọi vẫn chạy đủ khi không
có mạng — mọi lỗi gửi tin đều bị nuốt tại đây.

Ba loại tin, đúng như hợp đồng mô tả:
    call_success    sau mỗi cuộc gọi thành công
    daily_summary   tổng hợp cuối ngày
    campaign_done   chiến dịch chạy xong
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime

import httpx

from backend.models import db, reports_db
from backend.services import khung_gio

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"
_TIMEOUT = 10.0

SU_KIEN = ("call_success", "daily_summary", "campaign_done")

# Thử lại mấy lần, giãn cách tăng dần. Mất mạng vài giây là chuyện thường; mất
# hẳn thì bỏ qua chứ không được giữ chân vòng chạy chiến dịch.
_SO_LAN_THU = 3
_GIAN_CACH = (1.0, 4.0, 10.0)


# --- kho kênh ----------------------------------------------------------------

def _row(r) -> dict:
    d = dict(r)
    for key in ("config", "events"):
        raw = d.get(key) or ""
        try:
            d[key] = json.loads(raw) if raw else ({} if key == "config" else [])
        except (ValueError, TypeError):
            d[key] = {} if key == "config" else []
    d["enabled"] = bool(d.get("enabled"))
    # KHÔNG trả token ra ngoài. Giao diện chỉ cần biết đã cấu hình hay chưa.
    if isinstance(d.get("config"), dict) and d["config"].get("token"):
        d["config"] = {**d["config"], "token": "***"}
    return d


def _list_sync(chi_bat: bool) -> list[dict]:
    conn = db.connection()
    if conn is None:
        return []
    clause = "WHERE enabled = 1" if chi_bat else ""
    with db.write_lock:
        rows = conn.execute(
            f"SELECT * FROM notify_channels {clause} ORDER BY created_at"
        ).fetchall()
    return [dict(r) for r in rows]      # thô, còn token — chỉ dùng nội bộ


async def list_channels(che_token: bool = True) -> list[dict]:
    rows = await asyncio.to_thread(_list_sync, False)
    return [_row(r) for r in rows] if che_token else rows


def _upsert_sync(channel_id: str, fields: dict) -> dict | None:
    conn = db.connection()
    if conn is None:
        return None
    now = time.time()
    with db.write_lock, conn:
        if channel_id:
            cu = conn.execute(
                "SELECT config FROM notify_channels WHERE channel_id = ?", (channel_id,)
            ).fetchone()
            if cu is not None and "config" in fields:
                # Giao diện gửi lại token là "***" khi người dùng không sửa nó.
                # Ghi đè bằng "***" là làm hỏng kênh đang chạy tốt.
                try:
                    cu_cfg = json.loads(cu["config"] or "{}")
                except ValueError:
                    cu_cfg = {}
                moi = fields["config"]
                if isinstance(moi, dict) and moi.get("token") in ("", "***", None):
                    moi = {**moi, "token": cu_cfg.get("token", "")}
                fields["config"] = moi
        else:
            channel_id = f"nt_{uuid.uuid4().hex[:8]}"

        data = {
            "kind": fields.get("kind", "telegram"),
            "name": fields.get("name", "Telegram"),
            "config": json.dumps(fields.get("config") or {}, ensure_ascii=False),
            "events": json.dumps(
                [e for e in (fields.get("events") or []) if e in SU_KIEN],
                ensure_ascii=False,
            ),
            "enabled": 1 if fields.get("enabled", True) else 0,
        }
        cols = ", ".join(data)
        conn.execute(
            f"INSERT INTO notify_channels (channel_id, {cols}, created_at) "
            f"VALUES (?, {', '.join('?' * len(data))}, ?) "
            f"ON CONFLICT(channel_id) DO UPDATE SET "
            + ", ".join(f"{k} = excluded.{k}" for k in data),
            (channel_id, *data.values(), now),
        )
        row = conn.execute(
            "SELECT * FROM notify_channels WHERE channel_id = ?", (channel_id,)
        ).fetchone()
    return _row(row) if row else None


async def upsert_channel(channel_id: str = "", **fields) -> dict | None:
    """Tạo hoặc sửa một kênh.

    Nhận `config={"token":..., "chat_id":...}`, HOẶC token/chat_id ở ngoài cùng.
    Gộp cả hai kiểu ở đây vì kiểu sai sẽ mất token mà không báo lỗi gì — kênh
    vẫn tạo được, chỉ là không bao giờ gửi nổi một tin nào.
    """
    goi_tat = {k: fields.pop(k) for k in ("token", "chat_id") if k in fields}
    if goi_tat:
        fields["config"] = {**(fields.get("config") or {}), **goi_tat}
    return await asyncio.to_thread(_upsert_sync, channel_id, fields)


def _delete_sync(channel_id: str) -> bool:
    conn = db.connection()
    if conn is None:
        return False
    with db.write_lock, conn:
        cur = conn.execute(
            "DELETE FROM notify_channels WHERE channel_id = ?", (channel_id,)
        )
    return cur.rowcount > 0


async def delete_channel(channel_id: str) -> bool:
    return await asyncio.to_thread(_delete_sync, channel_id)


def _ghi_ket_qua_sync(channel_id: str, loi: str):
    conn = db.connection()
    if conn is None:
        return
    with db.write_lock, conn:
        conn.execute(
            "UPDATE notify_channels SET last_error = ?, last_sent = ? WHERE channel_id = ?",
            (loi, None if loi else time.time(), channel_id),
        )


# --- gửi ---------------------------------------------------------------------

async def _gui_telegram(config: dict, text: str) -> tuple[bool, str]:
    token = (config.get("token") or "").strip()
    chat_id = str(config.get("chat_id") or "").strip()
    if not token or not chat_id:
        return False, "Thiếu token hoặc chat_id"

    url = f"{TELEGRAM_API}/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text[:4000],          # Telegram chặn ở 4096 ký tự
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    loi = ""
    for lan in range(_SO_LAN_THU):
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                res = await client.post(url, json=payload)
            if res.status_code == 200:
                return True, ""
            # 4xx là sai cấu hình (token hỏng, chat_id sai): thử lại vô ích.
            if 400 <= res.status_code < 500:
                try:
                    mo_ta = res.json().get("description", "")
                except Exception:
                    mo_ta = res.text[:200]
                return False, f"Telegram từ chối ({res.status_code}): {mo_ta}"
            loi = f"Telegram lỗi máy chủ {res.status_code}"
        except httpx.TimeoutException:
            loi = "Hết thời gian chờ khi gửi Telegram"
        except Exception as e:
            loi = f"Lỗi mạng khi gửi Telegram: {e}"

        if lan < _SO_LAN_THU - 1:
            await asyncio.sleep(_GIAN_CACH[lan])
    return False, loi


async def gui(su_kien: str, text: str) -> dict:
    """Gửi `text` tới mọi kênh đang bật có đăng ký `su_kien`.

    KHÔNG BAO GIỜ ném lỗi ra ngoài: hàm này được gọi từ giữa vòng chạy chiến
    dịch, và một cái bot Telegram cấu hình sai không được phép dừng việc gọi
    điện cho khách.
    """
    ket_qua = {"da_gui": 0, "that_bai": 0, "loi": []}
    try:
        kenh = await asyncio.to_thread(_list_sync, True)
    except Exception as e:
        logger.debug(f"[thông báo] không đọc được danh sách kênh: {e}")
        return ket_qua

    for k in kenh:
        try:
            events = json.loads(k.get("events") or "[]")
            config = json.loads(k.get("config") or "{}")
        except ValueError:
            continue
        if su_kien not in events:
            continue

        ok, loi = await _gui_telegram(config, text)
        await asyncio.to_thread(_ghi_ket_qua_sync, k["channel_id"], loi)
        if ok:
            ket_qua["da_gui"] += 1
        else:
            ket_qua["that_bai"] += 1
            ket_qua["loi"].append(f"{k['name']}: {loi}")
            logger.warning(f"[thông báo] gửi tới '{k['name']}' thất bại: {loi}")
    return ket_qua


# --- ba loại tin --------------------------------------------------------------

def _thoat(s: str) -> str:
    """Thoát ký tự HTML — tên khách có thể chứa & < >."""
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


async def bao_cuoc_goi(session, contact: dict | None = None) -> dict:
    """Tin nhắn sau một cuộc gọi thành công."""
    ten = _thoat(getattr(session, "customer_name", "") or (contact or {}).get("name", ""))
    so = _thoat(getattr(session, "phone", "") or (contact or {}).get("phone", ""))
    giay = round(time.time() - session.created_at)
    luot = sum(1 for t in session.history if t.get("role") == "user")

    dong = [
        "✅ <b>Cuộc gọi xong</b>",
        f"👤 {ten or 'Không rõ'} — {so}",
        f"⏱ {giay // 60}p{giay % 60:02d}s · {luot} lượt khách nói",
    ]

    # Tóm tắt chạy nền sau cuộc gọi nên thường CHƯA có lúc tin này gửi đi. Đọc
    # lại từ CSDL: nếu kịp thì đính kèm, không kịp thì thôi, đừng chờ.
    try:
        phien = await db.get_session(session.session_id)
        if phien and phien.get("summary"):
            dong.append(f"📝 {_thoat(phien['summary'])}")
    except Exception:
        pass

    if getattr(session, "transferred_to", ""):
        dong.append(f"📞 Đã nối máy cho: {_thoat(session.transferred_to)}")

    return await gui("call_success", "\n".join(dong))


async def bao_chien_dich_xong(campaign_id: str, tien_do: dict) -> dict:
    from backend.models import contacts_db

    campaign = await contacts_db.get_campaign(campaign_id)
    ten = _thoat((campaign or {}).get("name", campaign_id))
    thong_ke = await contacts_db.contact_stats(campaign_id)

    dong = [
        f"🏁 <b>Chiến dịch xong: {ten}</b>",
        f"📞 Đã gọi {tien_do.get('da_goi', 0)} cuộc · "
        f"nghe máy {tien_do.get('da_nghe_may', 0)} "
        f"({tien_do.get('ty_le_nghe_may', 0)}%)",
    ]
    if thong_ke.get("by_status"):
        chi_tiet = " · ".join(f"{k}: {v}" for k, v in sorted(thong_ke["by_status"].items()))
        dong.append(f"📊 {chi_tiet}")
    return await gui("campaign_done", "\n".join(dong))


async def bao_tong_hop_ngay(campaign_id: str = "") -> dict:
    """Tổng hợp cuối ngày. Chỉ tính các cuộc gọi TRONG NGÀY hôm nay."""
    tz = khung_gio.mui_gio(None)
    bay_gio = datetime.now(tz)
    dau_ngay = bay_gio.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

    loc = {"from_ts": dau_ngay, "to_ts": time.time()}
    if campaign_id:
        loc["campaign_id"] = campaign_id
    tt = await reports_db.summary(loc)

    if not tt.get("tong_cuoc"):
        return {"da_gui": 0, "that_bai": 0, "loi": [], "bo_qua": "Hôm nay chưa gọi cuộc nào"}

    phut = round(tt["tong_thoi_luong"] / 60)
    dong = [
        f"📅 <b>Tổng hợp ngày {bay_gio:%d/%m/%Y}</b>",
        f"📞 {tt['tong_cuoc']} cuộc · nghe máy {tt['nghe_may']} ({tt['ty_le_nghe_may']}%)",
        f"⏱ Tổng {phut} phút · trung bình {tt['thoi_luong_tb']:.0f}s/cuộc",
    ]

    nhan = {k: v for k, v in tt["theo_nhan"].items() if k != "chua_gan"}
    if nhan:
        dong.append("🏷 " + " · ".join(f"{k}: {v}" for k, v in sorted(nhan.items())))
    if tt["theo_chat_luong"]:
        dong.append("📊 " + " · ".join(
            f"{reports_db.NHAN_HIEN_THI.get(k, k)}: {v}"
            for k, v in sorted(tt["theo_chat_luong"].items())
        ))
    return await gui("daily_summary", "\n".join(dong))


# --- hẹn giờ tổng hợp cuối ngày ------------------------------------------------

class LichTongHop:
    """Bắn tin tổng hợp mỗi ngày một lần, vào giờ đã hẹn."""

    def __init__(self, gio: int = 18, phut: int = 0):
        self.gio, self.phut = gio, phut
        self._task: asyncio.Task | None = None
        self._ngay_da_gui = ""

    def khoi_dong(self):
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._chay(), name="tong-hop-ngay")

    async def dung(self):
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        self._task = None

    async def _chay(self):
        tz = khung_gio.mui_gio(None)
        while True:
            try:
                bay_gio = datetime.now(tz)
                hom_nay = bay_gio.strftime("%Y-%m-%d")
                qua_gio = (bay_gio.hour, bay_gio.minute) >= (self.gio, self.phut)
                if qua_gio and self._ngay_da_gui != hom_nay:
                    self._ngay_da_gui = hom_nay
                    ket_qua = await bao_tong_hop_ngay()
                    if ket_qua.get("da_gui"):
                        logger.info(f"[thông báo] đã gửi tổng hợp ngày {hom_nay}")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"[thông báo] lỗi khi gửi tổng hợp ngày: {e}")
            # Kiểm mỗi phút: rẻ, và không phải tính toán mốc ngủ qua nửa đêm.
            await asyncio.sleep(60)


lich_tong_hop = LichTongHop()
