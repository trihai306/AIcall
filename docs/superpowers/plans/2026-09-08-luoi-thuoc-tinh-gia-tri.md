# Lưới thuộc tính–giá trị Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chặn AI nói sai mọi con số thuộc tính sản phẩm, với bảng thuộc tính khai báo được trong DB thay vì viết cứng.

**Architecture:** Một module thuần (`backend/pipeline/thuoc_tinh.py`) trích cặp (thuộc tính, giá trị) từ câu và từ tài liệu, so khớp, trả về mô tả chỗ lệch. Nối vào đúng chỗ `chan_so_sai` đang chạy trong `streaming_pipeline`, trên từng mảnh trước khi sang TTS. Bảng `thuoc_tinh_kiem` gieo mặc định từ hằng số trong code.

**Tech Stack:** Python 3.11, SQLite (`backend/models/db.py`, migration additive tự động), pytest. Không cần GPU.

**Spec:** `docs/superpowers/specs/2026-09-08-ep-ai-bam-tai-lieu-design.md`

## Global Constraints

- **Cắt/sửa đúng mệnh đề vi phạm, KHÔNG thay cả câu.** Lưới cũ thay cả mảnh và đó là nguồn của phản hồi *"sao nó trả lời 1 kiểu"*.
- **Không ghi lời AI vào căn cứ.** Chỉ tài liệu và lời khách. `so_can_cu.py` đã đặt ranh giới này và có test canh (`test_so_khong_ghi_loi_ai`).
- **Ngân sách trễ: lưới này phải ~0ms.** Không gọi mạng, không GPU, không I/O trong đường sinh.
- **Chuẩn hoá số: chỉ bỏ số 0 thừa SAU dấu thập phân.** `"500".rstrip("0")` cho `"5"` — đã mắc khi viết bộ chấm.
- **Dán lại số thập phân bị tách:** `re.sub(r"(\d)\.\s+(\d)", r"\1.\2", t)`. Bản ghi lời AI có `"từ 7. 9%"`, không dán thì trích ra 9% và chặn oan.
- Chạy test trên máy Win (nơi có deps): `ssh win 'cd C:/duan/chat-ai; .venv/python.exe -m pytest <đường dẫn> -q'`

---

### Task 1: Module trích cặp thuộc tính–giá trị

**Files:**
- Create: `backend/pipeline/thuoc_tinh.py`
- Test: `tests/test_thuoc_tinh.py`

**Interfaces:**
- Produces: `THUOC_TINH_MAC_DINH: dict[str, dict]`, `chuan_so(s: str) -> str`, `cap_trong(cau: str, bang: dict) -> list[tuple[str, str, str]]`

- [ ] **Step 1: Viết test thất bại**

```python
"""Trích cặp (thuộc tính, giá trị) - nền của lưới chặn số sai chủ thể.

Vì sao không dùng embedding: đo 08-09-2026 trên 20 câu đối chứng, cosine cho câu
ĐÚNG 0,02-0,46 và câu BỊA 0,03-0,33 - hai dải chồng lấn, không ngưỡng nào tách
được. Embedding đo CÙNG CHỦ ĐỀ chứ không đo ĐÚNG/SAI: với nó "lãi suất 5%" và
"lãi suất 7.9%" gần như đồng nghĩa.
"""
from backend.pipeline.thuoc_tinh import THUOC_TINH_MAC_DINH, cap_trong, chuan_so


def test_chuan_so_khong_an_so_khong_cua_hang_tram():
    """`"500".rstrip("0")` cho `"5"` - đã mắc, làm tài liệu đọc ra 'hạn mức 5 triệu'."""
    assert chuan_so("500") == "500"
    assert chuan_so("7,9") == "7.9"
    assert chuan_so("7.90") == "7.9"


def test_trich_duoc_lai_suat():
    assert cap_trong("Lãi suất từ 7.9% một năm", THUOC_TINH_MAC_DINH) == [("lãi suất", "7.9", "%")]


def test_so_thap_phan_bi_tach_van_trich_dung():
    """Bản ghi lời AI có "từ 7. 9%" - không dán lại thì trích ra 9% và chặn oan."""
    assert cap_trong("Lãi suất từ 7. 9% một năm", THUOC_TINH_MAC_DINH) == [("lãi suất", "7.9", "%")]


def test_tu_khoa_nam_sau_so_van_nhan_ra():
    """"trên 70 tuổi" - từ khoá đứng SAU số."""
    assert cap_trong("Khách trên 70 tuổi vẫn vay được", THUOC_TINH_MAC_DINH) == [("tuổi", "70", "tuổi")]


def test_khong_co_tu_khoa_thi_khong_trich():
    assert cap_trong("Anh chờ em 5 phút nhé", THUOC_TINH_MAC_DINH) == []
```

- [ ] **Step 2: Chạy test, xác nhận đỏ**

Run: `ssh win 'cd C:/duan/chat-ai; .venv/python.exe -m pytest tests/test_thuoc_tinh.py -q'`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.pipeline.thuoc_tinh'`

- [ ] **Step 3: Viết module tối thiểu**

```python
"""Trích cặp (thuộc tính, giá trị) từ câu, để đối chiếu với tài liệu.

Bảng thuộc tính ở đây là MẶC ĐỊNH gieo vào DB lần đầu; đường chạy thật đọc bảng
`thuoc_tinh_kiem`. Giữ bản gốc trong code để mất DB vẫn còn.
"""
import re

THUOC_TINH_MAC_DINH: dict[str, dict] = {
    "lãi suất":  {"khoa": ("lãi suất", "lãi xuất"), "dvi": ("%",)},
    "hạn mức":   {"khoa": ("hạn mức", "vay tối đa", "lên đến", "tối đa"), "dvi": ("triệu", "tỷ")},
    "thời hạn":  {"khoa": ("thời hạn", "kỳ hạn", "vay trong"), "dvi": ("tháng", "năm")},
    "giải ngân": {"khoa": ("giải ngân",), "dvi": ("giờ", "ngày")},
    "tuổi":      {"khoa": ("tuổi",), "dvi": ("tuổi",)},
    "thu nhập":  {"khoa": ("thu nhập", "lương từ"), "dvi": ("triệu",)},
    "sao kê":    {"khoa": ("sao kê",), "dvi": ("tháng",)},
    "miễn lãi":  {"khoa": ("miễn lãi",), "dvi": ("ngày",)},
}

_SO = re.compile(r"(\d+(?:[.,]\d+)?)\s*(%|triệu|tỷ|tháng|năm|giờ|ngày|tuổi)", re.I)


def chuan_so(s: str) -> str:
    """Chỉ bỏ số 0 thừa SAU dấu thập phân. `"500".rstrip("0")` cho "5" - đã mắc."""
    s = s.replace(",", ".")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


def cap_trong(cau: str, bang: dict) -> list[tuple[str, str, str]]:
    """[(thuộc tính, số, đơn vị)] tìm được trong câu."""
    t = re.sub(r"(\d)\.\s+(\d)", r"\1.\2", (cau or "").lower())
    ra = []
    for m in _SO.finditer(t):
        so, dvi = chuan_so(m.group(1)), m.group(2).lower()
        # Tìm từ khoá CẢ HAI PHÍA: "trên 70 tuổi" có từ khoá nằm SAU số.
        quanh = t[max(0, m.start() - 60):min(len(t), m.end() + 25)]
        for ten, d in bang.items():
            if dvi in d["dvi"] and any(k in quanh for k in d["khoa"]):
                ra.append((ten, so, dvi))
                break
    return ra
```

- [ ] **Step 4: Chạy test, xác nhận xanh**

Run: `ssh win 'cd C:/duan/chat-ai; .venv/python.exe -m pytest tests/test_thuoc_tinh.py -q'`
Expected: PASS, 5 test

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline/thuoc_tinh.py tests/test_thuoc_tinh.py
git commit -m "feat(chan-bia): trich cap thuoc tinh - gia tri tu cau"
```

---

### Task 2: Đọc giá trị đúng từ tài liệu

**Files:**
- Modify: `backend/pipeline/thuoc_tinh.py`
- Test: `tests/test_thuoc_tinh.py`

**Interfaces:**
- Consumes: `cap_trong`, `chuan_so` từ Task 1
- Produces: `gia_tri_tai_lieu(tai_lieu: str, bang: dict) -> dict[str, set[tuple[str, str]]]`

- [ ] **Step 1: Viết test thất bại**

```python
def test_doc_gia_tri_tu_tai_lieu():
    """Giá trị đúng ĐỌC TỪ TÀI LIỆU, không viết cứng - sửa tài liệu là lưới đổi theo."""
    from backend.pipeline.thuoc_tinh import gia_tri_tai_lieu
    tl = "- Lãi suất: từ 7.9%/năm\n- Hạn mức: lên đến 500 triệu đồng\n"
    kho = gia_tri_tai_lieu(tl, THUOC_TINH_MAC_DINH)
    assert kho["lãi suất"] == {("7.9", "%")}
    assert kho["hạn mức"] == {("500", "triệu")}


def test_tai_lieu_rong_thi_kho_rong():
    from backend.pipeline.thuoc_tinh import gia_tri_tai_lieu
    assert gia_tri_tai_lieu("", THUOC_TINH_MAC_DINH) == {}
```

- [ ] **Step 2: Chạy test, xác nhận đỏ**

Run: `ssh win 'cd C:/duan/chat-ai; .venv/python.exe -m pytest tests/test_thuoc_tinh.py -q'`
Expected: FAIL — `ImportError: cannot import name 'gia_tri_tai_lieu'`

- [ ] **Step 3: Viết hàm**

```python
def gia_tri_tai_lieu(tai_lieu: str, bang: dict) -> dict[str, set[tuple[str, str]]]:
    """{thuộc tính: {(số, đơn vị)}} đọc được từ tài liệu.

    Đọc TỪNG DÒNG chứ không cả khối: từ khoá của thuộc tính này không được vơ
    lấy con số của dòng khác.
    """
    kho: dict[str, set[tuple[str, str]]] = {}
    for dong in (tai_lieu or "").splitlines():
        for ten, so, dvi in cap_trong(dong, bang):
            kho.setdefault(ten, set()).add((so, dvi))
    return kho
```

- [ ] **Step 4: Chạy test, xác nhận xanh**

Run: `ssh win 'cd C:/duan/chat-ai; .venv/python.exe -m pytest tests/test_thuoc_tinh.py -q'`
Expected: PASS, 7 test

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline/thuoc_tinh.py tests/test_thuoc_tinh.py
git commit -m "feat(chan-bia): doc gia tri dung tu tai lieu"
```

---

### Task 3: Hàm chặn — so cặp của câu với cặp của tài liệu

**Files:**
- Modify: `backend/pipeline/thuoc_tinh.py`
- Test: `tests/test_thuoc_tinh.py`

**Interfaces:**
- Consumes: `cap_trong`, `gia_tri_tai_lieu`
- Produces: `chan_thuoc_tinh_sai(text: str, tai_lieu: str, bang: dict, khach_noi: str = "") -> tuple[str, str | None]` — trả `(văn bản, mô tả chỗ lệch hoặc None)`, **cùng dạng trả về với `chan_so_sai`**

- [ ] **Step 1: Viết test thất bại**

```python
def test_gia_tri_khop_thi_cho_qua():
    from backend.pipeline.thuoc_tinh import chan_thuoc_tinh_sai
    tl = "- Lãi suất: từ 7.9%/năm\n"
    ra, sua = chan_thuoc_tinh_sai("Lãi suất từ 7.9% một năm ạ", tl, THUOC_TINH_MAC_DINH)
    assert sua is None and ra == "Lãi suất từ 7.9% một năm ạ"


def test_gia_tri_lech_thi_bao_lech():
    from backend.pipeline.thuoc_tinh import chan_thuoc_tinh_sai
    tl = "- Lãi suất: từ 7.9%/năm\n"
    _, sua = chan_thuoc_tinh_sai("Lãi suất chỉ 5% một năm ạ", tl, THUOC_TINH_MAC_DINH)
    assert sua is not None and "lãi suất" in sua and "5" in sua


def test_so_do_KHACH_neu_thi_khong_chan():
    """AI nhắc lại số của khách là ĐÚNG. Cùng ranh giới `so_can_cu` đã đặt."""
    from backend.pipeline.thuoc_tinh import cap_trong, chan_thuoc_tinh_sai
    tl = "- Hạn mức: lên đến 500 triệu đồng\n"
    # Câu thử PHẢI trích được cặp, không thì test xanh vì `cap_trong` trả rỗng
    # chứ không phải vì lưới nhận ra số đó của khách.
    assert cap_trong("Hạn mức anh cần là 400 triệu ạ", THUOC_TINH_MAC_DINH)
    _, sua = chan_thuoc_tinh_sai("Hạn mức anh cần là 400 triệu ạ", tl, THUOC_TINH_MAC_DINH,
                                 khach_noi="anh muốn vay tầm 400 triệu")
    assert sua is None


def test_ty_va_trieu_quy_doi_duoc():
    from backend.pipeline.thuoc_tinh import chan_thuoc_tinh_sai
    tl = "- Hạn mức: lên đến 10 tỷ đồng\n"
    _, sua = chan_thuoc_tinh_sai("Hạn mức lên đến 10000 triệu đồng ạ", tl, THUOC_TINH_MAC_DINH)
    assert sua is None


def test_thuoc_tinh_KHONG_CO_trong_tai_lieu_thi_khong_phan():
    """Tài liệu không nói gì về thuộc tính đó thì lưới này im - việc của lưới NLI."""
    from backend.pipeline.thuoc_tinh import chan_thuoc_tinh_sai
    _, sua = chan_thuoc_tinh_sai("Miễn lãi 45 ngày ạ", "- Lãi suất: từ 7.9%/năm\n",
                                 THUOC_TINH_MAC_DINH)
    assert sua is None


def test_van_ban_KHONG_bi_thay_ca_cau():
    """Ràng buộc lõi: lưới trả về mô tả để chỗ gọi xử lý, KHÔNG tự thay câu."""
    from backend.pipeline.thuoc_tinh import chan_thuoc_tinh_sai
    goc = "Lãi suất chỉ 5% một năm ạ"
    ra, _ = chan_thuoc_tinh_sai(goc, "- Lãi suất: từ 7.9%/năm\n", THUOC_TINH_MAC_DINH)
    assert ra == goc
```

- [ ] **Step 2: Chạy test, xác nhận đỏ**

Run: `ssh win 'cd C:/duan/chat-ai; .venv/python.exe -m pytest tests/test_thuoc_tinh.py -q'`
Expected: FAIL — `ImportError: cannot import name 'chan_thuoc_tinh_sai'`

- [ ] **Step 3: Viết hàm**

```python
def _quy_doi(so: str, dvi: str) -> list[tuple[str, str]]:
    """Các cách viết tương đương của cùng một lượng."""
    ra = [(so, dvi)]
    try:
        v = float(so)
    except ValueError:
        return ra
    if dvi == "tỷ":
        ra.append((chuan_so(str(v * 1000)), "triệu"))
    elif dvi == "triệu":
        ra.append((chuan_so(str(v / 1000)), "tỷ"))
    return ra


def chan_thuoc_tinh_sai(text: str, tai_lieu: str, bang: dict,
                        khach_noi: str = "") -> tuple[str, str | None]:
    """Con số gán cho một thuộc tính có đúng như tài liệu không?

    Trả `(văn bản nguyên vẹn, mô tả chỗ lệch hoặc None)` - CÙNG DẠNG với
    `chan_so_sai` để chỗ gọi xử lý thống nhất. Hàm này KHÔNG tự thay câu.

    Ba trường hợp im lặng, đều có chủ ý:
      - thuộc tính không có trong tài liệu -> việc của lưới NLI, không phải của đây
      - con số do chính KHÁCH nêu -> AI nhắc lại là đúng
      - không trích được cặp nào -> không có gì để phán
    """
    kho = gia_tri_tai_lieu(tai_lieu, bang)
    if not kho:
        return text, None
    so_khach = {s for s, _ in cap_trong(khach_noi, bang)} | set(
        re.findall(r"\d+(?:[.,]\d+)?", (khach_noi or "")))
    lech = []
    for ten, so, dvi in cap_trong(text, bang):
        if ten not in kho or so in so_khach:
            continue
        if any(c in kho[ten] for c in _quy_doi(so, dvi)):
            continue
        dung = ", ".join(f"{a}{b}" for a, b in sorted(kho[ten]))
        lech.append(f"{ten} {so}{dvi} (tài liệu: {dung})")
    return text, ("; ".join(lech) if lech else None)
```

- [ ] **Step 4: Chạy test, xác nhận xanh**

Run: `ssh win 'cd C:/duan/chat-ai; .venv/python.exe -m pytest tests/test_thuoc_tinh.py -q'`
Expected: PASS, 13 test

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline/thuoc_tinh.py tests/test_thuoc_tinh.py
git commit -m "feat(chan-bia): luoi thuoc tinh - gia tri, chua noi vao duong sinh"
```

---

### Task 4: Bảng `thuoc_tinh_kiem` trong DB, gieo từ mặc định

**Files:**
- Modify: `backend/models/db.py` (thêm bảng vào `_SCHEMA`, khoảng dòng 34–235)
- Create: `backend/models/luat_kiem_db.py`
- Test: `tests/test_thuoc_tinh_db.py`

**Interfaces:**
- Consumes: `THUOC_TINH_MAC_DINH`
- Produces: trong `backend/models/luat_kiem_db.py`: `doc_bang_sync(conn) -> dict[str, dict]`, `gieo_mac_dinh_sync(conn) -> int`, `async doc_bang() -> dict`, `async sua(ten, tu_khoa, don_vi, bat) -> bool`, `async khoi_phuc() -> int`

Dự án đã có tầng repository riêng cho mỗi nhóm bảng (`scenarios_db.py`,
`devices_db.py`, `contacts_db.py`) — chúng dùng chung kết nối qua
`db.connection()` và khoá ghi `db.write_lock`, không mở handle thứ hai vào cùng
file SQLite. Theo đúng pattern đó.

- [ ] **Step 1: Viết test thất bại**

```python
"""Bảng thuộc tính: sửa được trên trang quản lý, gieo mặc định từ code."""
import sqlite3

from backend.models.db import _SCHEMA
from backend.models.luat_kiem_db import doc_bang_sync, gieo_mac_dinh_sync
from backend.pipeline.thuoc_tinh import THUOC_TINH_MAC_DINH


def _conn():
    c = sqlite3.connect(":memory:")
    c.executescript(_SCHEMA)
    return c


def test_gieo_roi_doc_lai_ra_dung_bang_mac_dinh():
    c = _conn()
    gieo_mac_dinh_sync(c)
    assert doc_bang_sync(c) == THUOC_TINH_MAC_DINH


def test_gieo_hai_lan_khong_nhan_doi():
    c = _conn()
    gieo_mac_dinh_sync(c)
    gieo_mac_dinh_sync(c)
    assert len(doc_bang_sync(c)) == len(THUOC_TINH_MAC_DINH)


def test_gieo_lai_KHONG_ghi_de_ban_nguoi_dung_da_sua():
    """Sửa trên UI rồi thì lần khởi động sau không được xoá công của họ."""
    c = _conn()
    gieo_mac_dinh_sync(c)
    c.execute("UPDATE thuoc_tinh_kiem SET don_vi='[\"%\"]' WHERE ten='hạn mức'")
    gieo_mac_dinh_sync(c)
    assert doc_bang_sync(c)["hạn mức"]["dvi"] == ("%",)


def test_tat_mot_thuoc_tinh_thi_khong_doc_ra_nua():
    c = _conn()
    gieo_mac_dinh_sync(c)
    c.execute("UPDATE thuoc_tinh_kiem SET bat=0 WHERE ten='tuổi'")
    assert "tuổi" not in doc_bang_sync(c)
```

- [ ] **Step 2: Chạy test, xác nhận đỏ**

Run: `ssh win 'cd C:/duan/chat-ai; .venv/python.exe -m pytest tests/test_thuoc_tinh_db.py -q'`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.models.luat_kiem_db'`

- [ ] **Step 3: Thêm bảng và hai hàm**

Thêm vào `_SCHEMA` trong `backend/models/db.py`:

```sql
CREATE TABLE IF NOT EXISTS thuoc_tinh_kiem (
    ten      TEXT PRIMARY KEY,
    tu_khoa  TEXT NOT NULL,          -- JSON list
    don_vi   TEXT NOT NULL,          -- JSON list
    bat      INTEGER NOT NULL DEFAULT 1
);
```

Tạo `backend/models/luat_kiem_db.py`:

```python
"""Bảng luật kiểm chứng - thứ trang quản lý sửa được.

Bản gốc của bảng thuộc tính nằm ở `pipeline/thuoc_tinh.THUOC_TINH_MAC_DINH`;
ở đây chỉ gieo và cho sửa. Giữ bản gốc trong code để mất DB vẫn còn.

Dùng chung kết nối và khoá ghi của `models/db.py`, không mở handle thứ hai -
cùng lý do với `scenarios_db.py`.
"""
import asyncio
import json

from backend.models import db


def doc_bang_sync(conn) -> dict[str, dict]:
    """Bảng thuộc tính đang BẬT, đúng dạng `cap_trong` nhận."""
    import json
    ra = {}
    for ten, tu_khoa, don_vi in conn.execute(
            "SELECT ten, tu_khoa, don_vi FROM thuoc_tinh_kiem WHERE bat=1"):
        ra[ten] = {"khoa": tuple(json.loads(tu_khoa)), "dvi": tuple(json.loads(don_vi))}
    return ra


def gieo_mac_dinh_sync(conn) -> int:
    """Gieo bảng mặc định. Chạy lại được: chỉ thêm thuộc tính còn thiếu.

    KHÔNG ghi đè dòng đã có - người dùng sửa trên UI rồi thì lần khởi động sau
    không được xoá công của họ.
    """
    from backend.pipeline.thuoc_tinh import THUOC_TINH_MAC_DINH
    n = 0
    for ten, d in THUOC_TINH_MAC_DINH.items():
        cur = conn.execute(
            "INSERT OR IGNORE INTO thuoc_tinh_kiem (ten, tu_khoa, don_vi, bat) "
            "VALUES (?, ?, ?, 1)",
            (ten, json.dumps(list(d["khoa"]), ensure_ascii=False),
             json.dumps(list(d["dvi"]), ensure_ascii=False)))
        n += cur.rowcount
    conn.commit()
    return n


# --- vỏ async cho tầng API (I/O SQLite chạy ngoài vòng lặp sự kiện) ----------

async def doc_bang() -> dict[str, dict]:
    def _lam():
        c = db.connection()
        if c is None:
            return {}
        gieo_mac_dinh_sync(c)
        return doc_bang_sync(c)
    return await asyncio.to_thread(_lam)


async def sua(ten: str, tu_khoa: list[str] | None,
              don_vi: list[str] | None, bat: bool | None) -> bool:
    def _lam():
        c = db.connection()
        if c is None:
            return False
        with db.write_lock:
            cu = c.execute("SELECT tu_khoa, don_vi, bat FROM thuoc_tinh_kiem WHERE ten=?",
                           (ten,)).fetchone()
            if cu is None:
                return False
            c.execute(
                "UPDATE thuoc_tinh_kiem SET tu_khoa=?, don_vi=?, bat=? WHERE ten=?",
                (json.dumps(tu_khoa, ensure_ascii=False) if tu_khoa is not None else cu[0],
                 json.dumps(don_vi, ensure_ascii=False) if don_vi is not None else cu[1],
                 cu[2] if bat is None else int(bat), ten))
            c.commit()
        return True
    return await asyncio.to_thread(_lam)


async def khoi_phuc() -> int:
    """Xoá sạch rồi gieo lại bản gốc trong code."""
    def _lam():
        c = db.connection()
        if c is None:
            return 0
        with db.write_lock:
            c.execute("DELETE FROM thuoc_tinh_kiem")
            return gieo_mac_dinh_sync(c)
    return await asyncio.to_thread(_lam)
```

- [ ] **Step 4: Chạy test, xác nhận xanh**

Run: `ssh win 'cd C:/duan/chat-ai; .venv/python.exe -m pytest tests/test_thuoc_tinh_db.py -q'`
Expected: PASS, 4 test

- [ ] **Step 5: Commit**

```bash
git add backend/models/db.py backend/models/luat_kiem_db.py tests/test_thuoc_tinh_db.py
git commit -m "feat(chan-bia): bang thuoc_tinh_kiem, gieo tu mac dinh"
```

---

### Task 5: Nối vào đường sinh

**Files:**
- Modify: `backend/pipeline/streaming_pipeline.py:27-29` (import), `:2087` (ngay sau `chan_so_sai`)
- Test: `tests/test_thuoc_tinh_duong_sinh.py`

**Interfaces:**
- Consumes: `chan_thuoc_tinh_sai`, `luat_kiem_db.doc_bang_sync`
- Produces: khoá metrics `chan_thuoc_tinh`

- [ ] **Step 1: Viết test thất bại**

```python
"""Lưới thuộc tính phải chạy ĐÚNG CHỖ `chan_so_sai` chạy: trên từng mảnh, trước TTS.

Hai test này đọc MÃ NGUỒN chứ không gọi pipeline: dựng `StreamingPipeline` thật
đòi STT + LLM + TTS + RAG, tức cần GPU và vài giây nạp model, quá đắt cho một
test canh dây nối. Đánh đổi: chúng bắt được "quên nối" và "nối sai thứ tự",
không bắt được "nối đúng chỗ nhưng truyền sai tham số" - phần đó do
`tests/test_thuoc_tinh.py` và bước chấm lại ở Task 7 gác.
"""
import inspect

from backend.pipeline import streaming_pipeline


def test_luoi_thuoc_tinh_duoc_goi_trong_duong_sinh():
    ma = inspect.getsource(streaming_pipeline)
    assert "chan_thuoc_tinh_sai" in ma


def test_goi_SAU_chan_so_sai():
    """`chan_so_sai` sửa số đọc nhầm trước; lưới này phán trên bản đã sửa."""
    ma = inspect.getsource(streaming_pipeline)
    assert ma.index("chan_so_sai(doan") < ma.index("chan_thuoc_tinh_sai(")
```

- [ ] **Step 2: Chạy test, xác nhận đỏ**

Run: `ssh win 'cd C:/duan/chat-ai; .venv/python.exe -m pytest tests/test_thuoc_tinh_duong_sinh.py -q'`
Expected: FAIL — `AssertionError` ở test đầu

- [ ] **Step 3: Nối vào**

Thêm import cạnh các lưới khác (`backend/pipeline/streaming_pipeline.py`, cạnh dòng 14):

```python
from backend.pipeline.thuoc_tinh import chan_thuoc_tinh_sai
```

Chèn ngay SAU khối `chan_so_sai` (sau dòng ghi `metrics["chan_so_sai"] = sua`):

```python
            # Lưới THUỘC TÍNH: con số đúng vẫn có thể gán sai chủ thể. Chạy sau
            # `chan_so_sai` để phán trên bản đã sửa số đọc nhầm.
            #
            # CHỈ GHI NHẬT KÝ, chưa thay câu. Bật chặn thật sau khi nhật ký trên
            # cuộc gọi thật cho thấy chặn nhầm <= 5% - xem mục 8 của spec.
            _, sua_tt = chan_thuoc_tinh_sai(
                ra, ngu_canh, self._bang_thuoc_tinh, khach_noi=user_text)
            if sua_tt:
                logger.warning("THUỘC TÍNH LỆCH: %s | %r", sua_tt, ra[:60])
                metrics["chan_thuoc_tinh"] = sua_tt
```

Nạp bảng một lần lúc khởi tạo pipeline (cạnh các thuộc tính khác của lớp):

```python
        # Đọc MỘT LẦN lúc dựng pipeline: đường sinh không được đụng SQLite.
        try:
            from backend.models import db as _db
            from backend.models.luat_kiem_db import doc_bang_sync
            _c = _db.connection()
            if _c is None:
                raise RuntimeError("DB chưa mở")
            self._bang_thuoc_tinh = doc_bang_sync(_c)
        except Exception as e:
            from backend.pipeline.thuoc_tinh import THUOC_TINH_MAC_DINH
            logger.warning("Không đọc được bảng thuộc tính (%s) - dùng mặc định", e)
            self._bang_thuoc_tinh = THUOC_TINH_MAC_DINH
```

- [ ] **Step 4: Chạy test, xác nhận xanh**

Run: `ssh win 'cd C:/duan/chat-ai; .venv/python.exe -m pytest tests/test_thuoc_tinh_duong_sinh.py tests/ -q'`
Expected: PASS toàn bộ (1305 test cũ + test mới)

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline/streaming_pipeline.py tests/test_thuoc_tinh_duong_sinh.py
git commit -m "feat(chan-bia): noi luoi thuoc tinh vao duong sinh, che do ghi nhat ky"
```

---

### Task 6: API đọc/sửa bảng thuộc tính

**Files:**
- Create: `backend/api/luat_kiem.py`
- Modify: `backend/main.py` (đăng ký router, cạnh các `include_router` khác)
- Test: `tests/test_api_luat_kiem.py`

**Interfaces:**
- Consumes: `luat_kiem_db.doc_bang`, `luat_kiem_db.sua`, `luat_kiem_db.khoi_phuc`
- Produces: `GET /api/luat-kiem/thuoc-tinh`, `POST /api/luat-kiem/thuoc-tinh`, `POST /api/luat-kiem/thuoc-tinh/khoi-phuc`

- [ ] **Step 1: Viết test thất bại**

```python
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_doc_ra_danh_sach_thuoc_tinh():
    r = client.get("/api/luat-kiem/thuoc-tinh")
    assert r.status_code == 200
    ten = [x["ten"] for x in r.json()["thuoc_tinh"]]
    assert "lãi suất" in ten


def test_tat_roi_bat_lai_mot_thuoc_tinh():
    """`doc_bang` chỉ trả thuộc tính ĐANG BẬT - tắt rồi thì biến khỏi danh sách."""
    client.post("/api/luat-kiem/thuoc-tinh", json={"ten": "tuổi", "bat": False})
    ten = [x["ten"] for x in client.get("/api/luat-kiem/thuoc-tinh").json()["thuoc_tinh"]]
    assert "tuổi" not in ten
    client.post("/api/luat-kiem/thuoc-tinh", json={"ten": "tuổi", "bat": True})
    ten = [x["ten"] for x in client.get("/api/luat-kiem/thuoc-tinh").json()["thuoc_tinh"]]
    assert "tuổi" in ten


def test_khoi_phuc_mac_dinh_dua_lai_du_bang():
    from backend.pipeline.thuoc_tinh import THUOC_TINH_MAC_DINH
    client.post("/api/luat-kiem/thuoc-tinh/khoi-phuc")
    r = client.get("/api/luat-kiem/thuoc-tinh").json()["thuoc_tinh"]
    assert len(r) >= len(THUOC_TINH_MAC_DINH)
```

- [ ] **Step 2: Chạy test, xác nhận đỏ**

Run: `ssh win 'cd C:/duan/chat-ai; .venv/python.exe -m pytest tests/test_api_luat_kiem.py -q'`
Expected: FAIL — 404 vì route chưa có

- [ ] **Step 3: Viết API**

```python
"""Luật kiểm chứng: bảng thuộc tính sửa được trên trang quản lý."""
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
    bang = await luat_kiem_db.doc_bang()
    return {"thuoc_tinh": [
        {"ten": ten, "tu_khoa": list(d["khoa"]), "don_vi": list(d["dvi"]), "bat": True}
        for ten, d in sorted(bang.items())]}


@router.post("/thuoc-tinh")
async def sua_thuoc_tinh(req: SuaThuocTinh):
    ok = await luat_kiem_db.sua(req.ten, req.tu_khoa, req.don_vi, req.bat)
    return {"ok": True} if ok else {"error": f"Không có thuộc tính {req.ten!r}"}


@router.post("/thuoc-tinh/khoi-phuc")
async def khoi_phuc_mac_dinh():
    return {"ok": True, "da_gieo": await luat_kiem_db.khoi_phuc()}
```

Đăng ký trong `backend/main.py`, cạnh các `include_router` khác:

```python
from backend.api import luat_kiem
app.include_router(luat_kiem.router)
```

- [ ] **Step 4: Chạy test, xác nhận xanh**

Run: `ssh win 'cd C:/duan/chat-ai; .venv/python.exe -m pytest tests/test_api_luat_kiem.py tests/ -q'`
Expected: PASS toàn bộ

- [ ] **Step 5: Commit**

```bash
git add backend/api/luat_kiem.py backend/main.py tests/test_api_luat_kiem.py
git commit -m "feat(chan-bia): API doc/sua bang thuoc tinh"
```

---

### Task 7: Chấm lại trên 250 lượt bằng chính lưới thật

**Files:**
- Modify: `scripts/cham_luoi_thuoc_tinh.py` (dùng `chan_thuoc_tinh_sai` thật thay bản chép tay)

**Interfaces:**
- Consumes: `chan_thuoc_tinh_sai`, `luat_kiem_db.doc_bang_sync`

- [ ] **Step 1: Sửa script chấm dùng module thật**

Thay phần trích/so chép tay trong script bằng:

```python
import asyncio

from backend.models import db
from backend.models.luat_kiem_db import doc_bang_sync
from backend.pipeline.thuoc_tinh import chan_thuoc_tinh_sai

asyncio.run(db.init_db(r"C:\duan\chat-ai\data\app.db"))
BANG = doc_bang_sync(db.connection())
```

và trong vòng lặp:

```python
    _, sua = chan_thuoc_tinh_sai(ai, tai_lieu_cua(sp), BANG, khach_noi=khach)
    if sua:
        n_chan += 1
```

- [ ] **Step 2: Chạy và so với số đã đo**

Run: `ssh win 'cd C:/duan/chat-ai; .venv/python.exe scripts/cham_luoi_thuoc_tinh.py'`
Expected: tỉ lệ chặn **6,4% ± 1** trên 250 lượt (số đã đo 08-09 bằng bản chép tay). Lệch nhiều hơn thế nghĩa là module thật khác bản đã chấm — phải tìm ra vì sao trước khi đi tiếp.

- [ ] **Step 3: Commit**

```bash
git add scripts/cham_luoi_thuoc_tinh.py
git commit -m "test(chan-bia): script cham dung module that thay ban chep tay"
```

---

## Nghiệm thu kế hoạch này

- `chan_thuoc_tinh_sai` chặn 6,4% ± 1 trên 250 lượt, khớp số đã đo bằng bản chép tay
- 0/10 câu đúng trong tập đối chứng bị báo lệch
- Toàn bộ test cũ vẫn xanh (1305 test)
- Đường sinh **chưa thay câu nào** — chỉ ghi `metrics["chan_thuoc_tinh"]` và log
- Không thêm mili giây nào đo được vào TTFA (không I/O, không GPU trong đường sinh)

## Hai kế hoạch tiếp theo (chưa viết)

- **Lưới NLI** — mốc 3–4 của spec. Cần mô hình ~560MB VRAM, năm bộ lọc, ngưỡng 0,30, chế độ ghi nhật ký trước.
- **Trang quản lý + mở CORE_RULES** — mốc 5–6. Phụ thuộc API ở Task 6 của kế hoạch này.
