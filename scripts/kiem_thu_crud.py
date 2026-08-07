#!/usr/bin/env python3
"""Kiểm thử CRUD toàn bộ API bổ sung theo Điều 6 hợp đồng.

Chạy trên MÁY CHỦ ĐANG SỐNG chứ không gọi hàm trực tiếp: mục đích là bắt các lỗi
chỉ lộ ra ở tầng HTTP — pydantic ép kiểu sai, route trùng nhau, tham số truy vấn
không khớp tên, JSON trả về thiếu khoá mà giao diện đang đọc.

Tự dọn sạch dữ liệu tạo ra, kể cả khi có bài kiểm thất bại giữa chừng.

    bash scripts/start_services.sh          # hoặc chỉ cần backend
    python scripts/kiem_thu_crud.py
    python scripts/kiem_thu_crud.py --url http://192.168.1.50:8100
"""

import argparse
import io
import json
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000"
TIMEOUT = 30.0

_ket_qua: list[tuple[bool, str, str]] = []
_dong_hien_tai = ""


# --- khung kiểm thử -----------------------------------------------------------

def nhom(ten: str):
    global _dong_hien_tai
    _dong_hien_tai = ten
    print(f"\n\033[1m{ten}\033[0m")


def kiem(ten: str, dieu_kien, chi_tiet: str = ""):
    """Ghi nhận một khẳng định. `dieu_kien` có thể là bool hoặc callable."""
    try:
        ok = bool(dieu_kien() if callable(dieu_kien) else dieu_kien)
        loi = ""
    except Exception as e:
        ok, loi = False, f"{type(e).__name__}: {e}"
    _ket_qua.append((ok, f"{_dong_hien_tai} › {ten}", chi_tiet or loi))
    dau = "\033[32m  ✓\033[0m" if ok else "\033[31m  ✗\033[0m"
    them = f"  \033[90m{chi_tiet or loi}\033[0m" if (chi_tiet or loi) else ""
    print(f"{dau} {ten}{them}")
    return ok


class Api:
    def __init__(self, base: str):
        self.c = httpx.Client(base_url=base, timeout=TIMEOUT)

    def get(self, url, **kw):
        return self.c.get(url, **kw).json()

    def post(self, url, body=None, **kw):
        return self.c.post(url, json=body, **kw).json()

    def patch(self, url, body=None):
        return self.c.patch(url, json=body).json()

    def delete(self, url):
        return self.c.delete(url).json()

    def raw(self, url, **kw):
        return self.c.get(url, **kw)

    def form(self, url, data=None, files=None):
        return self.c.post(url, data=data, files=files).json()


# --- F3 kịch bản --------------------------------------------------------------

def kiem_thu_kich_ban(api: Api, don: list):
    nhom("F3 · Kịch bản (CRUD)")

    # CREATE
    r = api.post("/api/scenarios", {
        "name": "KIỂM THỬ Bảo hiểm",
        "industry": "bảo hiểm",
        "org_name": "Bảo hiểm XYZ",
        "agent_name": "Mai",
        "opening_line": "Dạ em chào anh/chị ạ.",
        "rules": "Không được hứa chắc chắn về quyền lợi chi trả.",
        "examples": [{"khach": "Phí bao nhiêu?", "tu_van": "Dạ tuỳ gói ạ."},
                     {"khach": "", "tu_van": "bỏ vì thiếu vế"}],
        "max_turns": 12,
        "transfer_number": "0987000111",
        "transfer_on": ["khach_yeu_cau", "het_luot", "SAI_TRIGGER"],
        "direction": "outbound",
    })
    kiem("tạo được", "scenario" in r, r.get("error", ""))
    if "scenario" not in r:
        return
    sid = r["scenario"]["scenario_id"]
    don.append(lambda: api.delete(f"/api/scenarios/{sid}"))

    s = r["scenario"]
    kiem("ví dụ thiếu vế bị loại", len(s["examples"]) == 1, f"{len(s['examples'])} ví dụ")
    kiem("trigger lạ bị loại", "SAI_TRIGGER" not in s["transfer_on"], str(s["transfer_on"]))
    kiem("chưa phải mặc định", s["is_default"] is False)

    # READ
    kiem("get theo id", api.get(f"/api/scenarios/{sid}")["scenario"]["name"] == "KIỂM THỬ Bảo hiểm")
    ds = api.get("/api/scenarios")
    kiem("có trong danh sách", any(x["scenario_id"] == sid for x in ds["scenarios"]))
    kiem("lọc theo hướng gọi", all(
        x["direction"] in ("inbound", "both")
        for x in api.get("/api/scenarios", params={"direction": "inbound"})["scenarios"]))

    # UPDATE
    u = api.patch(f"/api/scenarios/{sid}", {"name": "KIỂM THỬ Bảo hiểm v2", "max_turns": 0})
    kiem("sửa được tên", u["scenario"]["name"] == "KIỂM THỬ Bảo hiểm v2")
    kiem("max_turns=0 bị ép về >=1", u["scenario"]["max_turns"] >= 1, f"={u['scenario']['max_turns']}")
    kiem("trường không gửi thì giữ nguyên", u["scenario"]["org_name"] == "Bảo hiểm XYZ")

    # DEFAULT
    cu = next((x for x in ds["scenarios"] if x["is_default"] and x["scenario_id"] != sid), None)
    api.post(f"/api/scenarios/{sid}/default")
    kiem("đặt được mặc định", api.get(f"/api/scenarios/{sid}")["scenario"]["is_default"] is True)
    if cu:
        # Đặt lại mặc định cũ để không làm hỏng dữ liệu người dùng.
        don.insert(0, lambda: api.post(f"/api/scenarios/{cu['scenario_id']}/default"))

    # EXPORT / IMPORT
    xuat = api.raw(f"/api/scenarios/{sid}/export")
    kiem("xuất file JSON", xuat.status_code == 200 and "attachment" in xuat.headers.get("content-disposition", ""))
    goc = json.loads(xuat.content)
    kiem("file xuất không mang id", "scenario_id" not in goc)

    mau = api.raw("/api/scenarios/template")
    kiem("tải được form mẫu", mau.status_code == 200 and "_huong_dan" in mau.text)

    nhap = api.form("/api/scenarios/import",
                    files={"file": ("kb.json", json.dumps({**goc, "name": "KIỂM THỬ Nhập lại"}).encode(),
                                    "application/json")})
    kiem("nhập từ file", "scenario" in nhap, nhap.get("error", ""))
    if "scenario" in nhap:
        nid = nhap["scenario"]["scenario_id"]
        don.append(lambda: api.delete(f"/api/scenarios/{nid}"))
        kiem("nhập ra id MỚI (không đè bản cũ)", nid != sid)

    hong = api.form("/api/scenarios/import",
                    files={"file": ("x.json", b"{khong-phai-json", "application/json")})
    kiem("file hỏng báo lỗi rõ", "error" in hong and "JSON" in hong["error"], hong.get("error", "")[:50])

    thieu_ten = api.form("/api/scenarios/import",
                         files={"file": ("x.json", b'{"industry":"abc"}', "application/json")})
    kiem("thiếu tên bị chặn", "error" in thieu_ten, thieu_ten.get("error", "")[:40])

    # DELETE
    kiem("id không tồn tại -> báo lỗi", "error" in api.get("/api/scenarios/sc_khong_co"))
    kiem("xoá id không tồn tại -> báo lỗi", "error" in api.delete("/api/scenarios/sc_khong_co"))


# --- F4/F5 danh bạ + chiến dịch ----------------------------------------------

CSV_MAU = (
    "Họ tên,Số điện thoại,Chi nhánh,Nhóm khách,Ghi chú,Cột thừa 1,Cột thừa 2\n"
    "Nguyễn Văn A,0912000101,Hà Nội,VIP,gọi sáng,x,y\n"
    "Trần Thị B,+84 912 000 102,Đà Nẵng,Thường,,x,y\n"
    "Lê Văn C,0084912000103,Hà Nội,VIP,,x,y\n"
    ",,,,,,\n"
)


def kiem_thu_danh_ba(api: Api, don: list) -> str:
    nhom("F4/F5 · Danh bạ + Chiến dịch (CRUD)")

    cd = api.post("/api/phones/campaigns", {"name": "KIỂM THỬ chiến dịch"})
    kiem("tạo chiến dịch", "campaign" in cd, cd.get("error", ""))
    cid = cd["campaign"]["campaign_id"]
    don.append(lambda: api.delete(f"/api/phones/campaigns/{cid}"))

    # PREVIEW trước khi nhập
    xt = api.form("/api/phones/contacts/import/preview", data={"text": CSV_MAU})
    kiem("xem trước đọc đúng số dòng", xt.get("so_dong") == 3, f"{xt.get('so_dong')} dòng")
    kiem("nhận nhãn 3 cột tuỳ biến",
         xt.get("nhan_cot") == {"field1_label": "Chi nhánh", "field2_label": "Nhóm khách",
                                "field3_label": "Cột thừa 1"},
         str(xt.get("nhan_cot")))
    kiem("báo cột bị bỏ qua", xt.get("cot_bo_qua") == ["Cột thừa 2"], str(xt.get("cot_bo_qua")))

    # IMPORT
    nh = api.form("/api/phones/contacts/import", data={"text": CSV_MAU, "campaign_id": cid})
    kiem("nhập 3 số", nh.get("added") == 3, str(nh))
    kiem("có cảnh báo cột dư", "canh_bao" in nh, nh.get("canh_bao", "")[:50])

    ds = api.get("/api/phones/contacts", params={"campaign_id": cid})
    so = sorted(c["phone"] for c in ds["contacts"])
    kiem("chuẩn hoá 3 kiểu viết số", so == ["0912000101", "0912000102", "0912000103"], str(so))
    kiem("trả về nhãn cột", ds.get("field_labels", {}).get("field1_label") == "Chi nhánh")
    for c in ds["contacts"]:
        don.append(lambda i=c["contact_id"]: api.delete(f"/api/phones/contacts/{i}"))

    # Nhập LẠI: không được reset trạng thái, không nhân đôi
    ct = ds["contacts"][0]
    api.patch(f"/api/phones/contacts/{ct['contact_id']}", {"status": "refused"})
    lai = api.form("/api/phones/contacts/import", data={"text": CSV_MAU, "campaign_id": cid})
    kiem("nhập lại không tạo trùng", lai.get("added") == 0 and lai.get("updated") == 3, str(lai))
    kiem("nhập lại giữ nguyên trạng thái đã gọi",
         api.get("/api/phones/contacts", params={"campaign_id": cid, "status": "refused"})["total"] == 1)
    api.patch(f"/api/phones/contacts/{ct['contact_id']}", {"status": "pending"})

    # FILTER
    kiem("lọc theo trường tuỳ biến",
         api.get("/api/phones/contacts", params={"campaign_id": cid, "field2": "VIP"})["total"] == 2)
    kiem("lọc theo tên", api.get("/api/phones/contacts", params={"search": "Nguyễn Văn A"})["total"] >= 1)

    # UPDATE
    up = api.patch(f"/api/phones/contacts/{ct['contact_id']}", {"name": "Sửa tên", "field1": "Hải Phòng"})
    kiem("sửa contact", up["contact"]["name"] == "Sửa tên" and up["contact"]["field1"] == "Hải Phòng")
    kiem("trạng thái lạ bị chặn",
         "error" in api.patch(f"/api/phones/contacts/{ct['contact_id']}", {"status": "trang_thai_bay"}))

    # CREATE thủ công + chống trùng
    them = api.post("/api/phones/contacts", {"phone": "0912000199", "name": "Thêm tay", "campaign_id": cid})
    kiem("thêm số thủ công", "contact" in them, them.get("error", ""))
    if "contact" in them:
        don.append(lambda i=them["contact"]["contact_id"]: api.delete(f"/api/phones/contacts/{i}"))
    kiem("thêm trùng số bị chặn", "error" in api.post("/api/phones/contacts", {"phone": "0912000199"}))
    kiem("số rỗng bị chặn", "error" in api.post("/api/phones/contacts", {"phone": "   "}))

    # EXPORT
    xp = api.raw("/api/phones/contacts/export", params={"campaign_id": cid})
    kiem("xuất CSV", xp.status_code == 200 and "phone" in xp.text)
    kiem("CSV dùng đúng nhãn cột gốc", "Chi nhánh" in xp.text, xp.text.splitlines()[0][:80])

    # ATTEMPTS
    kiem("lịch sử gọi rỗng lúc đầu",
         api.get(f"/api/phones/contacts/{ct['contact_id']}/attempts")["attempts"] == [])

    # CAMPAIGN update — mọi trường B3
    cf = api.patch(f"/api/phones/campaigns/{cid}", {
        "concurrency": 3, "retry_max": 5, "retry_delay_min": 7,
        "retry_no_answer": 1, "retry_busy": 0, "retry_voicemail": 1,
        "start_date": "2026-08-01", "end_date": "2026-12-31",
        "call_windows": json.dumps([{"days": [1, 2, 3], "from": "09:00", "to": "12:00"}]),
        "on_voicemail": "continue", "detect_gender": 0, "record_calls": 0,
    })
    c = cf["campaign"]
    kiem("lưu đủ cài đặt B3",
         (c["concurrency"], c["retry_max"], c["retry_delay_min"], c["on_voicemail"],
          c["detect_gender"], c["record_calls"]) == (3, 5, 7, "continue", 0, 0),
         f"concurrency={c['concurrency']} retry_max={c['retry_max']} delay={c['retry_delay_min']}")
    kiem("lưu khung giờ", json.loads(c["call_windows"])[0]["from"] == "09:00")
    kiem("trạng thái chiến dịch lạ bị chặn",
         "error" in api.patch(f"/api/phones/campaigns/{cid}", {"status": "bay_ba"}))

    # GET campaign + progress
    g = api.get(f"/api/phones/campaigns/{cid}")
    kiem("get chiến dịch kèm số dư", g.get("san_sang", -1) >= 3, f"sẵn sàng={g.get('san_sang')}")
    pr = api.get(f"/api/phones/campaigns/{cid}/progress")
    kiem("progress khi chưa chạy", pr.get("dang_chay") is False)

    # F5 — nhập từ chiến dịch khác
    cd2 = api.post("/api/phones/campaigns", {"name": "KIỂM THỬ đích"})
    cid2 = cd2["campaign"]["campaign_id"]
    don.append(lambda: api.delete(f"/api/phones/campaigns/{cid2}"))

    ids = [c["contact_id"] for c in api.get("/api/phones/contacts", params={"campaign_id": cid})["contacts"]]
    api.patch(f"/api/phones/contacts/{ids[0]}", {"status": "busy"})
    api.patch(f"/api/phones/contacts/{ids[1]}", {"status": "no_answer"})

    kiem("nguồn = đích bị chặn",
         "error" in api.post(f"/api/phones/campaigns/{cid}/import-from", {"source_campaign_id": cid}))
    kiem("chiến dịch đích không tồn tại bị chặn",
         "error" in api.post("/api/phones/campaigns/cp_khong_co/import-from",
                             {"source_campaign_id": cid}))
    kiem("trạng thái rỗng bị chặn",
         "error" in api.post(f"/api/phones/campaigns/{cid2}/import-from",
                             {"source_campaign_id": cid, "statuses": []}))

    im = api.post(f"/api/phones/campaigns/{cid2}/import-from",
                  {"source_campaign_id": cid, "statuses": ["busy", "no_answer"]})
    kiem("chuyển đúng 2 số", im.get("imported") == 2, str(im))
    kiem("số ở đích về pending",
         all(c["status"] == "pending"
             for c in api.get("/api/phones/contacts", params={"campaign_id": cid2})["contacts"]))
    kiem("số rời khỏi chiến dịch nguồn",
         api.get("/api/phones/contacts", params={"campaign_id": cid})["total"] == 2)

    return cid


# --- F14 nhãn -----------------------------------------------------------------

def kiem_thu_nhan(api: Api, don: list):
    nhom("F14 · Nhãn (CRUD)")

    ds = api.get("/api/reports/labels")["labels"]
    kiem("có sẵn 3 nhãn theo hợp đồng",
         {"quan_tam", "khong_quan_tam", "follow"} <= {l["label_id"] for l in ds},
         str([l["label_id"] for l in ds]))

    t = api.post("/api/reports/labels", {"label_id": "kt_nhan", "name": "KIỂM THỬ", "color": "#ff0000",
                                         "sort_order": 9})
    kiem("tạo nhãn", t.get("label", {}).get("name") == "KIỂM THỬ", str(t)[:60])
    don.append(lambda: api.delete("/api/reports/labels/kt_nhan"))

    u = api.post("/api/reports/labels", {"label_id": "kt_nhan", "name": "KIỂM THỬ v2", "color": "#00ff00"})
    kiem("sửa nhãn (upsert)", u["label"]["name"] == "KIỂM THỬ v2" and u["label"]["color"] == "#00ff00")
    kiem("không nhân đôi khi upsert",
         sum(1 for l in api.get("/api/reports/labels")["labels"] if l["label_id"] == "kt_nhan") == 1)

    kiem("mã nhãn rỗng bị chặn", "error" in api.post("/api/reports/labels", {"label_id": " ", "name": "x"}))
    kiem("xoá nhãn không tồn tại -> báo lỗi", "error" in api.delete("/api/reports/labels/khong_co"))
    kiem("gắn nhãn khi chưa chọn cuộc nào -> báo lỗi",
         "error" in api.post("/api/reports/label", {"session_ids": [], "label": "quan_tam"}))
    kiem("gắn nhãn không tồn tại -> báo lỗi",
         "error" in api.post("/api/reports/label", {"session_ids": ["x"], "label": "nhan_ma"}))


# --- F15 báo cáo --------------------------------------------------------------

def gieo_phien_mau(campaign_id: str) -> list[str]:
    """Ghi thẳng vài phiên gọi mẫu vào SQLite để có dữ liệu đối chiếu bộ lọc.

    Phải ghi thẳng vì phiên gọi không có endpoint tạo — nó chỉ sinh ra từ cuộc
    gọi thật hoặc từ bộ quay số. Dùng kết nối sqlite3 riêng (WAL cho phép nhiều
    tiến trình), KHÔNG gọi `db.init_db`: hàm đó có bước dọn phiên "active" và sẽ
    đóng nhầm cuộc gọi đang chạy thật.

    Trả về danh sách session_id đã tạo, để dọn sau.
    """
    import sqlite3
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from backend.config import settings

    mau = [
        # (outcome, quality, label, gender, direction, số lượt khách, giây)
        ("done",      "co_phan_hoi",    "quan_tam",       "male",   "outbound", 3, 95),
        ("done",      "it_phan_hoi",    "khong_quan_tam", "female", "outbound", 1, 40),
        ("done",      "khong_phan_hoi", "",               "",       "inbound",  0, 50),
        ("no_answer", "khong_nghe_may", "",               "",       "outbound", 0, 2),
        ("busy",      "khong_nghe_may", "follow",         "male",   "outbound", 0, 1),
        ("voicemail", "hop_thu_thoai",  "",               "",       "outbound", 0, 22),
    ]
    now = time.time()
    ids = []
    conn = sqlite3.connect(str(settings.db_file), timeout=15)
    try:
        with conn:
            for i, (kq, cl, nhan, gt, huong, luot, giay) in enumerate(mau):
                sid = f"kt{i:02d}{int(now) % 100000}"
                ids.append(sid)
                conn.execute(
                    "INSERT INTO call_sessions (session_id, customer_name, product, voice_name,"
                    " status, turn_count, created_at, ended_at, campaign_id, phone, direction,"
                    " outcome, quality, label, gender) "
                    "VALUES (?,?,?,?,'ended',?,?,?,?,?,?,?,?,?,?)",
                    (sid, f"KIỂM THỬ khách {i}", "vay tín chấp", "default",
                     luot, now - giay, now, campaign_id, f"09120009{i:02d}", huong,
                     kq, cl, nhan, gt),
                )
                for j in range(luot):
                    conn.execute(
                        "INSERT INTO conversation_turns (session_id, turn_index, role, content,"
                        " recorded_at) VALUES (?,?,?,?,?)",
                        (sid, j * 2, "user", "cho em hỏi lãi suất bao nhiêu", now))
                    conn.execute(
                        "INSERT INTO conversation_turns (session_id, turn_index, role, content,"
                        " recorded_at) VALUES (?,?,?,?,?)",
                        (sid, j * 2 + 1, "assistant", "Dạ bên em lãi suất ưu đãi ạ", now))
    finally:
        conn.close()
    return ids


def xoa_phien_mau(api: Api, ids: list[str]):
    """Xoá hẳn phiên khỏi lịch sử.

    Phải dùng `/api/history/{id}` chứ KHÔNG phải `/api/sessions/{id}`: cái sau
    chỉ đóng phiên đang sống trong bộ nhớ và luôn trả "deleted", dòng trong CSDL
    vẫn còn nguyên.
    """
    for sid in ids:
        try:
            api.delete(f"/api/history/{sid}")
        except Exception:
            pass


def kiem_thu_bao_cao(api: Api, campaign_id: str):
    nhom("F15 · Báo cáo (đọc + lọc)")

    r = api.get("/api/reports/calls", params={"limit": 5})
    kiem("liệt kê được", "calls" in r and "total" in r, f"tổng={r.get('total')}")
    kiem("trả danh mục cho ô lọc",
         bool(r.get("outcomes")) and bool(r.get("qualities")) and bool(r.get("quality_labels")))

    tong = r["total"]
    for ten, params in [
        ("lọc thời lượng chạy", {"min_duration": 5}),
        ("lọc chiến dịch chạy", {"campaign_id": campaign_id}),
        ("lọc chỉ có ghi âm chạy", {"co_ghi_am": "true"}),
        ("tìm trong nội dung chạy", {"q": "lãi suất"}),
    ]:
        got = api.get("/api/reports/calls", params={**params, "limit": 1})
        kiem(ten, "total" in got and got["total"] <= tong, f"{got.get('total')}/{tong}")

    kiem("lọc khoảng thời gian rỗng cho 0",
         api.get("/api/reports/calls", params={"from_ts": 1, "to_ts": 2})["total"] == 0)

    tt = api.get("/api/reports/summary")
    kiem("tổng hợp đủ khoá",
         {"tong_cuoc", "ty_le_nghe_may", "theo_nhan", "theo_chat_luong", "theo_ngay"} <= set(tt),
         f"{tt.get('tong_cuoc')} cuộc")

    # --- bộ lọc phải KHỚP ĐÚNG, không chỉ "trả về ít hơn tổng" ---------------
    #
    # Cần vì: một bộ lọc hỏng đến mức LUÔN trả 0 cũng thoả điều kiện "<= tổng".
    # Gieo 6 phiên gọi có kết quả/chất lượng/nhãn/giới tính biết trước rồi đối
    # chiếu từng bộ lọc với đúng con số mong đợi.
    nhom("F15 · Báo cáo (bộ lọc khớp đúng trên dữ liệu biết trước)")
    ids = []
    try:
        ids = gieo_phien_mau(campaign_id)
    except Exception as e:
        kiem("gieo dữ liệu mẫu", False, f"{type(e).__name__}: {e}")

    if ids:
        cd = {"campaign_id": campaign_id}
        kiem("thấy đủ 6 phiên vừa gieo",
             api.get("/api/reports/calls", params={**cd, "limit": 1})["total"] == 6,
             str(api.get("/api/reports/calls", params={**cd, "limit": 1})["total"]))

        mong_doi = [
            ("outcome=done",              {"outcome": "done"}, 3),
            ("outcome=no_answer",         {"outcome": "no_answer"}, 1),
            ("outcome=voicemail",         {"outcome": "voicemail"}, 1),
            ("quality=co_phan_hoi",       {"quality": "co_phan_hoi"}, 1),
            ("quality=khong_nghe_may",    {"quality": "khong_nghe_may"}, 2),
            ("label=quan_tam",            {"label": "quan_tam"}, 1),
            ("label=follow",              {"label": "follow"}, 1),
            ("gender=male",               {"gender": "male"}, 2),
            ("gender=female",             {"gender": "female"}, 1),
            ("direction=inbound",         {"direction": "inbound"}, 1),
            ("direction=outbound",        {"direction": "outbound"}, 5),
            # Thời lượng đã gieo: 95, 40, 50, 2, 1, 22 giây
            ("thời lượng >= 45s",         {"min_duration": 45}, 2),
            ("thời lượng <= 5s",          {"max_duration": 5}, 2),
            ("thời lượng 20s-60s",        {"min_duration": 20, "max_duration": 60}, 3),
            ("tìm nội dung 'lãi suất'",   {"q": "lãi suất"}, 2),
            ("tìm nội dung không có",     {"q": "xyzzy_khong_ton_tai"}, 0),
            ("chỉ cuộc có ghi âm",        {"co_ghi_am": "true"}, 0),
            ("ghép nhiều lọc",            {"outcome": "done", "gender": "male"}, 1),
        ]
        lech = []
        for ten, params, so in mong_doi:
            thuc = api.get("/api/reports/calls", params={**cd, **params, "limit": 1})["total"]
            if thuc != so:
                lech.append(f"{ten}: được {thuc}, mong {so}")
        kiem("18 tổ hợp lọc đều khớp", not lech, "; ".join(lech) or "tất cả đúng")

        # Phân bố ở /summary phải khớp với chính bộ lọc — hai đường tính khác nhau.
        tt2 = api.get("/api/reports/summary", params=cd)
        lech2 = []
        for phan_bo, khoa in (("theo_ket_qua", "outcome"), ("theo_chat_luong", "quality"),
                              ("theo_nhan", "label")):
            for k, so in (tt2.get(phan_bo) or {}).items():
                if not k or k.startswith("chua_"):
                    continue
                thuc = api.get("/api/reports/calls", params={**cd, khoa: k, "limit": 1})["total"]
                if thuc != so:
                    lech2.append(f"{khoa}={k}: lọc {thuc} ≠ tổng hợp {so}")
        kiem("tổng hợp khớp với bộ lọc", not lech2, "; ".join(lech2) or "khớp")
        kiem("tổng các nhóm = tổng chung",
             sum((tt2.get("theo_ket_qua") or {}).values()) == tt2["tong_cuoc"] == 6,
             f"{sum((tt2.get('theo_ket_qua') or {}).values())} / {tt2['tong_cuoc']}")
        kiem("tỉ lệ nghe máy tính đúng", tt2["ty_le_nghe_may"] == 50.0,
             f"{tt2['ty_le_nghe_may']}% (3 done / 6 cuộc)")

        xp2 = api.raw("/api/reports/export", params=cd)
        kiem("CSV xuất đúng số dòng đang lọc",
             len([l for l in xp2.text.strip().splitlines() if l]) == 7, "6 dòng + 1 tiêu đề")

        xoa_phien_mau(api, ids)
        kiem("dọn phiên mẫu",
             api.get("/api/reports/calls", params={**cd, "limit": 1})["total"] == 0)
    kiem("tổng hợp theo cùng bộ lọc",
         api.get("/api/reports/summary", params={"from_ts": 1, "to_ts": 2})["tong_cuoc"] == 0)

    xp = api.raw("/api/reports/export", params={"limit": 5})
    kiem("xuất CSV", xp.status_code == 200 and "thoi_gian" in xp.text)

    kiem("chi tiết cuộc không tồn tại", "error" in api.get("/api/reports/calls/khong_co"))
    kiem("ghi âm cuộc không tồn tại", "error" in api.get("/api/reports/calls/khong_co/recording"))

    if r["calls"]:
        sid = r["calls"][0]["session_id"]
        ct = api.get(f"/api/reports/calls/{sid}")
        kiem("chi tiết có history + quality_label", "history" in ct["call"] and "quality_label" in ct["call"])
        if not ct["call"].get("recording_path"):
            kiem("cuộc không có ghi âm báo rõ", "error" in api.get(f"/api/reports/calls/{sid}/recording"))

        api.post("/api/reports/label", {"session_ids": [sid], "label": "quan_tam"})
        kiem("gắn nhãn 1 cuộc",
             api.get(f"/api/reports/calls/{sid}")["call"]["label"] == "quan_tam")
        api.post("/api/reports/label", {"session_ids": [sid], "label": ""})
        kiem("gỡ nhãn", api.get(f"/api/reports/calls/{sid}")["call"]["label"] == "")

    st = api.get("/api/reports/summarizer/status")
    kiem("trạng thái hàng đợi tóm tắt", "dang_cho" in st, str(st))
    kiem("dọn ghi âm 0 ngày bị chặn",
         "error" in api.post("/api/reports/recordings/cleanup", params={"older_than_days": 0}))
    rs = api.get("/api/reports/recordings/stats")
    kiem("thống kê ghi âm", "dung_luong_mb" in rs, f"{rs.get('so_file')} file / {rs.get('dung_luong_mb')} MB")


# --- F11 Telegram -------------------------------------------------------------

def kiem_thu_telegram(api: Api, don: list):
    nhom("F11 · Kênh Telegram (CRUD)")

    t = api.post("/api/notify/channels", {
        "name": "KIỂM THỬ bot", "token": "123456:TOKEN_KIEM_THU", "chat_id": "999",
        "events": ["call_success", "daily_summary", "SU_KIEN_LA"],
    })
    kiem("tạo kênh", "channel" in t, t.get("error", ""))
    if "channel" not in t:
        return
    kid = t["channel"]["channel_id"]
    don.append(lambda: api.delete(f"/api/notify/channels/{kid}"))

    kiem("TOKEN BỊ CHE khi trả ra API", t["channel"]["config"].get("token") == "***",
         str(t["channel"]["config"]))
    kiem("sự kiện lạ bị loại", "SU_KIEN_LA" not in t["channel"]["events"], str(t["channel"]["events"]))

    api.post("/api/notify/channels", {"channel_id": kid, "name": "KIỂM THỬ đổi tên",
                                      "token": "***", "chat_id": "999", "events": ["call_success"]})
    thu = api.post("/api/notify/test", {"channel_id": kid})
    r0 = (thu.get("ket_qua") or [{}])[0]
    kiem("sửa tên KHÔNG xoá token",
         r0.get("ok") is False and "Telegram từ chối" in (r0.get("loi") or ""),
         (r0.get("loi") or "")[:60])

    kiem("kênh khác loại bị chặn",
         "error" in api.post("/api/notify/channels", {"kind": "zalo", "name": "x"}))
    kiem("gửi thử kênh không tồn tại", "error" in api.post("/api/notify/test", {"channel_id": "nt_khong_co"}))
    kiem("xoá kênh không tồn tại", "error" in api.delete("/api/notify/channels/nt_khong_co"))

    t0 = time.time()
    api.post("/api/notify/daily-summary")
    kiem("tổng hợp ngày không treo", time.time() - t0 < 20, f"{time.time() - t0:.1f}s")


# --- F16 nguồn dữ liệu --------------------------------------------------------

def kiem_thu_nguon_du_lieu(api: Api, don: list, thu_muc):
    nhom("F16 · Nguồn dữ liệu (CRUD)")

    from openpyxl import Workbook
    f_gia = thu_muc / "kt_bang_gia.xlsx"
    wb = Workbook(); ws = wb.active
    ws.append(["Sản phẩm", "Lãi suất", "Hạn mức"])
    ws.append(["Vay tín chấp", "7.9%/năm", "500 triệu"])
    ws.append(["Vay mua nhà", "6.5%/năm", "5 tỷ"])
    wb.save(f_gia)

    f_khach = thu_muc / "kt_khach.xlsx"
    wb2 = Workbook(); ws2 = wb2.active
    ws2.append(["so_dien_thoai", "ho_ten", "du_no"])
    ws2.append(["'0912 000 501", "Khách Năm Không Một", "120 triệu"])
    ws2.append(["+84912000502", "Khách Năm Không Hai", "0"])
    wb2.save(f_khach)

    # CREATE chế độ rag
    a = api.post("/api/data-sources", {"name": "KIỂM THỬ bảng giá", "kind": "excel",
                                       "mode": "rag", "path": str(f_gia)})
    kiem("tạo nguồn rag", "source" in a, a.get("error", ""))
    aid = a["source"]["source_id"]
    don.append(lambda: api.delete(f"/api/data-sources/{aid}"))

    kiem("chế độ lookup thiếu cột khoá bị chặn",
         "error" in api.post("/api/data-sources", {"name": "x", "mode": "lookup", "path": str(f_khach)}))

    b = api.post("/api/data-sources", {"name": "KIỂM THỬ hồ sơ", "kind": "excel", "mode": "lookup",
                                       "lookup_key": "so_dien_thoai", "path": str(f_khach)})
    kiem("tạo nguồn lookup", "source" in b, b.get("error", ""))
    bid = b["source"]["source_id"]
    don.append(lambda: api.delete(f"/api/data-sources/{bid}"))

    # READ + PREVIEW
    kiem("có trong danh sách",
         {aid, bid} <= {s["source_id"] for s in api.get("/api/data-sources")["sources"]})
    xt = api.post(f"/api/data-sources/{aid}/preview")
    kiem("xem trước đọc file thật", xt.get("so_dong") == 2 and "Sản phẩm" in (xt.get("cot") or []),
         str(xt.get("cot")))
    kiem("hiện đúng câu bot sẽ đọc", "Lãi suất: 7.9%/năm" in (xt.get("vi_du_van_ban") or ""),
         (xt.get("vi_du_van_ban") or "")[:60])

    # SYNC
    sy = api.post(f"/api/data-sources/{aid}/sync")
    kiem("nạp vào kho tri thức", sy.get("so_dong") == 2, str(sy)[:80])
    sy2 = api.post(f"/api/data-sources/{aid}/sync")
    kiem("nạp lại XOÁ bản cũ (không nhân đôi)", sy2.get("da_xoa_cu", 0) > 0, f"xoá {sy2.get('da_xoa_cu')} mảnh")
    kiem("nguồn lookup không cho sync", "error" in api.post(f"/api/data-sources/{bid}/sync"))

    # LOOKUP
    for so, mong in [("0912000501", True), ("0912 000 501", True), ("+84912000501", True),
                     ("0084912000501", True), ("0912000502", True), ("0999999999", False)]:
        got = api.post(f"/api/data-sources/{bid}/lookup", {"gia_tri": so})
        kiem(f"tra '{so}'", got.get("tim_thay") is mong,
             (got.get("du_lieu") or {}).get("ho_ten", got.get("ghi_chu", "")))

    kiem("nguồn rag không cho tra khoá", "error" in api.post(f"/api/data-sources/{aid}/lookup",
                                                            {"gia_tri": "x"}))
    tat = api.post("/api/data-sources/lookup-all", {"gia_tri": "0912000501"})
    kiem("tra qua mọi nguồn", len(tat.get("ket_qua") or []) == 1, str(len(tat.get("ket_qua") or [])))
    kiem("ngữ cảnh sạch dấu nháy Excel",
         "'0912" not in (tat.get("ngu_canh") or ""), (tat.get("ngu_canh") or "")[:70])

    # UPDATE
    up = api.post("/api/data-sources", {"source_id": aid, "name": "KIỂM THỬ bảng giá v2",
                                        "kind": "excel", "mode": "rag", "path": str(f_gia)})
    kiem("sửa nguồn", up["source"]["name"] == "KIỂM THỬ bảng giá v2")

    # RÀNG BUỘC OFFLINE
    w = api.post("/api/data-sources", {"name": "KIỂM THỬ web", "kind": "csv", "mode": "rag",
                                       "path": "https://example.com/gia.csv"})
    wid = w["source"]["source_id"]
    don.append(lambda: api.delete(f"/api/data-sources/{wid}"))
    pv = api.post(f"/api/data-sources/{wid}/preview")
    kiem("CHẶN đường dẫn web", "offline" in (pv.get("error") or ""), (pv.get("error") or "")[:60])

    kh = api.post("/api/data-sources", {"name": "KIỂM THỬ thiếu file", "kind": "excel",
                                        "mode": "rag", "path": "/khong/co/that.xlsx"})
    khid = kh["source"]["source_id"]
    don.append(lambda: api.delete(f"/api/data-sources/{khid}"))
    kiem("file không tồn tại báo rõ",
         "Không tìm thấy" in (api.post(f"/api/data-sources/{khid}/preview").get("error") or ""))

    kiem("xoá nguồn không tồn tại", "error" in api.delete("/api/data-sources/ds_khong_co"))


# --- F17 nhận cuộc gọi vào ----------------------------------------------------

def kiem_thu_duong_goi(api: Api, don: list):
    """Mọi đường gọi phải cho ra phiên GẮN ĐỦ nguồn gốc.

    Đây là chỗ từng hổng nặng nhất: chỉ bộ quay số tự động gắn số điện thoại,
    kịch bản, hồ sơ khách; còn nút "Gọi" tay và nút bật đường tiếng thì đẻ ra
    phiên trống — gọi xong không có bản ghi âm lẫn dòng nào tra được trong
    Báo cáo.
    """
    nhom("Đường gọi · phiên phải gắn đủ nguồn gốc")

    cd = api.post("/api/phones/campaigns", {"name": "KIỂM THỬ đường gọi"})
    cid = cd["campaign"]["campaign_id"]
    don.append(lambda: api.delete(f"/api/phones/campaigns/{cid}"))

    sc = api.post("/api/scenarios", {"name": "KIỂM THỬ kịch bản gọi", "org_name": "ABC",
                                     "agent_name": "Lan", "direction": "outbound"})
    sid = sc["scenario"]["scenario_id"]
    don.append(lambda: api.delete(f"/api/scenarios/{sid}"))
    api.patch(f"/api/phones/campaigns/{cid}", {"scenario_id": sid})

    ct = api.post("/api/phones/contacts", {"phone": "0912000701", "name": "Khách đường gọi",
                                           "campaign_id": cid, "product": "vay tín chấp",
                                           "field1": "Hà Nội"})
    ctid = ct["contact"]["contact_id"]
    don.append(lambda: api.delete(f"/api/phones/contacts/{ctid}"))

    dev = api.post("/api/devices", {"name": "KIỂM THỬ máy gọi", "kind": "phone_link",
                                    "address": "127.0.0.1:9", "dial_url": ""})
    did = dev["device"]["device_id"]
    don.append(lambda: api.delete(f"/api/devices/{did}"))

    # --- đường 2: bấm nút "Gọi" ở trang Danh bạ -----------------------------
    goi = api.post(f"/api/phones/contacts/{ctid}/call", {"device_id": did})
    kiem("gọi tay mở được phiên", bool(goi.get("session_id")), goi.get("detail", "")[:50])
    if not goi.get("session_id"):
        return
    ses = goi["session_id"]

    p = api.get(f"/api/sessions/{ses}")["session"]
    thieu = [k for k, v in (("phone", "0912000701"), ("contact_id", ctid),
                            ("campaign_id", cid), ("scenario_id", sid),
                            ("direction", "outbound")) if p.get(k) != v]
    kiem("phiên gọi tay GẮN ĐỦ số/khách/chiến dịch/kịch bản", not thieu,
         "thiếu: " + ", ".join(thieu) if thieu else
         f"phone={p.get('phone')} kịch bản={p.get('scenario_id')}")

    # --- chốt cuộc gọi: phải vào được Báo cáo -------------------------------
    kq = api.post(f"/api/phones/contacts/{ctid}/result", {"status": "done", "note": "kiểm thử"})
    kiem("chốt cuộc gọi trả về kết quả báo cáo", bool(kq.get("bao_cao")), str(kq.get("bao_cao")))

    bc = api.get("/api/reports/calls", params={"campaign_id": cid, "limit": 5})
    dong = next((c for c in bc.get("calls", []) if c["session_id"] == ses), None)
    kiem("cuộc gọi tay HIỆN trong Báo cáo", dong is not None, f"{bc.get('total')} dòng")
    if dong:
        kiem("có kết quả + chất lượng", bool(dong.get("outcome")) and bool(dong.get("quality")),
             f"{dong.get('outcome')} / {dong.get('quality_label')}")
        kiem("giữ số điện thoại để lọc", dong.get("phone") == "0912000701", str(dong.get("phone")))
        kiem("lọc theo số ra đúng cuộc",
             api.get("/api/reports/calls", params={"q": "0912000701"})["total"] >= 1)

    # --- gọi tay có áp chính sách gọi lại của chiến dịch không ---------------
    api.patch(f"/api/phones/campaigns/{cid}", {"retry_busy": 1, "retry_max": 3,
                                               "retry_delay_min": 30})
    api.post(f"/api/phones/contacts/{ctid}/call", {"device_id": did})
    api.post(f"/api/phones/contacts/{ctid}/result", {"status": "busy"})
    sau = api.get("/api/phones/contacts", params={"campaign_id": cid})["contacts"][0]
    kiem("bấm 'Máy bận' bằng tay cũng được xếp lịch gọi lại",
         sau.get("next_retry_at") and sau.get("status") == "pending",
         f"status={sau.get('status')} retry_reason={sau.get('retry_reason')}")

    # dọn các phiên vừa tạo
    for c in api.get("/api/reports/calls", params={"campaign_id": cid, "limit": 20}).get("calls", []):
        api.delete(f"/api/history/{c['session_id']}")

    # --- đường 3: bật đường tiếng ở trang Thiết bị --------------------------
    vs = api.post(f"/api/devices/{did}/voice/start", {"phone": "0912000701"})
    kiem("máy không phải ADB bị từ chối mở đường tiếng", "error" in vs,
         (vs.get("error") or "")[:60])


def kiem_thu_goi_vao(api: Api, don: list):
    nhom("F17 · Nhận cuộc gọi đến")

    d = api.post("/api/devices", {"name": "KIỂM THỬ máy", "kind": "phone_link",
                                  "address": "127.0.0.1:9", "dial_url": ""})
    kiem("tạo thiết bị", "device" in d, d.get("error", ""))
    did = d["device"]["device_id"]
    don.append(lambda: api.delete(f"/api/devices/{did}"))

    r = api.post(f"/api/devices/{did}/inbound/enable")
    kiem("máy không phải ADB bị từ chối", "error" in r, (r.get("error") or "")[:60])

    kiem("bật cho máy không tồn tại", "error" in api.post("/api/devices/dev_khong_co/inbound/enable"))
    kiem("tắt máy chưa bật", "error" in api.post(f"/api/devices/{did}/inbound/disable"))
    kiem("đọc được trạng thái", "devices" in api.get("/api/devices/inbound/status"))


# --- chạy --------------------------------------------------------------------

def _ep_utf8():
    """Ép đầu ra sang UTF-8.

    Console Windows mặc định là cp1252, không mã hoá nổi tiếng Việt — script
    chết ngay ở dòng tiêu đề với UnicodeEncodeError trước khi chạy bài nào. Mà
    máy Windows lại chính là chỗ cần chạy bộ kiểm này nhất.
    """
    for luong in (sys.stdout, sys.stderr):
        try:
            if (luong.encoding or "").lower().replace("-", "") != "utf8":
                luong.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main() -> int:
    _ep_utf8()
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=BASE)
    args = ap.parse_args()

    api = Api(args.url)
    try:
        h = api.raw("/api/health")
        if h.status_code != 200:
            print(f"Máy chủ ở {args.url} không trả lời (HTTP {h.status_code})")
            return 1
    except Exception as e:
        print(f"Không kết nối được {args.url}: {e}")
        print("Chạy trước: bash scripts/start_services.sh")
        return 1

    print(f"\033[1mKIỂM THỬ CRUD — {args.url}\033[0m")

    import tempfile
    from pathlib import Path
    thu_muc = Path(tempfile.mkdtemp(prefix="kt_crud_"))
    don: list = []

    try:
        kiem_thu_kich_ban(api, don)
        cid = kiem_thu_danh_ba(api, don)
        kiem_thu_nhan(api, don)
        kiem_thu_bao_cao(api, cid)
        kiem_thu_telegram(api, don)
        kiem_thu_nguon_du_lieu(api, don, thu_muc)
        kiem_thu_duong_goi(api, don)
        kiem_thu_goi_vao(api, don)
    finally:
        # Dọn theo thứ tự ngược: contact trước campaign, để không vướng khoá ngoại.
        nhom("Dọn dữ liệu kiểm thử")
        hong = 0
        for viec in reversed(don):
            try:
                viec()
            except Exception:
                hong += 1
        kiem("dọn sạch", hong == 0, f"{len(don)} mục, {hong} lỗi")
        import shutil
        shutil.rmtree(thu_muc, ignore_errors=True)

    sai = [t for ok, t, _ in _ket_qua if not ok]
    print(f"\n{'=' * 62}")
    print(f"\033[1mTỔNG: {len(_ket_qua) - len(sai)}/{len(_ket_qua)} ĐẠT\033[0m")
    if sai:
        print("\033[31m\nCÁC MỤC SAI:\033[0m")
        for t in sai:
            print(f"  • {t}")
    print("=" * 62)
    return 1 if sai else 0


if __name__ == "__main__":
    sys.exit(main())
