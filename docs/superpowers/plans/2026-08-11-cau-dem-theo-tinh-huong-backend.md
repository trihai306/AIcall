# Câu đệm theo tình huống — phần lõi và tích hợp vào cuộc gọi

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Câu đệm chọn theo tình huống khách vừa nói, ghép mẩu mở đầu riêng với đuôi dùng chung thành một phát ngôn F5, chạy được trên cuộc gọi thật.

**Architecture:** Phân loại tình huống bằng embedding của RAG, chạy trong `speculate()` lúc khách còn nói và **không bao giờ chờ**. `_send_filler` đọc kết quả đã có, chọn clip đã ghép sẵn trong cache theo độ dài tổng. Mọi đường xuống cấp đều về đúng hành vi hôm nay (rổ đuôi trần), không đường nào dẫn tới im lặng.

**Tech Stack:** Python 3.11, SQLite (stdlib `sqlite3`), sentence-transformers (đã nạp cho RAG), numpy, pytest. Không thêm phụ thuộc mới.

## Global Constraints

- **Không import torch** trong `filler_store.py`, `filler_pick.py`, `filler_situation.py`. Ba tệp này phải test được trên máy không GPU.
- **Tiếng câu đệm chỉ lấy từ cache.** Không bao giờ sinh trên đường găng. Thiếu thì dùng đuôi trần.
- Test chạy trên máy Win: `ssh win 'cd C:\duan\chat-ai; .venv\python.exe -m pytest ...'`. Máy Mac không có pytest lẫn torch.
- Mốc test hiện tại: **5 đỏ / 145 xanh**. 5 đỏ đó là `test_filler_pick.py` và Task 1 sửa chúng. Sau Task 1 phải là **0 đỏ**.
- `PHIEN_BAN = 4` trong `filler_store.py`. Ghép chuỗi làm đổi `text` nên vân tay tự đổi — **không tăng `PHIEN_BAN`** trong kế hoạch này.
- Ngưỡng tạm, chưa đo: độ phủ audio `0.5`, điểm cosine `0.55`, số đuôi `6`. Task 12 chốt bằng số thật.
- Tiếng Việt trong chuỗi và chú thích: viết trực tiếp UTF-8. **Không** truyền tiếng Việt qua dòng lệnh SSH — hỏng dấu; dùng tệp.

---

### Task 1: Sửa 5 test đỏ trong `test_filler_pick.py`

Điều kiện tiên quyết. Xây tính năng lên bộ test đang nói dối thì hồi quy sau không ai bắt được. **Mã là đúng và có số đo biện minh trong docstring `can_che_ms`; test cũ chưa cập nhật hai thay đổi: biên `1.25` và `mac_dinh` thành SÀN.**

**Files:**
- Modify: `tests/test_filler_pick.py:80-107`

**Interfaces:**
- Consumes: `can_che_ms(lich_su, la_thoai, mac_dinh)` từ `backend/services/filler_pick.py` — không đổi.
- Produces: không có gì cho task sau; đây là task dọn nền.

- [ ] **Step 1: Chạy để thấy đúng 5 lỗi và ghi lại giá trị thật**

```bash
ssh win 'cd C:\duan\chat-ai; .venv\python.exe -m pytest tests\test_filler_pick.py -q'
```

Kỳ vọng: `5 failed`. Các giá trị thật đã đo: `2500.0`, `1800.0`, `6250.0`, `1800.0`, `1800.0`.

- [ ] **Step 2: Sửa 5 kỳ vọng theo hành vi có chủ đích**

Thay toàn bộ 5 hàm test bằng bản dưới. Chú thích nêu vì sao con số là thế, để lần sau ai đọc cũng biết đây không phải sửa cho xanh.

```python
def test_chi_tinh_luot_that_khi_co_ca_hai_loai():
    """Lượt trả bằng bảng câu sẵn bị BỎ. Còn lại max(2000, 1500) = 2000,
    nhân biên 1.25 -> 2500."""
    su = [
        {"ttfa_ms": 450, "la_thoai": True, "luot_thuong_gap": "chào hỏi"},
        {"ttfa_ms": 2000, "la_thoai": True},
        {"ttfa_ms": 1500, "la_thoai": True},
    ]
    assert can_che_ms(su, la_thoai=True, mac_dinh=1800.0) == 2500.0


def test_loc_dung_duong_thoai_hay_chat():
    """Chỉ lượt thoại được tính: 1200 * 1.25 = 1500, nhưng `mac_dinh` là SÀN
    nên kết quả là 1800."""
    su = [{"ttfa_ms": 3000, "la_thoai": False}, {"ttfa_ms": 1200, "la_thoai": True}]
    assert can_che_ms(su, la_thoai=True, mac_dinh=1800.0) == 1800.0


def test_lay_max_cua_sau_luot_gan_nhat():
    """Cửa sổ là SÁU lượt (`lich_su[-6:]`), không phải ba. Cả 4 lượt đều nằm
    trong cửa sổ nên max là 5000, nhân biên -> 6250."""
    su = [{"ttfa_ms": v, "la_thoai": True} for v in (5000, 1000, 1100, 1200)]
    assert can_che_ms(su, la_thoai=True, mac_dinh=1800.0) == 6250.0


def test_bo_qua_luot_thieu_ttfa():
    """None và 0 đều bị bỏ. Còn 1300 * 1.25 = 1625, dưới sàn -> 1800."""
    su = [
        {"ttfa_ms": None, "la_thoai": True},
        {"ttfa_ms": 0, "la_thoai": True},
        {"ttfa_ms": 1300, "la_thoai": True},
    ]
    assert can_che_ms(su, la_thoai=True, mac_dinh=1800.0) == 1800.0


def test_suy_ra_duong_tu_stt_ms_khi_ban_ghi_cu_khong_co_la_thoai():
    """Bản ghi cũ thiếu khoá `la_thoai` thì suy từ `stt_ms`. 1400 * 1.25 = 1750,
    dưới sàn -> 1800."""
    cu = [{"ttfa_ms": 1400, "stt_ms": 300}]
    assert can_che_ms(cu, la_thoai=True, mac_dinh=1800.0) == 1800.0
```

- [ ] **Step 3: Thêm hai test khoá đúng hai thay đổi vừa làm test cũ sai**

Không có hai test này thì lần sau ai bỏ biên hoặc bỏ sàn vẫn xanh.

```python
def test_bien_an_toan_duoc_ap_dung():
    """Biên 1.25 phải ăn khi kết quả vượt sàn."""
    su = [{"ttfa_ms": 4000, "la_thoai": True}]
    assert can_che_ms(su, la_thoai=True, mac_dinh=1800.0) == 5000.0


def test_mac_dinh_la_san_khong_phai_chi_gia_tri_lui():
    """Lịch sử toàn lượt nhanh vẫn không được xuống dưới sàn - vài lượt nhanh
    liên tiếp rồi một lượt chậm đột ngột là khách nghe hụt."""
    su = [{"ttfa_ms": 200, "la_thoai": True} for _ in range(6)]
    assert can_che_ms(su, la_thoai=True, mac_dinh=1800.0) == 1800.0
```

- [ ] **Step 4: Chạy lại, phải sạch**

```bash
ssh win 'cd C:\duan\chat-ai; .venv\python.exe -m pytest tests\test_filler_pick.py -q'
```

Kỳ vọng: `9 passed`.

- [ ] **Step 5: Chạy toàn bộ để chắc mốc là 0 đỏ**

```bash
ssh win 'cd C:\duan\chat-ai; .venv\python.exe -m pytest tests -q'
```

Kỳ vọng: `0 failed`.

- [ ] **Step 6: Commit**

```bash
git add tests/test_filler_pick.py
git commit -m "test(filler): cap nhat 5 test cu theo bien 1.25 va san mac_dinh

Mac dinh la SAN chu khong phai gia tri lui, va can_che_ms nhan bien 1.25 -
ca hai deu co so do bien minh trong docstring. Test viet truoc hai thay doi
do nen ky vong gia tri tho. Ten test con noi 'ba luot' trong khi ma lay [-6:].

Them hai test khoa dung hai thay doi ay, khong thi lan sau bo di van xanh."
```

---

### Task 2: `filler_situation.py` — chọn tình huống bằng cosine

**Files:**
- Create: `backend/services/filler_situation.py`
- Test: `tests/test_filler_situation.py`

**Interfaces:**
- Consumes: numpy. Không gì từ task trước.
- Produces:
  - `chuan_hoa(v: np.ndarray) -> np.ndarray`
  - `chon_tinh_huong(q: np.ndarray, kho: dict[str, np.ndarray], nguong: float = NGUONG_DIEM) -> tuple[str | None, float]` — `kho` là `{id_tình_huống: ma trận (n_ví_dụ, d) đã chuẩn hoá}`. Trả `(id, điểm)` hoặc `(None, điểm_cao_nhất)`.
  - `NGUONG_DIEM: float = 0.55`

- [ ] **Step 1: Viết test trước**

```python
"""Chọn tình huống bằng cosine. Thuần numpy, không GPU."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest

from backend.services.filler_situation import (
    NGUONG_DIEM, chon_tinh_huong, chuan_hoa,
)


def v(*x) -> np.ndarray:
    return np.array(x, dtype=np.float32)


def test_chon_tinh_huong_diem_cao_nhat():
    kho = {
        "lai_suat": chuan_hoa(np.stack([v(1, 0, 0)])),
        "ho_so": chuan_hoa(np.stack([v(0, 1, 0)])),
    }
    id_th, diem = chon_tinh_huong(chuan_hoa(v(0.9, 0.1, 0))[0], kho)
    assert id_th == "lai_suat" and diem > NGUONG_DIEM


def test_lay_vi_du_khop_nhat_trong_cung_tinh_huong():
    """Một tình huống có nhiều ví dụ: lấy ví dụ KHỚP NHẤT, không lấy trung bình.
    Trung bình làm loãng - hai ví dụ trái nhau triệt tiêu nhau."""
    kho = {"a": chuan_hoa(np.stack([v(1, 0, 0), v(0, 0, 1)]))}
    id_th, diem = chon_tinh_huong(chuan_hoa(v(0, 0, 1))[0], kho)
    assert id_th == "a" and diem == pytest.approx(1.0, abs=1e-5)


def test_duoi_nguong_tra_none_kem_diem():
    """Trả cả điểm để nơi gọi ghi log được vì sao trượt."""
    kho = {"a": chuan_hoa(np.stack([v(1, 0, 0)]))}
    id_th, diem = chon_tinh_huong(chuan_hoa(v(0, 1, 0))[0], kho)
    assert id_th is None and diem < NGUONG_DIEM


def test_kho_rong():
    id_th, diem = chon_tinh_huong(chuan_hoa(v(1, 0, 0))[0], {})
    assert id_th is None and diem == 0.0


def test_tinh_huong_khong_co_vi_du_bi_bo_qua():
    """Ma trận rỗng không được làm hàm nổ."""
    kho = {"rong": np.zeros((0, 3), dtype=np.float32),
           "a": chuan_hoa(np.stack([v(1, 0, 0)]))}
    assert chon_tinh_huong(chuan_hoa(v(1, 0, 0))[0], kho)[0] == "a"


def test_chuan_hoa_vector_khong():
    """Vector 0 không được sinh NaN - chia cho 0 là bẫy im lặng."""
    r = chuan_hoa(v(0, 0, 0))
    assert not np.isnan(r).any()


def test_nguong_tuy_chinh():
    kho = {"a": chuan_hoa(np.stack([v(1, 0, 0)]))}
    q = chuan_hoa(v(0.8, 0.6, 0))[0]
    assert chon_tinh_huong(q, kho, nguong=0.9)[0] is None
    assert chon_tinh_huong(q, kho, nguong=0.5)[0] == "a"
```

- [ ] **Step 2: Chạy để thấy fail**

```bash
ssh win 'cd C:\duan\chat-ai; .venv\python.exe -m pytest tests\test_filler_situation.py -q'
```

Kỳ vọng: `ModuleNotFoundError: No module named 'backend.services.filler_situation'`.

- [ ] **Step 3: Viết bản cài đặt tối thiểu**

```python
"""Chọn tình huống từ phiên âm dở bằng cosine. KHÔNG import torch - xem
filler_store để biết vì sao cả ba tệp câu đệm phải chạy được không cần GPU.
"""
import numpy as np

# Điểm cosine tối thiểu để nhận một tình huống. TẠM 0.55, CHƯA ĐO.
# Chọn sai mẩu mở đầu tệ hơn không có mẩu nào, nên khi lưỡng lự phải rơi về rổ
# chung. Chốt lại bằng số thật sau khi có bộ câu khách để đối chiếu.
NGUONG_DIEM = 0.55


def chuan_hoa(v: np.ndarray) -> np.ndarray:
    """Chuẩn hoá L2 theo hàng cuối. Nhận cả vector 1 chiều và ma trận.

    Vector 0 trả về chính nó chứ không chia cho 0: đoạn phiên âm rỗng hoàn toàn
    có thể cho ra vector 0, mà NaN lan ra thì mọi điểm sau đó vô nghĩa và không
    có gì báo lỗi.
    """
    v = np.asarray(v, dtype=np.float32)
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return np.divide(v, n, out=np.zeros_like(v), where=n > 1e-12)


def chon_tinh_huong(q: np.ndarray, kho: dict[str, np.ndarray],
                    nguong: float = NGUONG_DIEM) -> tuple[str | None, float]:
    """Tình huống khớp nhất với `q`, hoặc `(None, điểm_cao_nhất)` nếu dưới ngưỡng.

    `kho` = {id: ma trận (số_ví_dụ, d) ĐÃ chuẩn hoá}. `q` đã chuẩn hoá.

    Lấy ví dụ KHỚP NHẤT trong mỗi tình huống, không lấy trung bình các ví dụ:
    một tình huống thường có nhiều cách nói rất khác nhau ("lãi suất bao nhiêu"
    với "một tháng trả bao nhiêu"), lấy trung bình là làm loãng cả hai.
    """
    tot_id, tot_diem = None, 0.0
    for id_th, M in kho.items():
        if M.size == 0:
            continue
        diem = float(np.max(M @ q))
        if diem > tot_diem:
            tot_id, tot_diem = id_th, diem
    if tot_id is not None and tot_diem >= nguong:
        return tot_id, tot_diem
    return None, tot_diem
```

- [ ] **Step 4: Chạy lại, phải xanh**

```bash
ssh win 'cd C:\duan\chat-ai; .venv\python.exe -m pytest tests\test_filler_situation.py -q'
```

Kỳ vọng: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/services/filler_situation.py tests/test_filler_situation.py
git commit -m "feat(filler): chon tinh huong bang cosine, thuan numpy

Lay vi du KHOP NHAT trong moi tinh huong chu khong lay trung binh: mot tinh
huong co nhieu cach noi rat khac nhau, trung binh lam loang ca hai.

Vector 0 khong chia cho 0 - doan phien am rong cho ra vector 0 va NaN lan ra
thi moi diem sau do vo nghia ma khong co gi bao loi."
```

---

### Task 3: Hai bảng kho trong `app.db`, nạp lần đầu từ JSON

**Files:**
- Modify: `backend/models/db.py` — thêm 2 bảng vào `_SCHEMA` (sau `CREATE TABLE ... scenarios`)
- Modify: `backend/services/filler_store.py` — `nap()` đọc DB, giữ `nap_lai()`
- Test: `tests/test_filler_store.py` (mới)

**Interfaces:**
- Consumes: `chuan_hoa` chưa dùng ở đây. Dùng `sqlite3` stdlib.
- Produces:
  - `TinhHuong(id, ten, vi_du: tuple[str,...], tu_khoa: tuple[str,...], mo_dau: tuple[str,...], speed: float | None, bat: bool)`
  - `CauDuoi(id, text, hop_cau_hoi: bool, bat: bool)`
  - `Kho(tinh_huong: tuple[TinhHuong,...], duoi: tuple[CauDuoi,...])`
  - `nap_tu_db(conn) -> Kho`, `do_json_vao_db(conn, duong_dan_json) -> int`
  - `LoiKho` — giữ nguyên tên cũ.

- [ ] **Step 1: Viết test xác thực trước**

```python
"""Kho câu đệm đọc từ SQLite. Không cần GPU."""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from backend.services.filler_store import (
    LoiKho, do_json_vao_db, nap_tu_db,
)

DDL = """
CREATE TABLE tinh_huong (
  id TEXT PRIMARY KEY, ten TEXT NOT NULL, vi_du TEXT NOT NULL,
  tu_khoa TEXT, mo_dau TEXT, speed REAL,
  bat INTEGER NOT NULL DEFAULT 1, created_at REAL, updated_at REAL);
CREATE TABLE cau_duoi (
  id TEXT PRIMARY KEY, text TEXT NOT NULL,
  hop_cau_hoi INTEGER NOT NULL DEFAULT 1,
  bat INTEGER NOT NULL DEFAULT 1, created_at REAL, updated_at REAL);
"""


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(DDL)
    return c


def them_th(c, id="hoi_lai_suat", vi_du=("lãi suất bao nhiêu", "lãi thế nào"),
            mo_dau=("Dạ về lãi suất thì,",), speed=None, bat=1):
    c.execute("INSERT INTO tinh_huong (id,ten,vi_du,tu_khoa,mo_dau,speed,bat) "
              "VALUES (?,?,?,?,?,?,?)",
              (id, "Hỏi lãi suất", json.dumps(list(vi_du)), "[]",
               json.dumps(list(mo_dau)), speed, bat))


def them_duoi(c, id="d1", text="anh chị chờ em một chút ạ.", bat=1):
    c.execute("INSERT INTO cau_duoi (id,text,bat) VALUES (?,?,?)", (id, text, bat))


def test_nap_binh_thuong(conn):
    them_th(conn); them_duoi(conn)
    kho = nap_tu_db(conn)
    assert [t.id for t in kho.tinh_huong] == ["hoi_lai_suat"]
    assert kho.tinh_huong[0].vi_du == ("lãi suất bao nhiêu", "lãi thế nào")
    assert kho.duoi[0].text == "anh chị chờ em một chút ạ."


def test_bo_qua_muc_da_tat(conn):
    them_th(conn, bat=0); them_duoi(conn, bat=0)
    kho = nap_tu_db(conn)
    assert kho.tinh_huong == () and kho.duoi == ()


def test_vi_du_duoi_hai_cau_thi_loi(conn):
    them_th(conn, vi_du=("chỉ một câu",)); them_duoi(conn)
    with pytest.raises(LoiKho, match="hoi_lai_suat"):
        nap_tu_db(conn)


def test_mo_dau_khong_ket_bang_phay_thi_loi(conn):
    """Mẩu mở đầu phải kết bằng phẩy để F5 nghỉ ngắn thay vì hạ giọng kết câu."""
    them_th(conn, mo_dau=("Dạ về lãi suất thì",)); them_duoi(conn)
    with pytest.raises(LoiKho, match="phẩy"):
        nap_tu_db(conn)


def test_duoi_text_rong_thi_loi(conn):
    them_th(conn); them_duoi(conn, text="   ")
    with pytest.raises(LoiKho, match="d1"):
        nap_tu_db(conn)


def test_khong_co_duoi_nao_thi_loi(conn):
    """Rổ đuôi rỗng là mất hoàn toàn đường xuống cấp - khách nghe im lặng."""
    them_th(conn)
    with pytest.raises(LoiKho, match="đuôi"):
        nap_tu_db(conn)


def test_do_json_vao_db_khi_bang_rong(conn, tmp_path):
    p = tmp_path / "fillers.json"
    p.write_text(json.dumps({
        "chu_de": [{"id": "chung", "ten": "Chung"}],
        "cau": [{"id": "c1", "text": "dạ vâng ạ.", "chu_de": "chung",
                 "hop_cau_hoi": True}],
    }, ensure_ascii=False), encoding="utf-8")
    assert do_json_vao_db(conn, p) == 1
    assert nap_tu_db(conn).duoi[0].text == "dạ vâng ạ."


def test_do_json_khong_ghi_de_khi_da_co_du_lieu(conn, tmp_path):
    them_duoi(conn, id="san_co", text="câu đã có ạ.")
    p = tmp_path / "fillers.json"
    p.write_text(json.dumps({"chu_de": [], "cau": [
        {"id": "c1", "text": "câu mới ạ.", "chu_de": "chung"}]},
        ensure_ascii=False), encoding="utf-8")
    assert do_json_vao_db(conn, p) == 0
    assert [d.id for d in nap_tu_db(conn).duoi] == ["san_co"]
```

- [ ] **Step 2: Chạy để thấy fail**

```bash
ssh win 'cd C:\duan\chat-ai; .venv\python.exe -m pytest tests\test_filler_store.py -q'
```

Kỳ vọng: `ImportError: cannot import name 'nap_tu_db'`.

- [ ] **Step 3: Thêm hai bảng vào `_SCHEMA`**

Trong `backend/models/db.py`, chèn ngay sau khối `CREATE TABLE IF NOT EXISTS scenarios (...);`:

```sql
-- Kho cau dem theo tinh huong. La CAU HINH dung chung cho moi cuoc goi, nen
-- nam o app.db chu khong tach theo khach: tach ra la moi khach mot ban sao cua
-- cung mot thu, va nhan len dung tai nguyen dat nhat (GPU dung tieng moi giong).
CREATE TABLE IF NOT EXISTS tinh_huong (
    id         TEXT PRIMARY KEY,
    ten        TEXT NOT NULL,
    vi_du      TEXT NOT NULL,      -- JSON array: cau khach noi mau, de nhung
    tu_khoa    TEXT,               -- JSON array: loc tho / du phong
    mo_dau     TEXT,               -- JSON array: mau mo dau rieng
    speed      REAL,               -- NULL = lay toc cua giong
    bat        INTEGER NOT NULL DEFAULT 1,
    created_at REAL,
    updated_at REAL
);

CREATE TABLE IF NOT EXISTS cau_duoi (
    id          TEXT PRIMARY KEY,
    text        TEXT NOT NULL,
    hop_cau_hoi INTEGER NOT NULL DEFAULT 1,
    bat         INTEGER NOT NULL DEFAULT 1,
    created_at  REAL,
    updated_at  REAL
);
```

- [ ] **Step 4: Viết `nap_tu_db` và `do_json_vao_db`**

Trong `backend/services/filler_store.py`: giữ nguyên `LoiKho`, `van_tay`, `PHIEN_BAN`. Thay `ChuDe`/`CauDem`/`Kho` bằng ba lớp dưới và thêm hai hàm.

```python
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
```

Thêm `import time` vào đầu tệp nếu chưa có.

- [ ] **Step 5: Chạy lại, phải xanh**

```bash
ssh win 'cd C:\duan\chat-ai; .venv\python.exe -m pytest tests\test_filler_store.py -q'
```

Kỳ vọng: `8 passed`.

- [ ] **Step 6: Nối `lay_kho()` vào DB**

Thay thân `lay_kho()`, giữ chữ ký và `nap_lai()`:

```python
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
```

Hàm lấy kết nối là `connection()` — trả `None` trước khi `init_db()` chạy, nên **phải kiểm None**. Không có hàm nào tên `get_conn`; đừng thêm hàm mới.

- [ ] **Step 7: Chạy toàn bộ test**

```bash
ssh win 'cd C:\duan\chat-ai; .venv\python.exe -m pytest tests -q'
```

Kỳ vọng: `0 failed`.

- [ ] **Step 8: Commit**

```bash
git add backend/models/db.py backend/services/filler_store.py tests/test_filler_store.py
git commit -m "feat(filler): kho tinh huong + cau duoi trong app.db

Hai bang trong app.db, KHONG tach theo khach: day la cau hinh dung chung cho
moi cuoc goi.

vi_du/tu_khoa/mo_dau de JSON mot cot vi luon doc-ghi ca cum, tach bang chi
them join ma khong dung de lam gi.

Ba luat xac thuc, moi luat chan mot loi im lang: vi_du duoi 2 cau lam diem
cosine dua vao dung mot cach noi; mau mo dau khong ket bang phay lam F5 ha
giong ket cau giua luot; ro duoi rong la mat duong xuong cap cuoi cung."
```

---

### Task 4: `RAGService.embed()` công khai + nhúng sẵn ví dụ lúc khởi động

**Files:**
- Modify: `backend/services/rag_service.py` — thêm `embed()`
- Modify: `backend/core/startup.py` — nhúng sẵn sau khi RAG và kho đã nạp

**Interfaces:**
- Consumes: `chuan_hoa` từ Task 2; `lay_kho()` từ Task 3.
- Produces:
  - `RAGService.embed(texts: list[str]) -> np.ndarray` — hình `(n, d)`, **chưa** chuẩn hoá.
  - `app_state.kho_vector: dict[str, np.ndarray]` — đã chuẩn hoá, dùng cho `chon_tinh_huong`.

- [ ] **Step 1: Thêm `embed()` vào `RAGService`**

```python
    def embed(self, texts: list[str]) -> "np.ndarray":
        """Nhúng danh sách chuỗi. Hình (n, d), CHƯA chuẩn hoá.

        Công khai để phần chọn tình huống dùng lại đúng model này thay vì nạp
        thêm một model nữa - VRAM 12GB đã phải chia cho STT, LLM và TTS.
        """
        import numpy as np
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        return np.asarray(self._embedder.encode(texts), dtype=np.float32)
```

- [ ] **Step 2: Nhúng sẵn ví dụ lúc khởi động**

Trong `backend/core/startup.py`, sau bước nạp RAG, thêm:

```python
    # Nhúng sẵn ví dụ của mọi tình huống. Làm một lần ở đây chứ không mỗi lượt:
    # lúc khách đang nói ta chỉ được nhúng ĐÚNG MỘT chuỗi (phiên âm dở), so với
    # ma trận đã có sẵn.
    from backend.services.filler_situation import chuan_hoa
    from backend.services.filler_store import lay_kho
    try:
        kho = lay_kho()
        app_state.kho_vector = {
            t.id: chuan_hoa(app_state.rag.embed(list(t.vi_du)))
            for t in kho.tinh_huong if t.vi_du
        }
        logger.info("Đã nhúng ví dụ của %d tình huống", len(app_state.kho_vector))
    except Exception as e:
        # Không có phân loại thì câu đệm rơi về rổ chung, tức đúng hành vi cũ.
        # Đây KHÔNG phải lỗi chặn khởi động.
        app_state.kho_vector = {}
        logger.warning("Không nhúng được ví dụ tình huống, câu đệm sẽ dùng rổ "
                       "chung: %s", e)
```

Khai báo `kho_vector: dict = {}` ở chỗ định nghĩa `app_state` để thuộc tính luôn tồn tại.

- [ ] **Step 3: Kiểm bằng tay trên máy Win**

```bash
ssh win 'cd C:\duan\chat-ai; powershell -ExecutionPolicy Bypass -File scripts\start_services.ps1 -Detached -Restart'
ssh win 'Select-String -Path C:\duan\chat-ai\logs\backend.log -Pattern "nhung vi du|nap kho cau dem" | ForEach-Object { $_.Line }'
```

Kỳ vọng: một dòng "Đã nạp kho câu đệm: 0 tình huống, 42 câu đuôi" và một dòng "Đã nhúng ví dụ của 0 tình huống". Số 0 là đúng ở bước này — chưa nạp tình huống nào, Task 11 mới nạp.

- [ ] **Step 4: Commit**

```bash
git add backend/services/rag_service.py backend/core/startup.py
git commit -m "feat(filler): RAGService.embed() cong khai, nhung san vi du luc khoi dong

Dung lai model embedding cua RAG chu khong nap them model: VRAM 12GB da phai
chia cho STT, LLM va TTS.

Nhung san mot lan luc khoi dong. Luc khach dang noi chi nhung DUNG MOT chuoi
(phien am do) roi so voi ma tran co san.

Nhung that bai KHONG chan khoi dong - khong co phan loai thi cau dem roi ve
ro chung, tuc dung hanh vi cu."
```

---

### Task 5: Phân loại trong `speculate` → `session.tinh_huong`

**Files:**
- Modify: `backend/pipeline/session_manager.py:106` — thêm ô `tinh_huong`, và reset ở `:181`
- Modify: `backend/pipeline/streaming_pipeline.py` — trong `speculate()._run()`, ngay sau `session.spec_stt = (n, text)`

**Interfaces:**
- Consumes: `chon_tinh_huong`, `chuan_hoa` (Task 2); `app_state.kho_vector` (Task 4).
- Produces: `session.tinh_huong: tuple[int, str, float] | None` = `(số_byte_đã_thấy, id_tình_huống, điểm)`.

- [ ] **Step 1: Thêm ô vào session**

Cạnh `self.spec_stt`, cùng lối chú thích:

```python
        # Tình huống đoán được từ phiên âm dở: (số byte đã thấy, id, điểm).
        # `_send_filler` đọc ô này để chọn mẩu mở đầu. Số byte để biết đoán này
        # phủ được bao nhiêu phần câu - đoán trên câu cụt thì dễ trượt.
        self.tinh_huong: tuple[int, str, float] | None = None
```

Và trong hàm reset lượt, cạnh `self.spec_stt = None`:

```python
        self.tinh_huong = None
```

- [ ] **Step 2: Phân loại trong `speculate`**

Trong `_run()` của `speculate`, ngay **sau** dòng `session.spec_stt = (n, text)` và **trước** `if len(text) < 4: return`:

```python
                # Phân loại tình huống ngay tại đây, cùng chỗ và cùng lý do với
                # `spec_stt`: đây là điểm sớm nhất đã có chữ. Không await gì ở
                # đường găng - `_send_filler` đọc được thì dùng, không thì rơi
                # về rổ chung. Cùng triết lý với chính hàm này: đoán trượt thì bỏ.
                try:
                    kho_vec = getattr(app_state, "kho_vector", None)
                    if kho_vec and len(text) >= 4:
                        q = chuan_hoa(self.rag.embed([text]))[0]
                        id_th, diem = chon_tinh_huong(q, kho_vec)
                        if id_th:
                            session.tinh_huong = (n, id_th, diem)
                except Exception as e:
                    logger.debug("phân loại tình huống trượt (bỏ qua): %s", e)
```

Thêm import ở đầu `streaming_pipeline.py`:

```python
from backend.services.filler_situation import chon_tinh_huong, chuan_hoa
```

`app_state` lấy bằng `from backend.main import app_state` **trong thân hàm**, giống lối `backend/api/voices.py` đang làm, để tránh vòng import.

- [ ] **Step 3: Kiểm bằng cuộc gọi thật, đọc log**

Chưa có tình huống nào trong DB nên `kho_vector` rỗng và nhánh này không chạy — đúng như mong đợi. Chỉ cần chắc **không có ngoại lệ nào rơi ra**:

```bash
ssh win 'cd C:\duan\chat-ai; .venv\python.exe scripts\goi_qua_he_thong.py 0396130621 --giay 30'
ssh win 'Select-String -Path C:\duan\chat-ai\logs\backend.log -Pattern "phan loai tinh huong|Traceback" | ForEach-Object { $_.Line } | Select-Object -Last 5'
```

Kỳ vọng: không có `Traceback`.

- [ ] **Step 4: Commit**

```bash
git add backend/pipeline/session_manager.py backend/pipeline/streaming_pipeline.py
git commit -m "feat(filler): phan loai tinh huong trong speculate, khong bao gio cho

Dat cung cho voi spec_stt va cung ly do: day la diem som nhat da co chu.
Khong await gi o duong gang - _send_filler doc duoc thi dung, khong thi roi ve
ro chung. Cung triet ly voi chinh speculate: doan truot thi bo.

Ghi ca SO BYTE da thay de _send_filler biet doan nay phu duoc bao nhieu phan
cau: doan tren cau cut thi de truot."
```

---

### Task 6: Ghép chuỗi và chọn theo tình huống trong `filler_pick`

**Files:**
- Modify: `backend/services/filler_pick.py` — thêm `ghep()`, `du_phu()`
- Modify: `tests/test_filler_pick.py` — thêm test

**Interfaces:**
- Consumes: `chon(ung_vien, min_ms, dem, rng)` — giữ nguyên, không sửa.
- Produces:
  - `ghep(mo_dau: str, duoi: str) -> str`
  - `du_phu(do_dai: list[float], thap: float = 700.0, cao: float = 2500.0, buoc: float = 300.0) -> list[tuple[float, float]]` — trả các khoảng hở.

- [ ] **Step 1: Viết test**

```python
from backend.services.filler_pick import du_phu, ghep


def test_ghep_dung_mot_khoang_trang():
    assert ghep("Dạ về lãi suất thì,", "anh chị chờ em ạ.") == \
        "Dạ về lãi suất thì, anh chị chờ em ạ."


def test_ghep_khong_mo_dau_thi_tra_duoi_nguyen_ven():
    """Mở đầu rỗng là trường hợp suy biến - đúng hành vi hôm nay."""
    assert ghep("", "anh chị chờ em ạ.") == "anh chị chờ em ạ."


def test_ghep_khong_de_hai_dau_cach():
    assert ghep("Dạ vâng,  ", "  em nghe ạ.") == "Dạ vâng, em nghe ạ."


def test_du_phu_khong_ho():
    """Các mốc rải đều 300ms một thì không hở khoảng nào."""
    assert du_phu([700, 1000, 1300, 1600, 1900, 2200, 2500]) == []


def test_du_phu_bao_dung_khoang_ho():
    """Chỉ có câu 700ms và 2400ms -> hở đúng dải 1000-2200, gộp thành MỘT khoảng.

    Kiểm giá trị chính xác chứ không chỉ "có hở": bước 300ms nên các mốc là
    700/1000/1300/1600/1900/2200/2500. 700 lấp mốc đầu, 2400 lấp mốc 2200,
    còn lại hở liền một dải từ 1000 tới 2200.
    """
    assert du_phu([700, 2400]) == [(1000.0, 2200.0)]


def test_du_phu_hai_khoang_ho_roi_nhau_giu_roi():
    """Hai khoảng hở KHÔNG liền nhau thì phải giữ riêng, không gộp bừa.

    700 lấp mốc đầu, 1300 lấp mốc giữa, 2400 lấp mốc cuối -> hở hai chỗ rời:
    1000-1300 và 1600-2200. (Việc GỘP khoảng liền nhau đã do test trên khoá,
    ở đó 1000-2200 là bốn mốc hở liên tiếp gộp lại.)
    """
    assert du_phu([700, 1300, 2400]) == [(1000.0, 1300.0), (1600.0, 2200.0)]


def test_du_phu_ro_rong_thi_ho_toan_dai():
    assert du_phu([]) == [(700.0, 2500.0)]
```

- [ ] **Step 2: Chạy để thấy fail**

```bash
ssh win 'cd C:\duan\chat-ai; .venv\python.exe -m pytest tests\test_filler_pick.py -q'
```

Kỳ vọng: `ImportError: cannot import name 'ghep'`.

- [ ] **Step 3: Cài đặt**

```python
def ghep(mo_dau: str, duoi: str) -> str:
    """Ghép mẩu mở đầu với câu đuôi thành MỘT chuỗi cho F5.

    Một chuỗi chứ không nối hai đoạn TIẾNG: nối tiếng là tái tạo đúng lỗi chỗ
    nối mảnh - F5 sinh mỗi phát ngôn với ngữ điệu kết câu riêng, hai lần "kết
    câu" dính nhau nghe thành hai đoạn rời.

    Mở đầu rỗng trả về đuôi nguyên vẹn: đó là trường hợp suy biến, tức đúng
    hành vi trước khi có tình huống.
    """
    a, b = (mo_dau or "").strip(), (duoi or "").strip()
    return f"{a} {b}".strip() if a else b


# Dải độ dài câu đệm phải phủ. Dưới 700ms thì `_FILLER_BO_QUA_MS` đã bỏ đệm;
# trên 2500ms là dài hơn mọi quãng trễ đo được (678-2084ms) cộng biên 1.25.
DAI_THAP_MS, DAI_CAO_MS, BUOC_MS = 700.0, 2500.0, 300.0


def du_phu(do_dai: list[float], thap: float = DAI_THAP_MS,
           cao: float = DAI_CAO_MS, buoc: float = BUOC_MS
           ) -> list[tuple[float, float]]:
    """Các khoảng trong [thap, cao] KHÔNG có câu nào dài xấp xỉ. Trả list khoảng hở.

    Vì sao cần: trục chọn câu đệm là ĐỘ DÀI. Hở một khoảng nghĩa là mọi lượt có
    quãng trễ rơi vào khoảng đó sẽ làm `chon()` tụt xuống tầng chót "lấy câu dài
    nhất", và khách nghe hụt đúng phần thiếu. Trang quản lý dùng hàm này để
    CHỈ RA lỗ hổng thay vì chỉ liệt kê câu.
    """
    ho: list[tuple[float, float]] = []
    moc = thap
    while moc < cao:
        het = min(moc + buoc, cao)
        if not any(moc <= d < het for d in do_dai):
            if ho and ho[-1][1] == moc:
                ho[-1] = (ho[-1][0], het)      # gộp khoảng hở liền nhau
            else:
                ho.append((moc, het))
        moc = het
    return ho
```

- [ ] **Step 4: Chạy lại, phải xanh**

```bash
ssh win 'cd C:\duan\chat-ai; .venv\python.exe -m pytest tests\test_filler_pick.py -q'
```

Kỳ vọng: `15 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/services/filler_pick.py tests/test_filler_pick.py
git commit -m "feat(filler): ghep chuoi mo dau + duoi, va do phu dai do dai

ghep() tra MOT chuoi cho F5 chu khong noi hai doan tieng: noi tieng la tai tao
dung loi cho noi manh - F5 sinh moi phat ngon voi ngu dieu ket cau rieng.

du_phu() chi ra khoang HO trong dai 700-2500ms. Truc chon la do dai, ho mot
khoang la moi luot tre roi vao do lam chon() tut xuong tang chot 'lay cau dai
nhat' va khach nghe hut."
```

---

### Task 7: Dựng tiếng tổ hợp và `pick_filler` theo tình huống

**Files:**
- Modify: `backend/services/tts_service.py` — `dung_fillers`, `pick_filler`, cache key
- Test: kiểm bằng tay trên Win (dựng tiếng cần GPU)

**Interfaces:**
- Consumes: `ghep` (Task 6), `Kho`/`TinhHuong`/`CauDuoi` (Task 3).
- Produces:
  - `pick_filler(kho, voice=None, min_ms=0.0, dem=None, id_tinh_huong=None, chi_duoi=None) -> tuple[bytes | None, str | None, str | None]` — trả `(wav, id_đuôi, id_tình_huống_đã_dùng)`. `id_tình_huống` trả về `None` khi rơi về đuôi trần, để nơi gọi ghi log đúng sự thật. `chi_duoi: set[str] | None` giới hạn tập id đuôi được chọn — Task 8 cần nó để lọc `hop_cau_hoi`; `None` là không giới hạn.
  - Khoá cache đổi từ `(giọng, id_câu)` sang `(giọng, id_tình_huống_hoặc_rỗng, id_đuôi)`.

- [ ] **Step 1: Đổi khoá cache và dựng tổ hợp**

Trong `dung_fillers`: dựng **rổ đuôi trần trước** (bảo đảm luôn có đường xuống cấp), rồi các tổ hợp ở nền.

```python
        # Thu tu BAT BUOC: duoi tran truoc, to hop sau. Duoi tran la duong xuong
        # cap cuoi cung - dung no sau thi trong khoang thoi gian dung to hop,
        # mot cuoc goi den se khong co gi de phat.
        for d in kho.duoi:
            self._dung_mot_filler(name, "", d.id, ghep("", d.text), toc_giong)
        for t in kho.tinh_huong:
            toc = t.speed if t.speed is not None else toc_giong
            for m in t.mo_dau:
                for d in kho.duoi:
                    self._dung_mot_filler(name, t.id, d.id,
                                          ghep(m, d.text), toc)
```

`_dung_mot_filler(giong, id_th, id_duoi, text, toc)` tra vân tay, đọc đĩa nếu có, sinh nếu chưa, rồi ghi `self._filler_cache[(giong, id_th, id_duoi)]` và `self._filler_ms[...] = độ dài đo được`.

- [ ] **Step 2: `pick_filler` nhận tình huống**

```python
    def pick_filler(self, kho, voice=None, min_ms=0.0, dem=None,
                    id_tinh_huong: str | None = None,
                    chi_duoi: set[str] | None = None):
        """Chọn clip câu đệm ĐÃ CÓ TIẾNG. Trả (wav, id_đuôi, id_tình_huống_dùng).

        Chỉ lấy từ cache, không bao giờ sinh: chờ sinh tiếng là phá đúng mục
        đích của câu đệm. Tình huống không có tổ hợp nào đã dựng xong thì rơi về
        đuôi trần, thứ luôn có sẵn từ bước dựng đầu tiên.

        Chọn theo ĐỘ DÀI TỔNG của clip đã ghép, không phải "độ dài đuôi trừ độ
        dài mở đầu": độ dài tiếng của mẩu mở đầu không suy được từ chuỗi chữ,
        còn clip ghép thì đã đo sẵn lúc dựng.
        """
        name = self._giong_thuc(voice)
        for th in (id_tinh_huong, ""):
            if th is None:
                continue
            ung_vien = [(k[2], self._filler_ms[k]) for k in self._filler_cache
                        if k[0] == name and k[1] == (th or "")
                        and (chi_duoi is None or k[2] in chi_duoi)]
            if not ung_vien:
                continue
            chon_id = _chon_filler(ung_vien, min_ms=min_ms, dem=dem or {})
            if chon_id:
                return (self._filler_cache[(name, th or "", chon_id)],
                        chon_id, th or None)
        logger.warning(
            "pick_filler về tay không: xin giọng='%s' -> quy về '%s', "
            "tình huống=%s; cache giọng này %d mục",
            voice, name, id_tinh_huong,
            sum(1 for k in self._filler_cache if k[0] == name))
        return None, None, None
```

- [ ] **Step 3: Kiểm trên Win — đếm số clip đã dựng**

```bash
ssh win 'cd C:\duan\chat-ai; powershell -ExecutionPolicy Bypass -File scripts\start_services.ps1 -Detached -Restart'
ssh win 'Select-String -Path C:\duan\chat-ai\logs\backend.log -Pattern "Cau dem|cau dem" | ForEach-Object { $_.Line } | Select-Object -Last 3'
```

Kỳ vọng: dựng 42 clip đuôi trần (chưa có tình huống nào nên chưa có tổ hợp). `PHIEN_BAN = 4` nên **phải thấy "dựng mới" chứ không phải "đọc từ đĩa"** — đây chính là chỗ bắt lỗi vân tay.

- [ ] **Step 4: Commit**

```bash
git add backend/services/tts_service.py
git commit -m "feat(filler): dung tieng to hop, pick_filler chon theo tinh huong

Khoa cache doi tu (giong, id_cau) sang (giong, id_tinh_huong, id_duoi).

Chon theo DO DAI TONG cua clip da ghep, khong phai 'do dai duoi tru do dai mo
dau': do dai tieng cua mau mo dau khong suy duoc tu chuoi chu, con clip ghep
thi da do san luc dung.

Thu tu dung BAT BUOC la duoi tran truoc roi to hop sau: duoi tran la duong
xuong cap cuoi cung, dung no sau thi trong luc dung to hop mot cuoc goi den se
khong co gi de phat."
```

---

### Task 8: `_send_filler` dùng tình huống

**Files:**
- Modify: `backend/pipeline/streaming_pipeline.py:451-505`

**Interfaces:**
- Consumes: `session.tinh_huong` (Task 5); `pick_filler(..., id_tinh_huong=)` (Task 7); `lay_kho()` (Task 3).
- Produces: `metrics["tinh_huong_id"]`, `metrics["tinh_huong_diem"]`, `metrics["tinh_huong_do_phu"]`, `metrics["filler_id"]`, `metrics["filler_text"]`.

- [ ] **Step 1: Thêm hằng số độ phủ**

Cạnh `_FILLER_BO_QUA_MS`:

```python
    # Phân loại đoán trên câu CỤT thì dễ trượt: khách có thể đổi ý giữa lượt
    # ("lãi suất bao nhiêu... à không, hồ sơ cần gì"). Chỉ dùng khi bản đoán đã
    # nghe được ít nhất bằng này phần audio cuối cùng.
    # TẠM 0.5, CHƯA ĐO. `tinh_huong_do_phu` trong metrics để chốt bằng số thật.
    # Chọn sai mẩu mở đầu tệ hơn không có mẩu nào -> lưỡng lự thì về rổ chung.
    _TINH_HUONG_DO_PHU_MIN = 0.5
```

- [ ] **Step 2: Thay khối chọn câu**

Thay đoạn từ `kho = lay_kho().cau` tới hết hàm:

```python
        kho = lay_kho()
        n_audio = session.audio_len() or 1
        id_th = None
        if session.tinh_huong:
            n_th, th, diem = session.tinh_huong
            do_phu = n_th / n_audio
            metrics["tinh_huong_do_phu"] = round(do_phu, 3)
            metrics["tinh_huong_diem"] = round(diem, 3)
            if do_phu >= self._TINH_HUONG_DO_PHU_MIN:
                id_th = th
            else:
                metrics["tinh_huong_bo"] = f"độ phủ {do_phu:.2f} quá thấp"

        # Khách vừa HỎI thì "em nắm được rồi" nghe như gạt đi. Nay đọc CHÍNH
        # phiên âm dở thay vì suy từ `session.turn_count` như trước.
        duoi = list(kho.duoi)
        chu = (session.spec_stt or (0, ""))[1].lower()
        if "?" in chu or any(t in chu for t in
                            ("bao nhiêu", "thế nào", "gì", "à", "không ạ")):
            duoi = [d for d in duoi if d.hop_cau_hoi] or duoi

        dem = getattr(session, "dem_filler", None)
        if dem is None:
            dem = session.dem_filler = {}

        filler_audio, id_duoi, th_dung = self.tts.pick_filler(
            kho, session.voice_name, min_ms=can_che, dem=dem,
            id_tinh_huong=id_th, chi_duoi={d.id for d in duoi},
        )
        if not filler_audio:
            return
        dem[id_duoi] = dem.get(id_duoi, 0) + 1
        await self._send_audio(ws, filler_audio, is_filler=True,
                              turn_id=session.turn_id)
        metrics["filler_ms"] = round((time.perf_counter() - t_start) * 1000)
        metrics["filler_id"] = id_duoi
        metrics["tinh_huong_id"] = th_dung
```

`chi_duoi` là chỗ lọc `hop_cau_hoi` thật sự có tác dụng: `pick_filler` chọn theo cache chứ không theo list, nên không truyền tập id được phép thì lọc ở trên là vô nghĩa. Chữ ký đã có tham số này từ Task 7.

- [ ] **Step 3: Gọi thật, đọc metrics**

```bash
ssh win 'cd C:\duan\chat-ai; .venv\python.exe scripts\goi_qua_he_thong.py 0396130621 --giay 45'
ssh win 'Select-String -Path C:\duan\chat-ai\logs\backend.log -Pattern "filler|tinh_huong" | ForEach-Object { $_.Line } | Select-Object -Last 8'
```

Kỳ vọng: có câu đệm phát ra, `tinh_huong_id` là `None` (chưa nạp tình huống), không `Traceback`.

- [ ] **Step 4: Commit**

```bash
git add backend/pipeline/streaming_pipeline.py
git commit -m "feat(filler): _send_filler chon cau theo tinh huong

Doc session.tinh_huong, bo neu do phu audio duoi 50% - phan loai tren cau cut
de truot khi khach doi y giua luot. Ghi do phu vao metrics de con chot nguong
bang so that thay vi doan.

Loc hop_cau_hoi nay doc CHINH phien am do thay vi suy tu session.turn_count."
```

---

### Task 9: `speed` của tình huống áp cho câu trả lời của lượt

**Files:**
- Modify: `backend/pipeline/streaming_pipeline.py:101-113` (`_toc_cho_phien`)

**Interfaces:**
- Consumes: `session.tinh_huong` (Task 5); `lay_kho()` (Task 3).
- Produces: không có gì mới; đổi giá trị trả về của `_toc_cho_phien`.

- [ ] **Step 1: Thêm tra tốc theo tình huống**

```python
    @staticmethod
    def _toc_cho_phien(tts, session, voice: str | None) -> float | None:
        """Tốc đọc cho phiên: tốc của tình huống nếu có, không thì tốc của giọng,
        nhân hệ số nếu là cuộc gọi.

        Phân biệt thoại/chat bằng `session.audio_rate` - 8000 là đường thoại.
        Đó là mốc sẵn có và luôn đúng, không phải cờ tự đặt thêm.

        GIÁ PHẢI TRẢ, ghi lại cho rõ: tốc riêng theo tình huống làm khoá cache
        câu bị CHIA theo tình huống, nên tỉ lệ trúng cache giảm. Phải đo lại.
        """
        try:
            goc = None
            if session.tinh_huong:
                from backend.services.filler_store import lay_kho
                th = session.tinh_huong[1]
                for t in lay_kho().tinh_huong:
                    if t.id == th and t.speed is not None:
                        goc = t.speed
                        break
            if goc is None:
                goc = tts.toc_do_cua(voice)
            if getattr(session, "audio_rate", 16000) <= 8000:
                return goc * tts.he_so_thoai()
            return goc
        except Exception:
            return None
```

- [ ] **Step 2: Chạy toàn bộ test**

```bash
ssh win 'cd C:\duan\chat-ai; .venv\python.exe -m pytest tests -q'
```

Kỳ vọng: `0 failed`.

- [ ] **Step 3: Commit**

```bash
git add backend/pipeline/streaming_pipeline.py
git commit -m "feat(filler): toc doc cua tinh huong ap cho ca cau tra loi

Ca luot noi cung mot kieu - dem mot kieu roi tra loi kieu khac thi nghe lech
ngay cho noi.

Gia phai tra da ghi trong docstring: khoa cache cau bi CHIA theo tinh huong
nen ti le trung cache giam. Task 12 do lai."
```

---

### Task 10: Lưu `filler_id` và `tinh_huong_id` vào `latency_metrics`

Điều kiện để **đo** được phân loại đúng hay sai. Phải có trước khi chốt ba ngưỡng, và trước trang quản lý.

**Files:**
- Modify: `backend/models/db.py:207` (`_ADDED_COLUMNS`), `:474-486` (INSERT)

**Interfaces:**
- Consumes: `metrics["filler_id"]`, `metrics["tinh_huong_id"]` (Task 8).
- Produces: hai cột mới trong `latency_metrics`.

- [ ] **Step 1: Thêm cột qua `_ADDED_COLUMNS`**

Cơ chế chỉ-thêm đã có, không cần migration.

```python
    "latency_metrics": {
        "filler_id": "TEXT",
        "tinh_huong_id": "TEXT",
    },
```

Nếu khoá `"latency_metrics"` đã tồn tại trong dict thì thêm hai khoá con vào đó, đừng khai lại bảng.

- [ ] **Step 2: Ghi hai cột trong `save_session`**

```python
            "INSERT OR IGNORE INTO latency_metrics "
            "(session_id, turn_number, timestamp, stt_ms, rag_ms, ttfa_ms, "
            " total_ms, filler_id, tinh_huong_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
```

và thêm vào tuple:

```python
                    m.get("filler_id"),
                    m.get("tinh_huong_id"),
```

- [ ] **Step 3: Kiểm cột đã có sau khi khởi động lại**

```bash
ssh win 'cd C:\duan\chat-ai; .venv\python.exe -c "import sqlite3;c=sqlite3.connect(r\"data/app.db\");print([r[1] for r in c.execute(\"PRAGMA table_info(latency_metrics)\")])"'
```

Kỳ vọng: danh sách có `filler_id` và `tinh_huong_id`.

- [ ] **Step 4: Commit**

```bash
git add backend/models/db.py
git commit -m "feat(db): luu filler_id va tinh_huong_id vao latency_metrics

Pipeline van ghi filler_id vao dict metrics tu truoc, nhung save_session chi
luu 4 cot stt/rag/ttfa/total - tuc so lan dung cau dem chua bao gio luu duoc o
dau ca.

Day la dieu kien de DO duoc phan loai dung hay sai, nen phai co truoc khi chot
nguong va truoc trang quan ly."
```

---

### Task 11: Nạp 20 tình huống

**Files:**
- Create: `data/tinh_huong_seed.json`
- Create: `scripts/nap_tinh_huong.py`

**Interfaces:**
- Consumes: bảng `tinh_huong` (Task 3).
- Produces: 20 dòng trong `tinh_huong`, và các tổ hợp tiếng do Task 7 dựng ở lần khởi động sau.

- [ ] **Step 1: Viết tệp seed**

`data/tinh_huong_seed.json`, mỗi tình huống ít nhất 3 `vi_du` và mọi `mo_dau` **kết bằng dấu phẩy**. Nguồn: `knowledge/products/*.md`, `knowledge/faq/faq_banking.md`, `scenarios.examples`. Ví dụ hai mục đầu, viết đủ 20 theo cùng khuôn:

```json
{
  "tinh_huong": [
    {
      "id": "hoi_lai_suat",
      "ten": "Khách hỏi lãi suất",
      "vi_du": ["lãi suất bao nhiêu", "vay thì lãi thế nào",
                "một tháng trả bao nhiêu tiền lãi", "lãi có cao không"],
      "tu_khoa": ["lãi suất", "lãi", "phần trăm"],
      "mo_dau": ["Dạ về lãi suất thì,", "Dạ lãi suất bên em thì,"],
      "speed": null
    },
    {
      "id": "khach_noi_khong_ro",
      "ten": "Khách nói không rõ, hỏi lại",
      "vi_du": ["a lô", "gì cơ", "em nói lại đi", "nghe không rõ"],
      "tu_khoa": ["a lô", "alo", "gì cơ", "nói lại"],
      "mo_dau": ["Dạ em xin phép nhắc lại,"],
      "speed": 1.0
    }
  ]
}
```

`khach_noi_khong_ro` để `speed: 1.0` chứ không theo giọng: khách đã nghe không rõ thì đọc chậm hơn mức thường.

- [ ] **Step 2: Viết script nạp**

```python
"""Nạp tình huống từ JSON vào bảng `tinh_huong`. Chạy lại được nhiều lần.

Chạy TRÊN MÁY WIN:
    .venv\\python.exe scripts\\nap_tinh_huong.py
    .venv\\python.exe scripts\\nap_tinh_huong.py --tep data\\tinh_huong_seed.json
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from backend.config import settings


def mo_db():
    """Kết nối sqlite3 RIÊNG, không gọi `db.init_db`.

    `init_db` có bước dọn phiên "active" và sẽ đóng nhầm cuộc gọi đang chạy
    thật - xem `scripts/kiem_thu_crud.py:gieo_phien_mau`. WAL cho phép nhiều
    tiến trình cùng mở nên kết nối riêng là an toàn.
    """
    import sqlite3
    return sqlite3.connect(str(settings.db_file))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tep", default="data/tinh_huong_seed.json")
    a = ap.parse_args()

    raw = json.loads(Path(a.tep).read_text(encoding="utf-8"))
    conn, now = mo_db(), time.time()
    n = 0
    for t in raw["tinh_huong"]:
        for m in t.get("mo_dau", []):
            if not m.rstrip().endswith(","):
                print(f"BO {t['id']}: mau mo dau khong ket bang phay: {m!r}")
                break
        else:
            conn.execute(
                "INSERT INTO tinh_huong "
                "(id,ten,vi_du,tu_khoa,mo_dau,speed,bat,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,1,?,?) "
                "ON CONFLICT(id) DO UPDATE SET ten=excluded.ten, "
                "vi_du=excluded.vi_du, tu_khoa=excluded.tu_khoa, "
                "mo_dau=excluded.mo_dau, speed=excluded.speed, "
                "updated_at=excluded.updated_at",
                (t["id"], t["ten"], json.dumps(t["vi_du"], ensure_ascii=False),
                 json.dumps(t.get("tu_khoa", []), ensure_ascii=False),
                 json.dumps(t.get("mo_dau", []), ensure_ascii=False),
                 t.get("speed"), now, now))
            n += 1
    conn.commit()
    print(f"da nap {n} tinh huong")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Nạp rồi khởi động lại để dựng tiếng**

```bash
scp -q data/tinh_huong_seed.json scripts/nap_tinh_huong.py win:C:/duan/chat-ai/
ssh win 'cd C:\duan\chat-ai; .venv\python.exe scripts\nap_tinh_huong.py'
ssh win 'cd C:\duan\chat-ai; powershell -ExecutionPolicy Bypass -File scripts\start_services.ps1 -Detached -Restart'
```

Kỳ vọng: `da nap 20 tinh huong`, rồi log báo nhúng 20 tình huống và dựng khoảng 20 × số mở đầu × 42 clip. **Nếu số clip vượt 2000 thì dừng lại** và giảm rổ đuôi xuống 6 câu phủ dải trước khi dựng — 42 đuôi × 20 tình huống là 840 tổ hợp mỗi mở đầu, quá nhiều.

- [ ] **Step 4: Commit**

```bash
git add data/tinh_huong_seed.json scripts/nap_tinh_huong.py
git commit -m "feat(filler): nap 20 tinh huong tu knowledge + faq + scenarios

Moi tinh huong >= 3 vi du va moi mau mo dau ket bang phay. Nguon: 3 tep san
pham trong knowledge/, faq_banking.md (the tin dung co muc rieng), examples
trong bang scenarios, va log cuoc goi 11-08 (khach noi 'a lo', last_error
'Khong nhan dang duoc giong noi') -> tinh huong khach_noi_khong_ro.

khach_noi_khong_ro de speed 1.0 chu khong theo giong: khach da nghe khong ro
thi doc cham hon muc thuong."
```

---

### Task 12: Đo trên cuộc gọi thật và chốt ba ngưỡng

**Files:**
- Create: `scripts/do_tinh_huong.py`
- Modify: `backend/services/filler_situation.py` (`NGUONG_DIEM`), `backend/pipeline/streaming_pipeline.py` (`_TINH_HUONG_DO_PHU_MIN`) — **chỉ sửa sau khi có số**

**Interfaces:**
- Consumes: cột `filler_id`/`tinh_huong_id` (Task 10).
- Produces: ba con số thay ba giá trị tạm.

- [ ] **Step 1: Viết script đọc số từ DB**

```python
"""Doc so do phan loai tinh huong tu app.db. Xuat ASCII de doc duoc qua SSH.

Chay TREN MAY WIN:
    .venv\\python.exe scripts\\do_tinh_huong.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from backend.config import settings

# Ket noi RIENG, khong goi db.init_db: ham do don phien "active" va se dong
# nham cuoc goi dang chay that. WAL cho phep nhieu tien trinh cung mo.
import sqlite3
c = sqlite3.connect(str(settings.db_file))
print("=== so luot theo tinh huong ===")
for r in c.execute(
        "SELECT COALESCE(tinh_huong_id,'(khong co)') th, COUNT(*) n, "
        "       ROUND(AVG(ttfa_ms)) ttfa "
        "FROM latency_metrics GROUP BY th ORDER BY n DESC"):
    print(f"  {r[0]:<28} {r[1]:>4} luot   ttfa TB {r[2]}")

print("\n=== luot co cau dem nhung khong phan loai duoc ===")
r = c.execute("SELECT COUNT(*) FROM latency_metrics "
              "WHERE filler_id IS NOT NULL AND tinh_huong_id IS NULL").fetchone()
print(f"  {r[0]} luot")
```

- [ ] **Step 2: Gọi ít nhất 5 cuộc thật, mỗi cuộc 60 giây**

```bash
ssh win 'cd C:\duan\chat-ai; .venv\python.exe scripts\goi_qua_he_thong.py 0396130621 --giay 60'
```

Lặp 5 lần, mỗi lượt nói một tình huống khác nhau: hỏi lãi suất, hỏi hồ sơ, từ chối đang bận, hẹn gọi lại, nói "a lô".

- [ ] **Step 3: Đọc số và đối chiếu bằng tai**

```bash
ssh win 'cd C:\duan\chat-ai; .venv\python.exe scripts\do_tinh_huong.py'
```

Với mỗi lượt, nghe bản ghi trong `data/recordings/<ngày>/` và ghi lại: phân loại **đúng** hay **sai**, kèm `tinh_huong_do_phu` trong log. Cần ít nhất 15 lượt để con số có nghĩa.

- [ ] **Step 4: Chốt ba ngưỡng bằng số vừa đo**

- `NGUONG_DIEM`: nâng nếu có lượt phân loại **sai** với điểm trên 0,55; hạ nếu nhiều lượt **đúng** bị trượt vì dưới ngưỡng.
- `_TINH_HUONG_DO_PHU_MIN`: xem phân bố `tinh_huong_do_phu` ở các lượt sai — nếu lượt sai tập trung ở độ phủ thấp thì nâng ngưỡng.
- Số đuôi cần thiết: chạy `du_phu()` trên độ dài thật của các clip đã dựng; còn khoảng hở thì thêm câu đuôi dài đúng khoảng đó.

Sửa hằng số kèm chú thích ghi **số đo và ngày đo**, thay chữ "TẠM, CHƯA ĐO".

- [ ] **Step 5: Commit**

```bash
git add scripts/do_tinh_huong.py backend/services/filler_situation.py backend/pipeline/streaming_pipeline.py
git commit -m "measure(filler): chot ba nguong bang so do tren cuoc goi that

Thay ba gia tri tam bang so do duoc, va thay chu 'TAM, CHUA DO' trong chu
thich bang so do that kem ngay do."
```

---

## Self-review

**Spec coverage.** Mô hình dữ liệu → Task 3. Phân loại trong `speculate` → Task 5. Ghép chuỗi một phát ngôn → Task 6, 7. Luật cứng chỉ-lấy-từ-cache → Task 7. `doc.speed` cho cả câu trả lời → Task 9. Tách module không torch → Task 2, 3, 6. Xuống cấp có kiểm soát → Task 4 (nhúng lỗi), 7 (thiếu cache), 8 (độ phủ thấp). 20 tình huống → Task 11. Ba ngưỡng chưa đo → Task 12. Sửa 5 test đỏ → Task 1. `filler_id` vào DB → Task 10.

**Chưa phủ, chuyển sang kế hoạch sau:** trang quản lý và API `/api/cau-dem/*`. Đó là mục "Trang quản lý" trong spec, tách thành `2026-08-11-cau-dem-trang-quan-ly.md` vì nó là một khối làm được và test được riêng, còn kế hoạch này đã đủ để tính năng **chạy trên cuộc gọi thật** — đúng thứ người dùng yêu cầu.

**Type consistency.** `pick_filler` trả 3 giá trị `(wav, id_duoi, id_th)` ở Task 7 và Task 8 nhận đúng 3. Khoá cache `(giọng, id_tình_huống, id_đuôi)` dùng thống nhất ở Task 7. `session.tinh_huong` là tuple 3 phần tử `(n, id, điểm)`, đặt ở Task 5, đọc ở Task 8 và Task 9. `chon_tinh_huong` trả `(id | None, điểm)` ở Task 2, dùng đúng ở Task 5.

**Một chỗ mâu thuẫn đã sửa trong lúc soát:** Task 8 lọc `hop_cau_hoi` trên `kho.duoi` nhưng `pick_filler` chọn theo cache chứ không theo list, nên lọc sẽ vô tác dụng. Đã thêm yêu cầu truyền `chi_duoi: set[str] | None` vào `pick_filler` ở Step 2 của Task 8.

**Một rủi ro về số lượng đã ghi thành chốt chặn:** 20 tình huống × 42 đuôi là 840 tổ hợp mỗi mẩu mở đầu — quá nhiều. Task 11 Step 3 buộc dừng lại nếu vượt 2000 clip và giảm rổ đuôi xuống 6 câu phủ dải trước khi dựng.
