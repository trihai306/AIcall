# Ép AI chỉ nói thứ có trong tài liệu, và mở luật cho trang quản lý

Ngày 08-09-2026. Trạng thái: chờ duyệt.

## 1. Việc cần làm

Hai việc bên A yêu cầu trong cùng một buổi:

1. Quy tắc cho AI (kể cả `CORE_RULES` đang viết cứng) phải sửa được trên trang
   quản lý, không phải sửa code.
2. Ép AI **chỉ nói những gì có trong tài liệu**.

## 2. Vì sao việc 2 không làm bằng prompt

Đã có ba bằng chứng trong chính dự án này:

- `chan_tuan_thu.py` ghi: *"dự án đã thử dặn bằng prompt ba kiểu và hỏng ba kiểu
  khác nhau. Với tư vấn tài chính thì 'phần lớn lượt sẽ đúng' không phải một bảo
  đảm."*
- Prompt còn tự gây hại: hai ví dụ "sáu phẩy năm phần trăm" trong `CORE_RULES` đã
  khiến mô hình báo lãi suất 6.5% thay vì 7.9% — thấp hơn thực tế 1,4 điểm phần
  trăm, trong cuộc gọi bán sản phẩm tài chính. Tách bạch bằng
  `scripts/soi_nguon_65.py`: prompt tối giản thì trả lời đúng.
- Cuộc gọi 08-09-2026 (`10619ae0`): AI đáp *"Lợi ích số loại 3 bao gồm giảm lãi
  suất và miễn phí quản lý tài khoản trong 12 tháng"* — bịa trọn mệnh đề, không
  con số nào sai nên năm lưới số hiện có đều mù.

Nên việc ép phải nằm ở **lưới chạy sau khi mô hình sinh, trước khi sang TTS**,
cùng chỗ với `chan_so_sai`.

## 3. Ba hướng đã chấm thử, và kết quả

Chấm trên 250 lượt lấy ngẫu nhiên từ `conversation_turns` (seed 11) cộng một tập
đối chứng 20 câu (10 lấy nguyên ý từ `knowledge/products/vay_tin_chap.md`, 10 bịa).

### 3.1 Cosine embedding — BÁC BỎ

Đánh dấu 88,1% mệnh đề, phần lớn là câu đúng. Đối chứng trực tiếp:

| | Dải điểm | Trung vị |
|---|---|---|
| câu đúng | 0,02 – 0,46 | 0,18 |
| câu bịa | 0,03 – 0,33 | 0,14 |

Hai dải chồng nhau. *"Khách cần từ 22 đến 60 tuổi"* (đúng nguyên văn) được 0,02,
thấp nhất bảng; *"Lãi suất chỉ 5% một năm"* (bịa) được 0,33, cao hơn 8/10 câu
đúng. Không ngưỡng nào cứu được.

**Vì sao**: embedding đo *cùng chủ đề*, không đo *đúng hay sai*. Với nó "lãi suất
5%" và "lãi suất 7.9%" gần như đồng nghĩa — khác nhau đúng ở con số, mà con số là
thứ cần kiểm. Đây cũng là điểm mù đã ghi trong dự án: mảnh định nghĩa sản phẩm
không bao giờ thắng điểm cosine.

### 3.2 Thuộc tính–giá trị — GIỮ, cho phần số

Trích cặp (thuộc tính, giá trị) từ câu, đối chiếu với giá trị đọc **từ tài liệu**
(không viết cứng — sửa tài liệu là lưới đổi theo).

- Đối chứng: 0/10 câu đúng bị chặn, 4/10 câu bịa bị bắt.
- 250 lượt: chặn 6,4%, trong đó **12 lượt chặn đúng**, chặn nhầm thật 1 lượt (0,4%).
- Chi phí: ~0ms, không cần GPU.

Loại lỗi nó bắt được và không lưới nào khác bắt: mô hình tự chế quy tắc suy diễn
thu nhập → hạn mức, xuất hiện **5 lần trong 250 lượt**. Một lượt còn lấy 3,4 triệu
(số tiền trả góp trong tài liệu) làm thu nhập — đúng cái bẫy tài liệu đã viết hoa
cảnh báo.

Điểm yếu: chỉ bắt được thuộc tính đã khai báo, và chỉ bắt được cái có con số.

### 3.3 NLI theo mục — GIỮ, cho phần mệnh đề

`MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` (100 thứ tiếng, có
tiếng Việt, 87,1% XNLI). Premise là **từng mục `##` của tài liệu**, lấy điểm
entailment cao nhất.

Chia theo mục là bước quyết định: lấy cả file làm premise thì *"Giảm 0.5% lãi suất
cho khách có lương qua ngân hàng"* (nguyên văn tài liệu) chỉ được 0,018; chia mục
thì lên 0,990.

| | Dải điểm | Trung vị |
|---|---|---|
| câu đúng | 0,843 – 0,992 | 0,985 |
| câu bịa | 0,008 – 0,911 | 0,051 |

Ngưỡng **0,30**: 10/10 câu đúng qua, 8/10 câu bịa bị chặn. Hai câu lọt
(*"Giải ngân ngay trong vòng 2 giờ"*, *"Tặng ngay 5 triệu tiền mặt"*) thì lưới
thuộc tính bắt được câu đầu → ghép lại 9/10.

Trên 250 lượt thật, phải thêm năm bộ lọc mới dùng được:

| Lần chấm | Lượt bị chặn |
|---|---|
| NLI thô | 50,3% |
| + 4 bộ lọc (nhắc lời khách / câu hành động / dữ liệu hồ sơ / neo sản phẩm theo nội dung) | 41,1% |
| + lọc mệnh đề cụt | 34,3% |
| + hạ ngưỡng 0,634 → 0,30 | **20,0%** |

20% này **không phải** tỉ lệ chặn nhầm: đọc mẫu thì phần lớn là bịa thật. Chặn
nhầm ước 3–6% (ước lượng từ 22 mệnh đề đọc tay, chưa chấm đủ 28 lượt).

## 4. Kiến trúc

Ba lưới nối tiếp, chạy đúng chỗ `chan_so_sai` đang chạy — trên từng mảnh, trước TTS:

```
mảnh do LLM sinh
   │
   ├─ Lưới 1  CẤM TỪ           mở rộng chan_tuan_thu.py sang bảng DB     ~0ms
   ├─ Lưới 2  THUỘC TÍNH-GIÁ TRỊ  khoá mọi con số                        ~0ms
   └─ Lưới 3  NLI THEO MỤC        khoá mệnh đề không số                 ~34ms
   │
   ▼
cắt đúng mệnh đề vi phạm, GIỮ phần còn lại
   │  (cắt sạch thì mới rơi về câu "em kiểm tra lại")
   ▼
TTS
```

**Cắt mệnh đề chứ không thay cả câu** — đây là chỗ cố ý làm khác lưới cũ.
`text_normalizer.py:831` thay cả mảnh bằng một câu trọn vẹn, và đó chính là nguồn
của phản hồi *"hỏi lãi cao vậy sao nó trả lời 1 kiểu"*: mô hình trả lời khác nhau,
lưới làm chúng giống nhau.

### 4.1 Năm bộ lọc trước khi phán

Bỏ qua mệnh đề nếu:

1. **Nhắc lại lời khách** — mọi con số trong mệnh đề đều có trong lời khách của
   phiên. Cùng ranh giới `so_can_cu.py` đã đặt: tài liệu và lời khách thì tin,
   lời AI thì không.
2. **Câu hành động** — "em sẽ kiểm tra", "em tổng hợp", "anh vui lòng"…
3. **Dữ liệu hồ sơ riêng của khách** — "dư nợ", "thời gian còn lại", "hạn mức đã
   duyệt cho anh". Không nằm trong tài liệu sản phẩm nên không kiểm bằng tài liệu.
4. **Xã giao / câu hỏi lại**.
5. **Mệnh đề cụt** — dưới 5 từ, hoặc không có động từ chỉ báo, hoặc kết thúc bằng
   liên từ. Cắt sai ra "các điều kiện sử dụng" thì phán nó là phán cái không phải câu.

### 4.2 Neo sản phẩm theo nội dung

Trường `product` của phiên có thể sai hoặc rỗng: đo được lượt khách hỏi thẻ tín
dụng trong phiên gán "vay tín chấp", làm *"miễn lãi 55 ngày"* (đúng tài liệu thẻ)
bị tra nhầm kho. Chọn kho theo dấu hiệu trong câu khách và mệnh đề trước, rồi mới
rơi về `product`, cuối cùng mới dùng toàn bộ kho.

## 5. Dữ liệu

Ba bảng mới, tất cả sửa được trên trang quản lý:

```sql
CREATE TABLE luat_loi_noi (          -- lưới 1
    luat_id     TEXT PRIMARY KEY,
    loai        TEXT NOT NULL,       -- cam_tu | bat_buoc_kem
    mau         TEXT NOT NULL,       -- khớp theo TỪ, có ranh giới hai đầu
    ly_do       TEXT NOT NULL,       -- hiện trên UI: luật này vá lỗi gì
    bat         INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE thuoc_tinh_kiem (       -- lưới 2
    ten         TEXT PRIMARY KEY,    -- "lãi suất", "hạn mức"
    tu_khoa     TEXT NOT NULL,       -- JSON list
    don_vi      TEXT NOT NULL,       -- JSON list: %, triệu, tỷ, tháng…
    bat         INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE core_rule (             -- mở CORE_RULES
    so_thu_tu   INTEGER PRIMARY KEY,
    noi_dung    TEXT NOT NULL,
    va_loi_gi   TEXT NOT NULL,       -- lấy nguyên từ chú thích trong llm_service
    bat         INTEGER NOT NULL DEFAULT 1,
    mac_dinh    TEXT NOT NULL        -- để có nút khôi phục
);
```

`CORE_RULES` trong code trở thành **giá trị mặc định gieo lần đầu**, không xoá —
mất DB thì vẫn còn bản gốc.

## 6. Trang quản lý

- **Luật lõi**: bật/tắt và sửa từng luật, mỗi luật hiện kèm dòng "vá lỗi gì".
  Tắt một luật thì hỏi lại chứ không tắt lặng lẽ. Có nút khôi phục mặc định.
- **Thuộc tính kiểm**: thêm/sửa thuộc tính và đơn vị.
- **Từ cấm**: thêm/sửa, mỗi dòng kèm lý do.
- **Nhật ký chặn**: câu nào bị chặn, lưới nào chặn, điểm bao nhiêu, tài liệu đối
  chiếu là mục nào. Đây là thứ để chỉnh ngưỡng bằng dữ liệu thay vì cảm tính.

## 7. Độ trễ

Ngân sách đã rất chật: khách đang chờ ~1285ms, trong đó ~373ms là GSM không rút
được. Nên:

- Lưới 1 và 2: ~0ms, chạy trên mọi mảnh.
- Lưới 3 (NLI): 26ms mỗi mệnh đề, trung bình 1,3 mệnh đề mỗi mảnh → **~34ms**.
- Mô hình ~560MB VRAM. Máy còn 3827 MiB trống lúc đo.
- **Mảnh đầu nằm trên đường găng TTFA.** Nếu đo thấy 34ms đó đội TTFA thì cho lưới
  3 bỏ qua mảnh đầu, để lưới 1 và 2 gác — mảnh đầu là câu đệm hoặc câu ngắn, ít
  mang số liệu nhất.

## 8. Nghiệm thu

Đo lại trên đúng 250 lượt đã dùng, cùng seed:

- bắt ≥ 80% câu bịa trong tập đối chứng — hiện đạt 80% (NLI đơn), 90% (ghép)
- chặn nhầm ≤ 5% số lượt — hiện ước 3–6%, phải **chấm tay đủ** để chốt
- cộng ≤ 50ms vào mảnh — hiện ~34ms
- không lượt nào bị thay cả câu khi chỉ một mệnh đề vi phạm

## 9. Giả định tôi chốt thay

| Giả định | Nếu sai thì đổi gì |
|---|---|
| "Chỉ nói thứ có trong tài liệu" = không bịa **thông tin sản phẩm**; xã giao và câu dẫn dắt vẫn được | Hiểu chặt hơn thì cuộc gọi nghe như đọc tài liệu |
| Bật ở chế độ **chỉ ghi nhật ký** trước, đo rồi mới cho chặn thật | Bật chặn ngay thì không biết chặn nhầm bao nhiêu cho tới khi khách phàn nàn |
| Cắt mệnh đề, giữ phần còn lại | Muốn an toàn tuyệt đối thì thay cả câu, đổi lại mọi lượt nghe giống nhau |
| Mở toàn bộ `CORE_RULES` cho sửa | Bên A đã chốt "mở cả core rule". Rủi ro: mỗi luật là bản vá cho một lỗi thật, tắt nhầm là lỗi cũ quay lại |

## 10. Chỗ tôi hiểu khác lời bên A

Bên A hỏi "có cách nào ép AI được không" và ban đầu nghĩ tới việc sửa rule. Rule
sửa được giải quyết chuyện **tự chỉnh không cần lập trình**; nó **không** ép được
AI. Thứ ép được là ba lưới ở mục 4. Hai việc đều đáng làm, nhưng không thay nhau.

## 11. Không làm

- **Trọng tài LLM**: cộng 200–600ms, trong khi NLI cho kết quả tương đương ở 26ms.
- **Bắt AI trích dẫn nguồn cho khách nghe**: không ai muốn nghe điều đó qua điện thoại.
- **Chỉnh ngưỡng cho số đẹp**: ngưỡng 0,30 chọn từ đường cong đo được, đổi thì
  phải chấm lại trên 250 lượt.

## 12. Mốc triển khai

1. Ba bảng DB + gieo mặc định từ `CORE_RULES` hiện tại. Đường sinh chưa đổi.
2. Lưới 2 (thuộc tính) — rẻ nhất, đã có nửa đường ở `chan_lai_suat_bia`.
3. Lưới 3 (NLI) ở chế độ **chỉ ghi nhật ký**, chạy vài chục cuộc thật rồi đọc.
4. Bật chặn cho lưới 3 sau khi nhật ký cho thấy chặn nhầm ≤ 5%.
5. Trang quản lý.
6. Lưới 1 (cấm từ) chuyển từ hằng số sang bảng.

Mốc 1–2 dùng được ngay mà không cần GPU thêm. Mốc 3 mới cần mô hình NLI.
