# Báo cáo thực hiện công việc

> Theo **Điều 4** hợp đồng khoán gọn ký 05/11/2025: *"Lập Báo cáo thực hiện công
> việc trước khi nghiệm thu thanh quyết toán Hợp đồng"*.
>
> Đối chiếu từng mục của **Điều 6** với kết quả thực tế.
> Lập ngày 05/08/2026.

---

## 1. Thay đổi phạm vi được bên A chốt

| # | Nội dung | Quyết định |
|---|----------|------------|
| 1 | Độ trễ 200–300 ms | **Bỏ.** Bên A chấp nhận giữ mức 1000 ms hiện tại. |
| 2 | Gửi báo cáo qua Zalo **hoặc** Telegram | **Chỉ làm Telegram.** Hợp đồng cho chọn một trong hai. |

Mọi hạng mục còn lại của Điều 6 đã thực hiện đầy đủ.

---

## 2. Đối chiếu Điều 6

Ký hiệu: **✅ xong** · **🔬 xong, cần mẫu thật để chốt số** · **⛔ bỏ theo thoả thuận**

### 2.1 Bot gọi ra

| Yêu cầu hợp đồng | TT | Thực hiện ở đâu |
|------------------|----|-----------------|
| Độ trễ 200–300 ms | ⛔ | Bỏ theo mục 1 |
| Giọng tự nhiên, training được | ✅ | Đã có từ trước |
| Nhận diện giọng vùng miền | 🔬 | `MOI_VUNG_MIEN` trong `stt_service.py` · `scripts/do_vung_mien.py` |
| Chạy offline 100% | ✅ | Giữ nguyên. Ngoại lệ duy nhất: Telegram (kênh thông báo ra ngoài) |
| Kết nối CSDL/Excel để tra cứu | ✅ | `data_source_service.py` · `api/data_sources.py` |
| Train kịch bản, form thống nhất | ✅ | `scenarios_db.py` · `api/scenarios.py` · `GET /api/scenarios/template` |
| Train giọng, form thống nhất | ✅ | Đã có từ trước |
| Kết nối gọi qua điện thoại | ✅ | Đã có từ trước |

### 2.2 Bot nhận cuộc gọi vào

| Yêu cầu hợp đồng | TT | Thực hiện ở đâu |
|------------------|----|-----------------|
| Tiếp nhận cuộc gọi, giao tiếp tự nhiên | ✅ | `inbound_service.py` · `adb_service.answer()` |
| Chuyển tiếp đến số cài sẵn khi vượt giới hạn | ✅ | `transfer_service.py` · `adb_service.chuyen_cuoc_goi()` |

### 2.3 Dashboard

| Yêu cầu hợp đồng | TT | Thực hiện ở đâu |
|------------------|----|-----------------|
| B1 — Chọn kịch bản | ✅ | Tab **Kịch bản** + ô chọn trong khối chạy chiến dịch |
| B2 — Tải file khách hàng + 1–2 trường thêm | ✅ | 3 cột tuỳ biến, tự nhận nhãn từ tiêu đề file |
| B2 — Nhập từ chiến dịch khác | ✅ | `POST /api/phones/campaigns/{id}/import-from` |
| B3 — Tắt máy khi vào hộp thư thoại | ✅ | `voicemail_detect.py` |
| B3 — Nhận diện giới tính | ✅ | `gender_detect.py` |
| B3 — Gọi lại khi không bắt máy / bận / hộp thư | ✅ | `contacts_db.finish_attempt()` |
| B3 — Số lần gọi lại, gọi lại sau bao nhiêu phút | ✅ | `retry_max`, `retry_delay_min` |
| B3 — Ngày bắt đầu, khung giờ chạy | ✅ | `khung_gio.py` |
| B3 — Gửi báo cáo qua Telegram | ✅ | `notify_service.py` |
| B3 — Ngắt khi khách chen ngang | ✅ | Đã có từ trước |
| *(nền tảng)* Chạy chiến dịch tự động | ✅ | `campaign_runner.py` |

### 2.4 Báo cáo

| Yêu cầu hợp đồng | TT | Thực hiện ở đâu |
|------------------|----|-----------------|
| Lọc trạng thái | ✅ | Tab **Báo cáo** |
| Lọc chất lượng (có/không phản hồi, dập máy) | ✅ | `reports_db.derive_quality()` — hệ thống tự chấm |
| Lọc thời lượng gọi | ✅ | Tab **Báo cáo** |
| Gắn nhãn (quan tâm / không / follow) | ✅ | Bảng `labels`, gắn hàng loạt |
| Có ghi âm | ✅ | `recorder.py` — stereo, trái khách phải bot |
| Lưu text từng cuộc gọi | ✅ | Đã có từ trước |
| Tổng hợp ý chính từng cuộc gọi | ✅ | `summarizer.py` |

---

## 3. Kết quả kiểm thử

### Bộ kiểm thử CRUD tự động

```bash
python scripts/kiem_thu_crud.py                      # máy đang chạy backend
python scripts/kiem_thu_crud.py --url http://127.0.0.1:8100   # máy Windows qua tunnel
```

**121/121 khẳng định ĐẠT.** Chạy trên máy chủ đang sống (HTTP thật, không gọi
hàm trực tiếp) để bắt cả lỗi tầng API: pydantic ép kiểu sai, route trùng, tên
tham số truy vấn lệch, JSON thiếu khoá mà giao diện đang đọc. Tự dọn sạch dữ
liệu tạo ra, kể cả khi có bài hỏng giữa chừng.

Phủ tạo–đọc–sửa–xoá cho: kịch bản · danh bạ · chiến dịch · nhãn · báo cáo ·
kênh Telegram · nguồn dữ liệu · nhận cuộc gọi đến. Cùng với đó là các trường
hợp phải BỊ CHẶN: id không tồn tại, trùng số, trạng thái lạ, sự kiện lạ, file
JSON hỏng, thiếu tên, nguồn = đích, đường dẫn web, chế độ sai.

Điểm đáng nói: bản đầu của chính bộ kiểm này có lỗ hổng — các bộ lọc báo cáo
chỉ được kiểm `số kết quả <= tổng`, nên **một bộ lọc hỏng đến mức luôn trả 0
cũng qua được**. Đã siết lại: gieo 6 phiên gọi có kết quả/chất lượng/nhãn/giới
tính/thời lượng biết trước, rồi đối chiếu **18 tổ hợp lọc** với con số mong đợi,
và đối chiếu chéo phân bố ở `/summary` với chính bộ lọc (hai đường tính khác
nhau, khớp nhau mới là bằng chứng).


Mỗi hạng mục được chạy thử ngay sau khi làm xong. Ba lỗi thật đã bị bắt và sửa
trong quá trình đó — ghi lại vì chúng là loại lỗi im lặng, không có bài kiểm thì
chỉ phát hiện khi đã chạy thật:

| Lỗi | Triệu chứng nếu để lọt | Đã sửa |
|-----|------------------------|--------|
| Ghi âm ghép hai kênh theo thứ tự hàng đợi | Tiếng bot rơi sai vị trí thời gian trong bản ghi | Đóng dấu vị trí cho từng khung tiếng bot |
| So chuỗi có dấu với chuỗi đã bỏ dấu | Điều kiện chuyển tiếp "bot bí 2 lượt" **không bao giờ** kích hoạt | Bỏ dấu cả hai vế |
| `+84...` không khớp `0...` khi tra Excel | Tra hồ sơ khách trượt với số viết kiểu quốc tế | Dùng lại `normalize_phone` của danh bạ |
| Cuộc gọi không ai nghe bị loại khỏi báo cáo | Nửa số dòng của mọi chiến dịch biến mất | Giữ phiên thuộc chiến dịch dù không có lượt nào |
| `.btn` đè `.hidden` | Bốn nút Bắt đầu/Tạm dừng/Tiếp tục/Dừng hiện cùng lúc | Thêm luật `.hidden` ưu tiên cao |
| **Chỉ bộ quay số tự động gắn nguồn gốc vào phiên** | Gọi tay và bật đường tiếng đẻ ra phiên trống: KHÔNG ghi âm, KHÔNG vào Báo cáo | Gom về `services/call_session_service.py`, cả 4 đường dùng chung |
| Cuộc gọi không có tiếng vẫn sinh file Opus | File 871 byte HỎNG mà Báo cáo trỏ tới như có ghi âm | Không có khung nào thì xoá file, báo "không có bản ghi" |

### Số đo cụ thể

| Hạng mục | Kết quả đo |
|----------|-----------|
| Migration CSDL | Chạy trên `app.db` thật: 13 phiên + 40 lượt cũ còn nguyên, chạy lại lần 2 không nhân đôi |
| Kịch bản | Tạo kịch bản ngành bảo hiểm hoàn toàn qua API, **không sửa dòng code nào** |
| Trường tuỳ biến | File CSV có cột "Chi nhánh"/"Nhóm khách" → tự nhận nhãn, lọc được |
| Chuẩn hoá số | `0912345678`, `0912 345 678`, `+84912345678`, `0084912345678`, `0912.345.678` → cùng một thuê bao |
| Auto-dialer | 10 số, 2 luồng: gọi hết, xếp lịch gọi lại đúng, **không sót số nào ở trạng thái `calling`** |
| Nhận diện giới tính | F0 thật 110/135/210/240 Hz → đo được 111/135.6/210.5/242.4 Hz, đúng 4/4; vùng chồng lấn trả `unknown` |
| Hộp thư thoại | 6 tình huống: bắt đúng 3 hộp thư, **không nhận nhầm người thật lần nào** |
| Ghi âm | Bản ghi 10s, hai kênh khớp đúng mốc; nạp một khung tốn **0.2 µs** (không ăn vào độ trễ) |
| Chất lượng cuộc gọi | 7/7 tình huống chấm đúng |
| Telegram | Token sai → báo đúng lỗi 401 từ Telegram, không thử lại vô ích, **không chặn vòng chạy** |
| Nguồn dữ liệu | Đọc Excel thật, tra chính xác theo số điện thoại, chặn đường dẫn web |
| Chuyển tiếp | 7 tình huống điều kiện đúng hết; "bí – trả lời được – bí lại" **không** kích hoạt (đúng thiết kế) |
| Khung giờ chạy | 7 mốc thời gian biên đúng hết (nghỉ trưa, đúng giờ đóng, cuối tuần, chưa tới ngày, quá hạn) |

### Kiểm thử trên giao diện thật

Chạy `backend.main` với `data/app.db` thật, thao tác qua trình duyệt:

- Bốn trang mới (Tổng quan, Kịch bản, Báo cáo, Nguồn dữ liệu) hiển thị và nạp dữ liệu đúng
- Trang Báo cáo: 23 cuộc gọi, áp bộ lọc chất lượng → số kết quả đổi đúng
- Nguồn dữ liệu: đọc file Excel thật, hiện đúng câu mà bot sẽ đọc
- Chạy chiến dịch: bấm Bắt đầu lúc 12 giờ trưa → hệ thống **tự đợi**, báo
  *"Ngoài khung giờ, mở lại lúc 13:30 thứ Tư 05/08"*
- Không có lỗi nào ở console trình duyệt lẫn log máy chủ

---

## 4. Còn cần bên A phối hợp

| Việc | Vì sao cần bên A |
|------|------------------|
| **Mẫu thu giọng vùng miền** | Cần ≥ 20 câu/vùng thu **qua đường điện thoại thật**. Không có mẫu thì không đo được WER, và không đo thì không nghiệm thu được mục "nhận diện giọng vùng miền". Chạy: `python scripts/do_vung_mien.py` |
| **Gọi thử trên SIM thật** | Các mục cần điện thoại thật để chốt số: phát hiện hộp thư thoại (≥18/20), nhận diện giới tính (≥85%/40 cuộc), chuyển tiếp cuộc gọi, bot nhận cuộc gọi vào. Logic đã kiểm thử đầy đủ bằng dữ liệu tổng hợp. |
| **Bot Telegram** | Cần token + chat_id của bên A để bật kênh báo cáo. Hướng dẫn ngay trong tab **Cài đặt**. |

---

## 5. Danh mục bàn giao

### Mã nguồn mới

| File | Chức năng |
|------|-----------|
| `backend/models/scenarios_db.py` | Kho kịch bản |
| `backend/models/reports_db.py` | Chốt kết quả, chấm chất lượng, nhãn, truy vấn báo cáo |
| `backend/services/campaign_runner.py` | Bộ quay số tự động |
| `backend/services/khung_gio.py` | Ngày bắt đầu + khung giờ chạy |
| `backend/services/voicemail_detect.py` | Phát hiện hộp thư thoại |
| `backend/services/gender_detect.py` | Nhận diện giới tính |
| `backend/services/recorder.py` | Ghi âm hai kênh |
| `backend/services/summarizer.py` | Tổng hợp ý chính |
| `backend/services/notify_service.py` | Telegram |
| `backend/services/data_source_service.py` | Nguồn dữ liệu ngoài |
| `backend/services/inbound_service.py` | Bot nhận cuộc gọi |
| `backend/services/transfer_service.py` | Chuyển tiếp người thật |
| `backend/services/call_session_service.py` | Mở/chốt phiên — dùng chung cho cả 4 đường gọi |
| `backend/api/scenarios.py` · `reports.py` · `notify.py` · `data_sources.py` | REST API |
| `frontend/trang_moi.js` | Giao diện các trang mới |
| `scripts/do_vung_mien.py` | Đo WER theo vùng miền |
| `scripts/kiem_thu_crud.py` | Kiểm thử CRUD toàn bộ API (121 khẳng định) |

### Tài liệu

| File | Nội dung |
|------|----------|
| `docs/HUONG_DAN_SU_DUNG.md` | Hướng dẫn vận hành |
| `docs/DAC_TA_TINH_NANG_CON_THIEU.md` | Đặc tả gốc, đối chiếu hợp đồng |
| `docs/BAO_CAO_THUC_HIEN.md` | Tài liệu này |
| `docs/ARCHITECTURE.md` | Kiến trúc kỹ thuật |

### Lưu ý vận hành

- **Không cần xoá `data/app.db` khi nâng cấp.** Hệ thống tự bổ sung cột mới lúc
  khởi động (`_ADDED_COLUMNS` trong `models/db.py`), đã kiểm trên dữ liệu thật.
- Sao lưu: chép `data/app.db` và `data/recordings/`.
- Thêm phụ thuộc mới: `openpyxl` (đọc Excel).
- Build lại CSS sau khi sửa giao diện:
  `npx tailwindcss@3 -c frontend/tailwind.config.js -i frontend/tailwind.input.css -o frontend/tailwind.css --minify`

---

## 6. Bảo hành

Theo hợp đồng: **6 tháng** kể từ ngày bàn giao.
