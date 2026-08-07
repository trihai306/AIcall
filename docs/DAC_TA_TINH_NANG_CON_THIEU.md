# Đặc tả tính năng còn thiếu — Bot autocall AI

> Đối chiếu **Điều 6 Hợp đồng khoán gọn** ký ngày 05/11/2025 (Phạm Minh Đức ↔ Nguyễn Chí Hải)
> với mã nguồn hiện tại của repo `chat-ai`.
> Lập ngày 05/08/2026.

**Mục đích:** liệt kê đúng những gì hợp đồng yêu cầu mà code chưa có, mô tả đủ chi tiết
để bắt tay triển khai và để hai bên nghiệm thu theo mốc thanh toán 30–50–70–100.

---

> ## ⚠️ Tài liệu này là bản ĐẶC TẢ BAN ĐẦU — đã được thực hiện
>
> Toàn bộ F2–F19 đã lập trình xong. Kết quả và trạng thái nghiệm thu từng mục:
> **[BAO_CAO_THUC_HIEN.md](BAO_CAO_THUC_HIEN.md)**. Hướng dẫn vận hành:
> **[HUONG_DAN_SU_DUNG.md](HUONG_DAN_SU_DUNG.md)**.
>
> **Hai thay đổi phạm vi do bên A quyết định sau khi đọc bản đặc tả này:**
>
> 1. **F1 (độ trễ 200–300 ms) — BỎ.** Bên A chốt giữ mức 1000 ms hiện tại. Mục
>    F1 bên dưới giữ nguyên để lưu vết, nhưng không thực hiện.
> 2. **Zalo — BỎ, chỉ làm Telegram.** Mục F11 bên dưới mô tả cả hai; phần Zalo
>    không thực hiện. Lý do kỹ thuật: Zalo OA cần Official Account đã duyệt và
>    access token phải làm mới định kỳ, thời gian duyệt nằm ngoài tầm kiểm soát.

---

## 1. Mốc thanh toán theo hợp đồng

| Mốc | Nội dung nghiệm thu (nguyên văn HĐ) | Trạng thái |
|-----|--------------------------------------|------------|
| 30% | Tối ưu tốc độ phản hồi của bot | Gần xong — **chưa đạt ngưỡng số trong HĐ** |
| 50% | Tối ưu giọng | Cơ bản xong — thiếu phần kiểm chứng giọng vùng miền |
| 70% | Các chức năng cơ bản của dashboard | **Thiếu phần lớn** |
| 100% | Interfere, giao diện cuối, hoàn thiện bàn giao source | Chưa bắt đầu |

Bảo hành: 6 tháng kể từ bàn giao.

---

## 2. Bảng đối chiếu tổng

Ký hiệu: **✅ đã có** · **⚠️ có một phần** · **❌ chưa có**

### 2.1 Bot gọi ra

| Mã | Yêu cầu hợp đồng | TT | Vị trí trong code / ghi chú |
|----|------------------|----|-----------------------------|
| — | Chạy offline 100%, không gọi API web ngoài | ✅ | Ollama + PhoWhisper + F5-TTS + ChromaDB, toàn bộ chạy nội bộ |
| — | Giọng tự nhiên, có thể training | ✅ | `training/voice/`, tab **Training giọng**, `backend/api/voice_training.py` |
| — | Train giọng theo một form thống nhất | ✅ | `voice_training.py` — kịch bản thu 60 câu, upload, prepare, train qua UI |
| — | Kết nối để gọi qua điện thoại | ✅ | `dialer_service.py` (dial_url), `adb_service.py`, `phone_call_service.py` |
| — | Ngắt khi khách nói chen ngang rồi tiếp tục luồng | ✅ | `websocket.py:172` (`barge_in`), `phone_call_service.py:676` (`huy_luot_dang_chay`) |
| **F1** | Độ trễ **200–300 ms** từ lúc khách nói xong | ❌ | Ngưỡng "ĐẠT" đang cài trong code là `ttfa < 1000` (`streaming_pipeline.py:698`); README đặt mục tiêu 500–650 ms |
| **F2** | Nhận diện giọng vùng miền | ⚠️ | PhoWhisper vốn đa vùng miền nhưng **chưa có bộ đo, chưa có số liệu, chưa có xử lý riêng** |
| **F16** | Kết nối cơ sở dữ liệu (ví dụ bảng Excel) để truy cứu và tư vấn | ❌ | RAG chỉ nạp `.md` trong `knowledge/`; không đọc Excel/CSV/SQL |
| **F3** | Train kịch bản đầu vào theo form thống nhất, dễ mở rộng sang ngành khác | ⚠️ | Có train LLM bằng `.jsonl` (`api/training.py`) nhưng **không có khái niệm "kịch bản" chọn được**; prompt cứng trong `llm_service.py:25` |

### 2.2 Bot nhận cuộc gọi vào

| Mã | Yêu cầu hợp đồng | TT | Ghi chú |
|----|------------------|----|---------|
| **F17** | Tiếp nhận cuộc gọi vào, giao tiếp tự nhiên như bot gọi ra | ❌ | Chỉ đọc được trạng thái `ringing` (`adb_service.py:32`); **không có tự bắt máy + mở phiên AI** |
| **F18** | Chuyển tiếp đến số điện thoại cài sẵn khi vượt giới hạn đã training | ❌ | Chưa có gì |

### 2.3 Dashboard

| Mã | Yêu cầu hợp đồng | TT | Ghi chú |
|----|------------------|----|---------|
| **F3** | B1 — Chọn kịch bản | ❌ | Không có bảng kịch bản, không có UI chọn |
| **F4** | B2 — Tải file khách hàng: name, sđt, **thêm 1–2 trường** để lọc khi xem báo cáo | ⚠️ | Import CSV đã có (`api/phones.py:103`); chỉ có sẵn `name/product/note`, **không có trường tuỳ biến** |
| **F5** | B2 — Nhập từ chiến dịch khác (số đã gọi nhưng bận / không nhấc máy) | ❌ | Chưa có |
| **F6** | Chạy chiến dịch tự động (ngầm định của B1→B2→B3) | ❌ | Chỉ có `POST /api/phones/call-next` bấm tay từng số |
| **F7** | B3 — Tắt máy khi vào hộp thư thoại | ❌ | Chưa có phát hiện hộp thư thoại |
| **F8** | B3 — Nhận diện giới tính | ❌ | Chưa có |
| **F9** | B3 — Gọi lại khi không bắt máy / máy bận / vào hộp thư thoại; số lần gọi lại; gọi lại sau bao nhiêu phút | ❌ | Có cột `attempts` nhưng **không có lịch gọi lại** |
| **F10** | B3 — Ngày bắt đầu chạy, khung giờ chạy | ❌ | Chưa có |
| **F11** | B3 — Gửi báo cáo qua Zalo hoặc Telegram | ❌ | Chưa có |

### 2.4 Báo cáo

| Mã | Yêu cầu hợp đồng | TT | Ghi chú |
|----|------------------|----|---------|
| **F15** | Lọc theo trạng thái (thành công, thất bại…) | ⚠️ | Lọc được ở danh bạ và phiên gọi, **chưa có trang báo cáo cuộc gọi hợp nhất** |
| **F14** | Lọc theo chất lượng (có phản hồi, không phản hồi, dập máy) | ❌ | Chưa có trường chất lượng |
| **F15** | Lọc theo thời lượng gọi | ❌ | Có `duration_seconds` nhưng không lọc được |
| **F14** | Gắn nhãn (quan tâm, không quan tâm, follow chăm sóc thêm) | ❌ | Chưa có |
| **F12** | Có ghi âm | ❌ | **Không lưu file audio cuộc gọi ở bất kỳ đâu** |
| — | Lưu text của từng cuộc gọi | ✅ | Bảng `conversation_turns` (`models/db.py:43`) |
| **F13** | Tổng hợp ý chính của từng cuộc gọi | ❌ | Chưa có |

**Tổng kết: 18 hạng mục cần làm** (F1–F18), cộng F19 là phần bàn giao của mốc 100%.

---

## 3. Lưu ý chung trước khi triển khai

**CSDL không có migration.** `backend/models/db.py:8` ghi rõ: đổi schema thì xoá
`data/app.db` rồi khởi động lại. Kế hoạch dưới đây thêm nhiều bảng và nhiều cột,
nên **trước khi bắt đầu mốc 70 phải quyết định**: giữ nguyên chính sách này
(chấp nhận mất dữ liệu thử nghiệm) hay bổ sung `PRAGMA user_version` + migration.
Khuyến nghị: bổ sung migration ngay ở F6, vì từ lúc chạy chiến dịch thật thì dữ
liệu danh bạ và lịch sử gọi trở thành dữ liệu sản xuất, không xoá được nữa.

**Toàn bộ tính năng mới phải giữ nguyên ràng buộc offline** của Điều 6: không gọi
API web ngoài. Ngoại lệ duy nhất được hợp đồng cho phép là F11 (gửi báo cáo qua
Zalo/Telegram) — đây là kênh thông báo ra ngoài, không phải phụ thuộc suy luận.

**Mọi ghi vào SQLite phải qua `asyncio.to_thread`** và dùng `db.write_lock`,
theo đúng khuôn đang dùng ở `contacts_db.py` — luồng thoại không được chờ ổ đĩa.

---

## 4. Đặc tả chi tiết

### MỐC 30% — Tốc độ phản hồi

---

#### F1. Đạt độ trễ 200–300 ms từ lúc khách nói xong

**Yêu cầu HĐ:** *"Độ trễ: 200-300mls từ thời điểm khách nói xong (dựa trên cấu hình
máy: GPU RTX 4070, CPU 16–24 luồng, RAM 64 GB)"*

**Hiện trạng:** ngân sách thời gian hiện tại cộng lại đã vượt mốc:

| Chặng | Hiện tại | Nguồn |
|-------|----------|-------|
| VAD chốt hết câu | 220 ms | `config.py:54` `vad_min_silence_ms` |
| STT PhoWhisper-small | ~90 ms | README |
| RAG | ~100 ms (đã có đoán trước) | `streaming_pipeline.py:460` |
| LLM TTFT | ~70 ms | README |
| TTS mảnh đầu | ~130 ms | README |
| **Cộng** | **~510–610 ms** | |

Ngưỡng cảnh báo trong code đang là `ttfa < 1000` (`streaming_pipeline.py:698`) —
tức là code hiện chưa coi 300 ms là mục tiêu.

**Hướng xử lý (theo thứ tự hiệu quả / rủi ro):**

1. **Hạ `vad_min_silence_ms` 220 → 120–150 ms**, bù lại bằng cơ chế huỷ lượt khi
   khách nói tiếp (đã có sẵn `barge_in`). Đây là khoản cắt lớn nhất và rẻ nhất:
   riêng nó đã lấy lại 70–100 ms.
2. **Chạy STT trên luồng nói dở (streaming/partial)** thay vì chờ hết câu: nạp
   audio vào PhoWhisper theo cửa sổ trượt, khi VAD chốt thì chỉ còn phải xử lý
   đoạn đuôi. Cắt được phần lớn 90 ms.
3. **Bắt đầu LLM bằng bản ghi tạm** ngay khi STT có kết quả sơ bộ, huỷ và chạy lại
   nếu bản ghi cuối khác. Cơ chế "đoán trước" đã có ở RAG, mở rộng sang LLM.
4. **Giữ filler tức thì** làm lớp che: khách nghe "Dạ…" trong lúc mảnh thật đang
   sinh. Lưu ý mục 3 đã ghi trong `streaming_pipeline.py:331` — `ttfa_ms` đo tới
   mảnh THẬT nên nhìn một mình con số này sẽ tưởng khách chờ lâu hơn thực tế.

**Tiêu chí nghiệm thu:**
- Chạy `POST /api/benchmark/full` 30 lượt trên máy cấu hình HĐ (RTX 4070, 16–24
  luồng, 64 GB): **p50 ≤ 300 ms, p90 ≤ 400 ms**, đo từ mốc VAD chốt hết câu tới
  byte audio thật đầu tiên.
- Đổi ngưỡng "ĐẠT" trong `streaming_pipeline.py` từ 1000 xuống 300, log rõ chặng
  nào vượt ngân sách.
- Có bảng phân rã thời gian từng chặng trong tab **Benchmark**.

**Ước lượng:** 4–6 ngày.

---

### MỐC 50% — Giọng

---

#### F2. Nhận diện giọng vùng miền

**Yêu cầu HĐ:** *"Có thể nhận diện giọng vùng miền..."*

**Hiện trạng:** dùng PhoWhisper-small vốn đã huấn luyện trên tiếng Việt nhiều
vùng, nhưng **chưa có bất kỳ số đo nào** để nói là đạt hay không đạt. Không thể
nghiệm thu một tính năng chưa từng được đo.

**Thiết kế:**

- **Bộ mẫu kiểm thử:** `data/test_vung_mien/{bac,trung,nam}/` — mỗi vùng ≥ 20 câu
  thoại thật (đi qua đường điện thoại 8 kHz, không phải file thu phòng sạch),
  kèm bản ghi chuẩn `.txt`.
- **Script đo:** `scripts/do_vung_mien.py` — chạy toàn bộ mẫu qua đúng đường xử
  lý thật (`stt_service.transcribe`), xuất WER/CER theo từng vùng.
- **Xử lý khi lệch:** nếu một vùng có WER cao hơn hẳn, hai lựa chọn theo thứ tự:
  (a) mồi từ vựng theo vùng qua `initial_prompt` của faster-whisper;
  (b) fine-tune PhoWhisper trên mẫu vùng đó.
- **UI:** thêm ô chọn "Vùng miền khách hàng" ở tab **Cài đặt** (`bac`/`trung`/`nam`/`tự động`),
  lưu vào `.env` là `stt_vung_mien`.

**Tiêu chí nghiệm thu:** có báo cáo WER ba vùng; **WER mỗi vùng ≤ 15%** trên bộ
mẫu qua đường điện thoại; chênh lệch WER giữa vùng tốt nhất và tệ nhất ≤ 5 điểm.

**Ước lượng:** 3–4 ngày (phần lớn là thu và gán nhãn mẫu).

---

### MỐC 70% — Dashboard

Đây là khối lớn nhất. Thứ tự dưới đây là thứ tự phụ thuộc, nên làm đúng thứ tự.

---

#### F3. Quản lý kịch bản (B1 — Chọn kịch bản)

**Yêu cầu HĐ:** *"B1: Chọn kịch bản — Gọi ra chào sản phẩm theo một vài kịch bản
nhất định"* và *"Có thể train kịch bản đầu vào, thống nhất 1 form train => dễ mở
rộng sang các ngành khác"*

**Hiện trạng:** system prompt cứng trong `llm_service.py:25`, gắn chặt với ngành
ngân hàng (`bank_name`, `agent_name`, quy tắc xưng hô). Muốn đổi sang ngành khác
phải sửa code.

**Thiết kế:**

*CSDL* — bảng mới trong `models/db.py`:
```sql
CREATE TABLE IF NOT EXISTS scenarios (
    scenario_id  TEXT PRIMARY KEY,
    name         TEXT NOT NULL,              -- "Vay tín chấp Q1", "Bảo hiểm nhân thọ"
    industry     TEXT NOT NULL DEFAULT '',   -- ngân hàng | bảo hiểm | bất động sản | ...
    org_name     TEXT NOT NULL DEFAULT '',   -- thay {bank_name}
    agent_name   TEXT NOT NULL DEFAULT '',   -- thay {agent_name}
    opening_line TEXT NOT NULL DEFAULT '',   -- câu chào mở đầu, đọc ngay khi khách bắt máy
    rules        TEXT NOT NULL DEFAULT '',   -- các quy tắc bắt buộc, mỗi dòng một quy tắc
    examples     TEXT NOT NULL DEFAULT '',   -- ví dụ hỏi-đáp mẫu (JSON list)
    knowledge_tag TEXT NOT NULL DEFAULT '',  -- lọc mảnh RAG theo nhãn này
    max_turns    INTEGER NOT NULL DEFAULT 20,-- vượt thì chuyển tiếp (xem F18)
    is_default   INTEGER NOT NULL DEFAULT 0,
    created_at   REAL NOT NULL
);
```
Thêm cột `scenario_id TEXT` vào bảng `campaigns` và `call_sessions`.

*Backend* — tách `SYSTEM_PROMPT_TEMPLATE` thành khung cố định + phần nạp từ kịch
bản. Khung giữ nguyên các quy tắc chống lỗi đã đúc kết (mục 3 về con số phải lấy
từ THÔNG TIN THAM KHẢO, mục 10–11 về bản ghi sai chính tả) — **không được bỏ**,
vì đó là các luật đã sửa lỗi thực tế. Phần thay được: tên tổ chức, tên nhân viên,
câu chào, ví dụ, quy tắc riêng ngành.

*File mới:* `backend/models/scenarios_db.py`, `backend/api/scenarios.py`.
*Sửa:* `backend/services/llm_service.py` (`build_system_prompt` nhận `scenario: dict`),
`backend/models/db.py` (schema), `backend/main.py` (đăng ký router).

*API:*
```
GET    /api/scenarios              danh sách
POST   /api/scenarios              tạo
GET    /api/scenarios/{id}         chi tiết
PATCH  /api/scenarios/{id}         sửa
DELETE /api/scenarios/{id}         xoá
POST   /api/scenarios/{id}/test    chạy thử 1 lượt hội thoại, trả về prompt đã dựng + câu trả lời
POST   /api/scenarios/import       nhập từ file JSON/YAML (form train thống nhất)
GET    /api/scenarios/template     tải form mẫu
```

*UI* — tab mới **Kịch bản**: danh sách, form soạn thảo, nút "Chạy thử", nút
"Nhập/Xuất". Trong tab **Danh bạ gọi**, thêm ô chọn kịch bản cho chiến dịch.

**Tiêu chí nghiệm thu:** tạo được một kịch bản ngành **ngoài ngân hàng** (ví dụ
bán bảo hiểm) hoàn toàn qua UI, không sửa dòng code nào, và bot gọi thử đúng
theo kịch bản đó.

**Ước lượng:** 4–5 ngày.

---

#### F4. Trường tuỳ biến cho danh bạ (B2)

**Yêu cầu HĐ:** *"Tải lên file khách hàng: có các trường cơ bản như name, sđt,
thêm 1 2 trường nữa để điền thêm thông tin để lúc xem lại báo cáo cuộc gọi dễ
dàng lọc thông tin"*

**Hiện trạng:** `contacts` có sẵn `name`, `product`, `note` — dùng tạm được
nhưng tên cột cố định, không lọc được theo giá trị, và người dùng không tự đặt
được nhãn cột.

**Thiết kế:**

*CSDL* — thêm vào `contacts`:
```sql
field1 TEXT NOT NULL DEFAULT '',
field2 TEXT NOT NULL DEFAULT '',
field3 TEXT NOT NULL DEFAULT '',
```
và vào `campaigns` (nhãn hiển thị của ba cột đó, theo từng chiến dịch):
```sql
field1_label TEXT NOT NULL DEFAULT '',
field2_label TEXT NOT NULL DEFAULT '',
field3_label TEXT NOT NULL DEFAULT '',
```
Thêm index: `CREATE INDEX ix_contacts_field1 ON contacts(field1);`

Ba cột cố định thay vì bảng key-value phụ: lọc bằng SQL thẳng, không phải JOIN,
và hợp đồng chỉ yêu cầu "1 2 trường nữa".

*Backend* — `api/phones.py`: bộ nhận diện tiêu đề CSV (`HEADER_ALIASES`, dòng 14)
mở rộng để cột lạ tự map vào `field1..3` theo thứ tự xuất hiện, đồng thời ghi
nhãn cột vào chiến dịch. `EDITABLE_FIELDS` trong `contacts_db.py:28` thêm ba cột.
`list_contacts` nhận thêm `field1=`, `field2=`, `field3=` để lọc.

*UI* — bảng danh bạ hiển thị cột theo nhãn của chiến dịch; thêm ô lọc theo từng
trường; màn hình import hiện bảng xem trước ánh xạ cột trước khi ghi.

**Tiêu chí nghiệm thu:** import file Excel-xuất-CSV có cột "Chi nhánh" và "Nhóm
khách" → hai cột hiện đúng nhãn trong bảng, lọc theo được, và xuất hiện trong
báo cáo cuộc gọi (F15).

**Ước lượng:** 2–3 ngày.

---

#### F5. Nhập số từ chiến dịch khác

**Yêu cầu HĐ:** *"Nhập từ chiến dịch khác (các số đã gọi nhưng bận, hoặc không
nhấc máy của chiến dịch khác...)"*

**Hiện trạng:** chưa có. `import_contacts` chỉ nhận danh sách từ file.

**Thiết kế:**

*API mới:*
```
POST /api/phones/campaigns/{id}/import-from
body: {
  "source_campaign_id": "cp_xxx",
  "statuses": ["busy", "no_answer"],   // trạng thái muốn lấy
  "min_attempts": 0,                    // đã gọi ít nhất bao nhiêu lần
  "max_attempts": 3,                    // và nhiều nhất bao nhiêu lần
  "move": false                         // false = nhân bản sang, true = chuyển hẳn
}
→ { "imported": 128, "skipped": 4 }
```

*Backend* — `contacts_db.py`: hàm `import_from_campaign(...)`. Vì `contacts.phone`
là UNIQUE, một số chỉ tồn tại ở một chiến dịch tại một thời điểm. Do đó:
- `move=true`: `UPDATE contacts SET campaign_id=?, status='pending', attempts=0`
- `move=false`: giữ lịch sử `call_attempts`, đổi `campaign_id`, reset `status` về
  `pending` (bản chất vẫn là chuyển; ghi rõ điều này trên UI để người dùng không
  hiểu nhầm là nhân bản).

*UI* — trong tab **Danh bạ gọi**, nút "Nhập từ chiến dịch khác" mở hộp thoại:
chọn chiến dịch nguồn, tick các trạng thái, xem trước số lượng, xác nhận.

**Tiêu chí nghiệm thu:** lấy được đúng tập số `busy` + `no_answer` từ chiến dịch
cũ sang chiến dịch mới, lịch sử gọi cũ vẫn tra được ở `GET /api/phones/contacts/{id}/attempts`.

**Ước lượng:** 1–2 ngày.

---

#### F6. Bộ chạy chiến dịch tự động (auto-dialer)

**Yêu cầu HĐ:** ngầm định của toàn bộ luồng B1 → B2 → B3. Không có bộ chạy này
thì F7–F11 không có chỗ bám.

**Hiện trạng:** chỉ có `POST /api/phones/call-next` — bấm tay từng số một.

**Thiết kế:**

*CSDL* — thêm vào `campaigns`:
```sql
scenario_id      TEXT REFERENCES scenarios(scenario_id),
device_ids       TEXT NOT NULL DEFAULT '',   -- JSON list, chạy song song nhiều máy
concurrency      INTEGER NOT NULL DEFAULT 1, -- số cuộc gọi đồng thời
started_at       REAL,
paused_at        REAL
```

*File mới:* `backend/services/campaign_runner.py`

Vòng chạy, mỗi chiến dịch một task `asyncio`:
```
while chiến dịch đang chạy:
    nếu ngoài khung giờ cho phép (F10):  ngủ tới đầu khung kế tiếp
    lấy số kế tiếp = số 'pending' hoặc số tới hạn gọi lại (F9)
    nếu hết số:  đánh dấu chiến dịch 'done', thoát
    với mỗi thiết bị rảnh (tới mức concurrency):
        bấm số → mở phiên AI (kịch bản của chiến dịch)
        theo dõi tới khi cuộc gọi kết thúc
        ghi kết quả + xếp lịch gọi lại nếu cần
    ngủ ngắn
```

Quan trọng: một task cho mỗi chiến dịch, **không phải một task cho mỗi số** — để
tạm dừng/tiếp tục là thao tác trên một đối tượng duy nhất, và để `concurrency`
là hàng rào thật chứ không phải gợi ý.

*API:*
```
POST /api/phones/campaigns/{id}/start
POST /api/phones/campaigns/{id}/pause
POST /api/phones/campaigns/{id}/resume
POST /api/phones/campaigns/{id}/stop
GET  /api/phones/campaigns/{id}/progress   → {đang gọi, xong, còn lại, tỉ lệ nghe máy}
WS   /ws/campaign/{id}                      → đẩy tiến độ realtime lên UI
```

*UI* — tab **Danh bạ gọi**: nút Chạy/Tạm dừng/Dừng, thanh tiến độ, danh sách
cuộc gọi đang diễn ra kèm trạng thái từng máy.

**Tiêu chí nghiệm thu:** nạp 20 số, bấm Chạy, hệ thống tự gọi lần lượt hết 20 số
qua 2 máy song song, tạm dừng và tiếp tục được, tắt app rồi mở lại thì chiến dịch
ở trạng thái `paused` chứ không mất số nào.

**Ước lượng:** 5–7 ngày. Đây là hạng mục nặng nhất của mốc 70%.

---

#### F7. Phát hiện hộp thư thoại và tự tắt máy

**Yêu cầu HĐ:** *"Tắt máy khi vào hộp thư thoại (alo khách lâu quá không nhấc
máy thì sẽ vào hộp thư thoại)"*

**Hiện trạng:** chưa có. Bot sẽ tư vấn hết kịch bản cho hộp thư thoại, tốn thời
gian máy và tốn tiền cước.

**Thiết kế:** hộp thư thoại có ba dấu hiệu, dùng cả ba rồi cho điểm:

1. **Lời chào dài không ngắt** — hộp thư thoại nói liên tục 8–15 giây rồi im hẳn;
   người thật nói 1–3 giây ("A lô?") rồi chờ. Đo bằng VAD sẵn có: đoạn nói đầu
   tiên > 6 giây → nghi ngờ cao.
2. **Từ khoá trong bản ghi STT** — "hộp thư thoại", "để lại lời nhắn", "sau tiếng
   bíp", "thuê bao quý khách vừa gọi", "hiện không liên lạc được". Danh sách để
   trong `backend/services/voicemail_detect.py`, sửa được từ UI.
3. **Tiếng bíp** — tone đơn tần 1000–1400 Hz kéo 300–500 ms. Đã có sẵn hàm dò
   tone `_co_tone` ở `phone_call_service.py:753`, dùng lại.

Kết luận là hộp thư thoại khi: có từ khoá, **hoặc** (đoạn nói đầu > 6 giây **và**
có tiếng bíp).

*File mới:* `backend/services/voicemail_detect.py`
*Sửa:* `phone_call_service.py` — gọi bộ dò trong `_read_loop` ở 15 giây đầu cuộc gọi.
*Cấu hình chiến dịch:* `on_voicemail` = `hangup` | `leave_message` | `continue`.

**Tiêu chí nghiệm thu:** trên 20 cuộc gọi thật vào số đã tắt máy/không nghe,
phát hiện đúng ≥ 18 lần và **không nhận nhầm người thật lần nào** trong 20 cuộc
gọi có người nghe. Nhận nhầm người thật là lỗi nặng hơn bỏ sót hộp thư thoại.

**Ước lượng:** 3–4 ngày (phần lớn là gọi thật để lấy mẫu).

---

#### F8. Nhận diện giới tính

**Yêu cầu HĐ:** *"Nhận diện giới tính"*

**Hiện trạng:** chưa có.

**Thiết kế:** phân loại theo cao độ giọng (F0) — chạy offline, nhẹ, không cần
model thêm:
- Ước lượng F0 trên 2–3 giây đầu khách nói. Đã có sẵn `_uoc_luong_chu_ky` ở
  `phone_call_service.py:251` (dò chu kỳ để tăng tuần hoàn) — F0 = tần số lấy mẫu
  chia chu kỳ, dùng lại được ngay.
- Ngưỡng cho tiếng Việt qua đường thoại 8 kHz: F0 trung vị < 165 Hz → nam;
  > 190 Hz → nữ; ở giữa → `không rõ`.
- Chỉ tính trên các khung có tiếng nói (VAD đã lọc), lấy **trung vị** chứ không
  lấy trung bình — trung bình bị một khung nhiễu kéo lệch.

*Dùng để làm gì:* chọn cách xưng hô ("anh" / "chị") trong prompt, và làm cột lọc
trong báo cáo.

*CSDL:* thêm `gender TEXT DEFAULT ''` vào `call_sessions` (`male` | `female` | `unknown`).
*File mới:* `backend/services/gender_detect.py`

**Tiêu chí nghiệm thu:** đúng ≥ 85% trên 40 cuộc gọi thật đã gán nhãn tay; khi
không chắc thì trả `unknown` và bot dùng "anh/chị" như hiện nay chứ không đoán bừa.

**Ước lượng:** 2 ngày.

---

#### F9. Lịch gọi lại

**Yêu cầu HĐ:** *"Gọi lại nếu không bắt máy / Gọi lại nếu máy bận / Gọi lại nếu
vào hộp thư thoại / Số lần gọi lại, gọi lại sau bao nhiêu phút"*

**Hiện trạng:** có cột `attempts` đếm số lần đã gọi, nhưng **không có lịch**.

**Thiết kế:**

*CSDL* — thêm vào `campaigns`:
```sql
retry_no_answer   INTEGER NOT NULL DEFAULT 1,  -- 0 = không gọi lại
retry_busy        INTEGER NOT NULL DEFAULT 1,
retry_voicemail   INTEGER NOT NULL DEFAULT 0,
retry_max         INTEGER NOT NULL DEFAULT 3,  -- trần tổng số lần gọi một số
retry_delay_min   INTEGER NOT NULL DEFAULT 30  -- phút giữa hai lần
```
và vào `contacts`:
```sql
next_retry_at REAL,        -- NULL = không có lịch
retry_reason  TEXT NOT NULL DEFAULT ''
```
Index: `CREATE INDEX ix_contacts_retry ON contacts(next_retry_at) WHERE next_retry_at IS NOT NULL;`

*Backend* — trong `campaign_runner`, khi một cuộc gọi kết thúc:
```
nếu kết quả ∈ {no_answer, busy, voicemail} và bật gọi lại cho loại đó
   và contacts.attempts < campaigns.retry_max:
      next_retry_at = now + retry_delay_min * 60
      status = 'pending'
ngược lại:
      next_retry_at = NULL, status = kết quả cuối
```
Bộ chọn số kế tiếp lấy theo thứ tự: số tới hạn gọi lại trước, rồi mới tới số
chưa gọi lần nào.

*UI* — tab **Danh bạ gọi**, khối "Cài đặt khác": ba ô tick + hai ô số. Cột
"Gọi lại lúc" trong bảng danh bạ.

**Tiêu chí nghiệm thu:** đặt `retry_delay_min=1`, gọi một số đang bận → sau đúng
1 phút hệ thống tự gọi lại, đủ `retry_max` lần thì dừng và số chuyển sang trạng
thái cuối, không gọi thêm.

**Ước lượng:** 2–3 ngày.

---

#### F10. Ngày bắt đầu chạy và khung giờ chạy

**Yêu cầu HĐ:** *"Ngày bắt đầu chạy, khung giờ chạy"*

**Hiện trạng:** chưa có.

**Thiết kế:**

*CSDL* — thêm vào `campaigns`:
```sql
start_date   TEXT NOT NULL DEFAULT '',   -- 'YYYY-MM-DD', rỗng = chạy ngay
end_date     TEXT NOT NULL DEFAULT '',
call_windows TEXT NOT NULL DEFAULT '',   -- JSON: [{"days":[1,2,3,4,5],"from":"08:30","to":"11:30"},
                                         --        {"days":[1,2,3,4,5],"from":"13:30","to":"17:00"}]
timezone     TEXT NOT NULL DEFAULT 'Asia/Ho_Chi_Minh'
```

*Backend* — `campaign_runner` kiểm tra trước mỗi lần bấm số. Ngoài khung giờ thì
**ngủ tới đầu khung kế tiếp** chứ không hỏi lại mỗi giây. Cuộc gọi đang diễn ra
khi hết khung giờ được nói nốt, không cắt ngang giữa câu.

Mặc định khi tạo chiến dịch mới: 08:00–11:30 và 13:30–17:00, thứ 2–6. Gọi ngoài
giờ hành chính là cách nhanh nhất để bị khách chặn số.

*UI* — bộ chọn ngày + các khung giờ thêm/bớt được, có xem trước "Lần gọi kế tiếp:
08:00 thứ Hai 10/08".

**Tiêu chí nghiệm thu:** đặt khung 14:00–14:05, bấm Chạy lúc 13:50 → hệ thống
chờ, tự bắt đầu lúc 14:00, tự dừng lúc 14:05 và cuộc gọi đang nói được nói nốt.

**Ước lượng:** 2 ngày.

---

#### F11. Gửi báo cáo qua Zalo / Telegram

**Yêu cầu HĐ:** *"Gửi báo cáo qua zalo hoặc telegram (bot gửi lại text sau mỗi
cuộc gọi thành công, hoặc tổng hợp theo form những ý chính...)"*

**Hiện trạng:** chưa có.

**Thiết kế:**

*Telegram* — dùng Bot API (`https://api.telegram.org/bot<token>/sendMessage`).
Chỉ cần token + chat_id, không cần duyệt.
*Zalo* — Zalo OA Message API, cần Official Account đã duyệt và access token có
hạn (làm mới bằng refresh token). **Cần hỏi bên A đã có OA chưa** — nếu chưa,
làm Telegram trước và để Zalo lại, vì thời gian duyệt OA nằm ngoài tầm kiểm soát.

*CSDL:*
```sql
CREATE TABLE IF NOT EXISTS notify_channels (
    channel_id TEXT PRIMARY KEY,
    kind       TEXT NOT NULL,            -- telegram | zalo
    name       TEXT NOT NULL,
    config     TEXT NOT NULL DEFAULT '', -- JSON: token, chat_id / oa_id, access_token
    events     TEXT NOT NULL DEFAULT '', -- JSON: ["call_success","daily_summary","campaign_done"]
    enabled    INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL
);
```

*File mới:* `backend/services/notify_service.py`, `backend/api/notify.py`

*Ba loại tin:*
1. **Sau mỗi cuộc gọi thành công** — tên, số, thời lượng, nhãn, 2–3 dòng ý chính (F13).
2. **Tổng hợp cuối ngày** — tổng cuộc gọi, tỉ lệ nghe máy, số khách quan tâm, top lý do từ chối.
3. **Chiến dịch chạy xong**.

Gửi thất bại thì thử lại 3 lần với giãn cách tăng dần, rồi bỏ và ghi log —
**không được để việc gửi tin chặn vòng chạy chiến dịch**.

*UI* — tab **Cài đặt**, khối "Kênh thông báo": thêm kênh, nút "Gửi thử".

**Tiêu chí nghiệm thu:** cấu hình một bot Telegram, chạy chiến dịch 5 số → nhận
đủ 5 tin sau mỗi cuộc và 1 tin tổng hợp; rút mạng giữa chừng thì chiến dịch vẫn
chạy tiếp bình thường.

**Ước lượng:** 2–3 ngày (Telegram). Zalo thêm 2–3 ngày nếu đã có OA.

---

#### F12. Ghi âm cuộc gọi

**Yêu cầu HĐ:** *"Có ghi âm"*

**Hiện trạng:** **không lưu audio ở bất kỳ đâu**. Đây là hạng mục thiếu rõ ràng
nhất trong phần báo cáo.

**Thiết kế:**

- Ghi **hai chiều tách riêng** rồi trộn: đường xuống (tiếng bot) đã đi qua
  `PhoneCallBridge.play`, đường lên (tiếng khách) đã đi qua `_read_loop`. Ghi
  mỗi chiều một kênh, xuất file stereo — kênh trái khách, kênh phải bot. Nghe lại
  biết ngay ai nói gì, và tách được để đo lại STT sau này.
- Ghi ở **8 kHz mono mỗi kênh** (đúng chất lượng đường thoại thật, không dựng
  thêm gì) rồi mã hoá Opus 16 kbps. Một cuộc 3 phút ≈ 360 KB. Nếu lưu WAV thô
  thì 3 phút ≈ 2.8 MB — chạy chiến dịch vài nghìn số là đầy ổ.
- **Ghi bất đồng bộ vào hàng đợi**, một task riêng đẩy xuống đĩa. Không được ghi
  file trong luồng audio: nó sẽ ăn vào ngân sách 200–300 ms của F1.

*Đường dẫn:* `data/recordings/{YYYY-MM-DD}/{session_id}.opus`

*CSDL* — thêm vào `call_sessions`:
```sql
recording_path TEXT NOT NULL DEFAULT '',
recording_size INTEGER NOT NULL DEFAULT 0
```

*File mới:* `backend/services/recorder.py`
*Sửa:* `phone_call_service.py` (`play` và `_read_loop` bơm dữ liệu vào recorder),
`websocket.py` (ghi cả phiên gọi qua web).

*API:*
```
GET    /api/sessions/{id}/recording         phát/tải file
DELETE /api/sessions/{id}/recording         xoá
GET    /api/recordings/stats                dung lượng đang chiếm
POST   /api/recordings/cleanup?older_than_days=90
```

*UI* — trình phát audio ngay trong màn hình chi tiết phiên gọi; ô cấu hình thời
gian giữ file trong tab **Cài đặt**.

**Tiêu chí nghiệm thu:** gọi thật 1 cuộc 2 phút → có file nghe rõ cả hai chiều,
đúng hai kênh; TTFA đo trong lúc đang ghi **không tăng quá 10 ms** so với khi tắt ghi.

**Ước lượng:** 3 ngày.

---

#### F13. Tổng hợp ý chính cuộc gọi

**Yêu cầu HĐ:** *"Có lưu text của từng cuộc gọi, tổng hợp ý chính của từng cuộc gọi..."*

**Hiện trạng:** text đã lưu đủ (`conversation_turns`). Phần tổng hợp chưa có.

**Thiết kế:**

- Chạy **sau khi cuộc gọi kết thúc**, không chạy trong lúc gọi — tổng hợp không
  cần realtime và LLM lúc đó đang bận phục vụ cuộc gọi khác.
- Xếp hàng: mỗi phiên kết thúc đẩy một việc vào hàng đợi, một worker chạy tuần tự.
  Dùng đúng model Ollama đang có, không thêm phụ thuộc.
- Prompt tổng hợp yêu cầu trả về JSON:
```json
{
  "tom_tat": "2-3 câu",
  "nhu_cau": "sản phẩm khách quan tâm, hoặc rỗng",
  "phan_hoi": "tich_cuc | trung_tinh | tu_choi",
  "ly_do_tu_choi": "nếu từ chối",
  "can_goi_lai": true,
  "nhan_de_xuat": "quan_tam | khong_quan_tam | follow"
}
```
- `nhan_de_xuat` là **gợi ý**, ghi vào `suggested_label`; nhãn chính thức
  (`label`, F14) vẫn do người dùng bấm. Không để LLM tự gán nhãn cuối — nó sẽ sai
  và người dùng lọc báo cáo theo nhãn sai thì mất số thật.

*CSDL* — thêm vào `call_sessions`:
```sql
summary          TEXT NOT NULL DEFAULT '',
summary_json     TEXT NOT NULL DEFAULT '',
suggested_label  TEXT NOT NULL DEFAULT '',
summarized_at    REAL
```

*File mới:* `backend/services/summarizer.py`

*API:* `POST /api/sessions/{id}/summarize` (chạy lại thủ công),
`POST /api/sessions/summarize-pending` (chạy bù cho các phiên cũ).

**Tiêu chí nghiệm thu:** 20 cuộc gọi thật → 20 bản tóm tắt đọc hiểu được, trường
`phan_hoi` đúng ≥ 80% so với người nghe lại và chấm tay.

**Ước lượng:** 2–3 ngày.

---

#### F14. Gắn nhãn và chấm chất lượng cuộc gọi

**Yêu cầu HĐ:** *"Có lọc theo chất lượng (có phản hồi, không phản hồi, dập máy...)"*
và *"Gắn nhãn (quan tâm, không quan tâm, follow chăm sóc thêm...)"*

**Hiện trạng:** chưa có cả hai.

**Thiết kế:**

*Chất lượng* — suy ra tự động, không bắt người dùng nhập:
| Giá trị | Điều kiện |
|---------|-----------|
| `co_phan_hoi` | khách nói ≥ 2 lượt |
| `it_phan_hoi` | khách nói đúng 1 lượt |
| `khong_phan_hoi` | khách không nói lượt nào (nghe máy rồi im) |
| `dap_may` | cuộc gọi < 10 giây và khách không nói lượt nào |
| `hop_thu_thoai` | F7 phát hiện |
| `khong_nghe_may` | không có kết nối |

*Nhãn* — người dùng bấm, có sẵn 3 nhãn theo hợp đồng (`quan_tam`,
`khong_quan_tam`, `follow`) và thêm được nhãn mới.

*CSDL:*
```sql
-- thêm vào call_sessions
quality TEXT NOT NULL DEFAULT '',
label   TEXT NOT NULL DEFAULT '',

CREATE TABLE IF NOT EXISTS labels (
    label_id   TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    color      TEXT NOT NULL DEFAULT '#888888',
    sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX ix_sessions_label ON call_sessions(label);
CREATE INDEX ix_sessions_quality ON call_sessions(quality);
```

*API:* `PATCH /api/sessions/{id}` (nhận `label`), `GET|POST|DELETE /api/labels`,
`POST /api/sessions/bulk-label`.

*UI* — chip nhãn bấm đổi ngay trong bảng báo cáo; chọn nhiều dòng rồi gắn nhãn hàng loạt.

**Tiêu chí nghiệm thu:** sau 20 cuộc gọi thật, cột chất lượng tự điền đúng ≥ 18
cuộc so với người nghe lại chấm tay; gắn nhãn hàng loạt 10 dòng một lần được.

**Ước lượng:** 2 ngày.

---

#### F15. Trang báo cáo cuộc gọi

**Yêu cầu HĐ:** *"Báo cáo: có lọc trạng thái / lọc chất lượng / lọc thời lượng
gọi / gắn nhãn / có ghi âm / có lưu text và tổng hợp ý chính"*

**Hiện trạng:** tab **Phiên gọi** có danh sách + tìm kiếm + lọc active/ended. Đó
là màn hình gỡ lỗi kỹ thuật, chưa phải báo cáo kinh doanh.

**Thiết kế:** tab mới **Báo cáo**, gom mọi thứ F12–F14 vào một chỗ.

*Bộ lọc:* khoảng thời gian · chiến dịch · kịch bản · trạng thái · chất lượng ·
nhãn · thời lượng từ…đến (giây) · giới tính · ba trường tuỳ biến (F4) · tìm trong
nội dung hội thoại.

*Cột:* thời gian · tên · số · chiến dịch · thời lượng · trạng thái · chất lượng ·
nhãn · ghi âm (nút phát) · tóm tắt (rút gọn).

*Chi tiết một dòng:* trình phát ghi âm, toàn văn hội thoại, khối tóm tắt, số đo
độ trễ, lịch sử các lần gọi số đó.

*API:*
```
GET  /api/reports/calls?from&to&campaign_id&status&quality&label
                       &min_duration&max_duration&gender&field1&q&page&limit
GET  /api/reports/summary   → tổng cuộc, tỉ lệ nghe máy, thời lượng trung bình,
                              phân bố nhãn, phân bố chất lượng, theo ngày
GET  /api/reports/export    → CSV/Excel theo đúng bộ lọc đang áp
```

*File mới:* `backend/api/reports.py`, `backend/models/reports_db.py`

Truy vấn phải chạy trên index chứ không quét bảng: thêm
`CREATE INDEX ix_sessions_campaign_created ON call_sessions(campaign_id, created_at DESC);`
Với vài chục nghìn phiên mà không có index thì trang báo cáo sẽ treo.

**Tiêu chí nghiệm thu:** với 5 000 phiên trong CSDL, mọi tổ hợp lọc trả kết quả
**dưới 1 giây**; xuất Excel ra đúng tập đang lọc; nghe được ghi âm và đọc được
tóm tắt ngay trên trang.

**Ước lượng:** 4–5 ngày.

---

#### F16. Kết nối cơ sở dữ liệu ngoài để tra cứu

**Yêu cầu HĐ:** *"Có khả năng kết nối đến cơ sở dữ liệu (ví dụ bảng excel... để
truy cứu thông tin và tư vấn cho KH)"*

**Hiện trạng:** RAG chỉ nạp `.md` trong `knowledge/`. Muốn thêm bảng giá thì phải
chép tay sang Markdown.

**Thiết kế:** hai đường khác nhau cho hai nhu cầu khác nhau — đừng gộp làm một.

**(a) Tri thức chung → nạp vào RAG.** Bảng giá, biểu phí, danh mục sản phẩm.
Đọc `.xlsx`/`.csv`, mỗi dòng thành một mảnh văn bản
(`"Sản phẩm: X | Lãi suất: Y | Hạn mức: Z"`), nạp vào ChromaDB kèm nhãn nguồn để
xoá/nạp lại theo file. Dùng `openpyxl` (đã có sẵn qua `pandas` trong `.venv`).

**(b) Tra cứu theo khách hàng → không qua RAG.** "Dư nợ của tôi bao nhiêu",
"đơn hàng của tôi tới đâu". Đây là tra chính xác theo số điện thoại/mã khách,
không phải tìm gần đúng. Cho LLM một công cụ tra cứu, kết quả chèn thẳng vào
THÔNG TIN THAM KHẢO.

*CSDL:*
```sql
CREATE TABLE IF NOT EXISTS data_sources (
    source_id   TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL,            -- excel | csv | sqlite | mysql | postgres
    config      TEXT NOT NULL DEFAULT '', -- JSON: đường dẫn file, hoặc chuỗi kết nối
    mode        TEXT NOT NULL DEFAULT 'rag',  -- rag | lookup
    lookup_key  TEXT NOT NULL DEFAULT '', -- cột khoá khi mode=lookup, ví dụ 'so_dien_thoai'
    sync_at     REAL,
    row_count   INTEGER NOT NULL DEFAULT 0,
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  REAL NOT NULL
);
```

*File mới:* `backend/services/data_source_service.py`, `backend/api/data_sources.py`

*API:*
```
GET|POST|PATCH|DELETE /api/data-sources
POST /api/data-sources/{id}/sync      nạp lại vào ChromaDB
POST /api/data-sources/{id}/preview   xem 10 dòng đầu + ánh xạ cột
POST /api/data-sources/{id}/lookup    tra thử theo khoá
```

*UI* — tab mới **Nguồn dữ liệu**: tải file Excel lên, xem trước, chọn cột nào là
nội dung / cột nào là khoá tra cứu, bấm nạp.

*Ràng buộc offline:* chỉ chấp nhận file cục bộ và CSDL trong mạng nội bộ. Không
nhận đường dẫn HTTP ra Internet.

**Tiêu chí nghiệm thu:** tải một file Excel bảng lãi suất lên → bot trả lời đúng
số trong file đó ở cuộc gọi ngay sau khi nạp, không phải khởi động lại dịch vụ.
Và: tra được dư nợ theo số điện thoại từ một file Excel danh sách khách.

**Ước lượng:** 4–5 ngày.

---

### Bot nhận cuộc gọi vào

---

#### F17. Tiếp nhận cuộc gọi đến

**Yêu cầu HĐ:** *"Giống như Bot gọi ra (tiếp nhận cuộc gọi, giao tiếp với khách
một cách tự nhiên)"*

**Hiện trạng:** `adb_service.py:32` đọc được `CALL_STATES = {0:idle, 1:ringing,
2:offhook}` — biết máy đang đổ chuông, nhưng **không có gì bắt máy**.

**Thiết kế:**

- **Vòng theo dõi** trạng thái máy: khi chuyển `idle → ringing`, lấy số gọi đến,
  tra danh bạ, đợi N giây (cấu hình được, mặc định 2 giây — bắt máy ngay giây đầu
  nghe rất máy móc), rồi bắt máy bằng ADB (`input keyevent KEYCODE_ANSWER`).
- **Mở phiên AI** với kịch bản inbound, cắm vào đúng `PhoneCallBridge` đã có.
  Khác biệt duy nhất so với gọi ra: **bot nói trước hay khách nói trước**. Gọi
  vào thì khách đã chủ động, nên bot chào ngắn rồi im để khách nói.
- **Nhận diện số quen:** nếu số có trong `contacts`, nạp tên và lịch sử vào ngữ
  cảnh — "Dạ chào anh Nam, em nghe ạ".
- Ghi phiên với `direction = 'inbound'`.

*CSDL:*
```sql
-- thêm vào call_sessions
direction TEXT NOT NULL DEFAULT 'outbound',   -- outbound | inbound
caller_number TEXT NOT NULL DEFAULT ''
```
Thêm `inbound_scenario_id` và `inbound_enabled` vào bảng `devices`.

*File mới:* `backend/services/inbound_service.py`
*Sửa:* `adb_service.py` (thêm `answer()`, `get_incoming_number()`),
`api/devices.py` (bật/tắt nhận cuộc gọi theo máy).

*API:*
```
POST /api/devices/{id}/inbound/enable
POST /api/devices/{id}/inbound/disable
GET  /api/devices/inbound/status
```

*UI* — trong tab **Thiết bị**, mỗi máy có công tắc "Tự nhận cuộc gọi đến" và ô
chọn kịch bản inbound.

**Tiêu chí nghiệm thu:** gọi vào số của máy đã bật → bot bắt máy sau 2 giây, chào,
hội thoại được ít nhất 3 lượt, phiên lưu với `direction='inbound'` và có ghi âm.

**Ước lượng:** 4–5 ngày.

---

#### F18. Chuyển tiếp cuộc gọi khi vượt giới hạn

**Yêu cầu HĐ:** *"Có thể chuyển tiếp đến số điện thoại đã cài đặt sẵn nếu yêu cầu
vượt giới hạn đã training"*

**Hiện trạng:** chưa có gì.

**Thiết kế:**

*Khi nào chuyển tiếp:*
1. Khách nói thẳng: "cho tôi gặp người thật", "nói chuyện với nhân viên".
2. Bot trả lời câu "ngoài phạm vi" quá 2 lần liên tiếp — trong prompt hiện tại là
   *"Dạ em sẽ ghi nhận và có chuyên viên liên hệ lại ạ"* (`llm_service.py`, quy tắc 4).
   Đếm số lần bot rơi vào câu này.
3. RAG không tìm được mảnh nào liên quan 2 lượt liên tiếp.
4. Vượt `scenarios.max_turns`.

*Cách chuyển tiếp:* qua ADB, hai kiểu tuỳ tổng đài:
- **Chuyển mù** — bấm mã chuyển tiếp của nhà mạng (`**21*<số>#`) hoặc dùng tính
  năng chuyển cuộc gọi của máy.
- **Gọi hội nghị** — giữ cuộc hiện tại, gọi số nhân viên, ghép hai bên.

Trước khi chuyển, bot phải nói: *"Dạ em xin phép nối máy cho chuyên viên ạ"* —
im lặng rồi đổi người là cách chắc chắn nhất để khách cúp máy.

Nếu số chuyển tiếp bận hoặc không nghe: quay lại cuộc gọi, xin lỗi, ghi nhãn
`follow` để gọi lại sau. Không được bỏ khách ở đầu dây im lặng.

*CSDL:*
```sql
-- thêm vào scenarios
transfer_number   TEXT NOT NULL DEFAULT '',
transfer_on       TEXT NOT NULL DEFAULT '',  -- JSON: ["khach_yeu_cau","ngoai_pham_vi","het_luot"]
transfer_message  TEXT NOT NULL DEFAULT 'Dạ em xin phép nối máy cho chuyên viên ạ',
-- thêm vào call_sessions
transferred_to    TEXT NOT NULL DEFAULT '',
transfer_reason   TEXT NOT NULL DEFAULT ''
```

*File mới:* `backend/services/transfer_service.py`
*Sửa:* `streaming_pipeline.py` (đếm điều kiện chuyển tiếp mỗi lượt),
`adb_service.py` (thao tác chuyển cuộc gọi).

**Tiêu chí nghiệm thu:** khách nói "cho tôi gặp nhân viên" → bot nói câu xin phép
rồi nối máy thành công sang số đã cài; phiên ghi `transferred_to` và
`transfer_reason`; số chuyển tiếp bận thì bot quay lại xin lỗi khách chứ không
để im.

**Ước lượng:** 3–4 ngày.

---

### MỐC 100% — Bàn giao

---

#### F19. Giao diện cuối và tài liệu bàn giao

**Yêu cầu HĐ:** *"Interfere, giao diện cuối, hoàn thiện bàn giao source"* và Điều 4:
*"Lập Báo cáo thực hiện công việc trước khi nghiệm thu thanh quyết toán"*

**Việc cần làm:**

- **Gom tab.** Hiện có 12 tab, sau khi thêm F3/F15/F16 sẽ thành 15+. Gom lại:
  *Vận hành* (Hội thoại, Danh bạ, Báo cáo) · *Cấu hình* (Kịch bản, Nguồn dữ liệu,
  Giọng nói, Thiết bị) · *Hệ thống* (Training, Cài Model, Benchmark, Cài đặt, Logs).
- **Màn hình tổng quan** làm trang chủ: số cuộc hôm nay, tỉ lệ nghe máy, chiến
  dịch đang chạy, trạng thái thiết bị, độ trễ trung bình.
- **Rà thông báo lỗi**: mọi lỗi hiện ra cho người dùng phải là tiếng Việt và nói
  được cách khắc phục.
- **Hướng dẫn sử dụng** (`docs/HUONG_DAN_SU_DUNG.md`): cài đặt, tạo kịch bản, nạp
  danh bạ, chạy chiến dịch, đọc báo cáo, xử lý sự cố thường gặp.
- **Tài liệu kỹ thuật**: cập nhật `docs/ARCHITECTURE.md`, sơ đồ luồng, mô tả
  schema CSDL, danh mục API.
- **Báo cáo thực hiện công việc** theo Điều 4 hợp đồng: đối chiếu từng mục Điều 6
  với kết quả đo thực tế.
- **Đóng gói bàn giao**: mã nguồn, script cài đặt một lệnh, model đã train,
  `.env.example` đầy đủ.

**Ước lượng:** 4–5 ngày.

---

## 5. Thứ tự triển khai đề xuất

Thứ tự này theo phụ thuộc kỹ thuật, không theo độ khó.

| Đợt | Hạng mục | Ngày | Nghiệm thu |
|-----|----------|------|------------|
| 1 | **F1** độ trễ 200–300 ms | 4–6 | **Mốc 30%** |
| 2 | **F2** giọng vùng miền | 3–4 | **Mốc 50%** |
| 3 | **F3** kịch bản → **F4** trường tuỳ biến | 6–8 | |
| 4 | **F6** auto-dialer *(cần F3)* → **F5** nhập từ chiến dịch khác | 6–9 | |
| 5 | **F9** gọi lại → **F10** khung giờ *(cần F6)* | 4–5 | |
| 6 | **F7** hộp thư thoại → **F8** giới tính *(cần F6)* | 5–6 | |
| 7 | **F12** ghi âm → **F13** tóm tắt → **F14** nhãn/chất lượng | 7–8 | |
| 8 | **F15** trang báo cáo *(cần F12–F14)* | 4–5 | |
| 9 | **F11** Zalo/Telegram *(cần F13)* | 2–3 | |
| 10 | **F16** nguồn dữ liệu ngoài | 4–5 | **Mốc 70%** |
| 11 | **F17** nhận cuộc gọi → **F18** chuyển tiếp *(cần F3)* | 7–9 | |
| 12 | **F19** giao diện cuối + bàn giao | 4–5 | **Mốc 100%** |

**Tổng: 56–73 ngày công.**

Hợp đồng cho **60 ngày làm việc kể từ ngày ký (05/11/2025)**. Cận dưới của ước
lượng vừa khít, cận trên vượt khoảng hai tuần. Ba điểm cần thống nhất với bên A
trước khi bắt đầu:

1. **F1 (độ trễ 200–300 ms) là hạng mục rủi ro nhất.** Ngân sách thời gian hiện
   tại là ~510–610 ms; cắt xuống 300 ms cần cả bốn hướng ở mục F1 và vẫn có khả
   năng chỉ đạt 350–400 ms trên phần cứng thật. Nên đo trên máy đúng cấu hình HĐ
   (RTX 4070) sớm nhất có thể, trước khi cam kết lịch cho các đợt sau.
2. **Zalo OA (F11)** cần Official Account đã duyệt. Nếu bên A chưa có, làm
   Telegram trước và tách Zalo ra khỏi mốc 70%.
3. **Chính sách CSDL** (mục 3): cần chốt có làm migration hay không trước khi bắt
   đầu đợt 3, vì từ đợt 4 trở đi dữ liệu danh bạ là dữ liệu thật.

---

## 6. Những gì hợp đồng KHÔNG yêu cầu

Ghi ra để tránh làm thừa, và để khi bên A đề nghị thêm thì hai bên biết là ngoài
phạm vi hợp đồng:

- Nhiều người dùng, phân quyền, đăng nhập
- Tích hợp CRM (Salesforce, HubSpot…)
- Ứng dụng di động
- Kết nối SIP/VoIP trực tiếp (HĐ chỉ yêu cầu *"kết nối với các đơn vị cung cấp
  dịch vụ viễn thông hoặc kết nối để gọi qua điện thoại"* — điều khiển máy điện
  thoại như hiện tại đã thoả)
- Đa ngôn ngữ ngoài tiếng Việt
- Triển khai đám mây (HĐ yêu cầu **offline 100%**)
- A/B test kịch bản, chấm điểm tự động chất lượng tư vấn
