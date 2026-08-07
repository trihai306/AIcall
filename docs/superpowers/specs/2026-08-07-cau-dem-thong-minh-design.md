# Câu đệm thông minh — thiết kế

Ngày: 2026-08-07

## Vấn đề

Khách nghe câu đệm (filler) lặp đi lặp lại suốt cuộc gọi.

Nguyên nhân đo được, không phải cảm giác:

- Kho có 14 câu cứng trong `backend/pipeline/streaming_pipeline.py:31`.
- Từ lượt 2 trở đi, `_send_filler` lọc còn nhóm `FILLER_HOP_CAU_HOI` = 11 câu.
- Lọc tiếp "đủ dài để che độ trễ" (đường thoại `_FILLER_MIN_THOAI_MS = 1800ms`)
  thì **chỉ còn 2 câu** vượt ngưỡng. Cuộc gọi 9 lượt nghe 2 câu đó luân phiên.

Thêm câu là điều kiện cần, nhưng chưa đủ và có cái giá của nó — xem "Ràng buộc".

## Ràng buộc phát hiện được khi khảo sát

### 1. Câu đệm phát TRƯỚC STT — nhưng vẫn biết khách nói gì

`_send_filler` là `await` đầu tiên của lượt (`streaming_pipeline.py:546`), chạy
trước khi phiên âm chính thức xong. Thoạt nhìn tưởng không thể chọn theo ngữ cảnh.

Thực tế **biết được, miễn phí**: luồng "nghĩ sẵn" (`speculate`) phiên âm khi khách
còn đang nói và ghi vào `session.spec_stt` ngay sau STT
(`streaming_pipeline.py:267`), trước cả RAG/LLM. `_send_filler` chạy ngay trước chỗ
đọc ô đó (`streaming_pipeline.py:555`). Đường chat còn đơn giản hơn: `text` nằm sẵn
trong tay ở `process_text_turn` (`streaming_pipeline.py:686`).

Hệ quả: chọn theo ngữ cảnh làm được **ngay trong cùng lượt, 0ms phát sinh**.

Trường hợp `spec_stt` rỗng (khách nói quá ngắn, dưới `_SPEC_MIN_MS`) → rơi về nhóm
`chung`, không chờ.

### 2. Chi phí dựng tiếng chặn việc mở rộng kho

`presynthesize_fillers` gọi F5 cho từng câu, giữ trong RAM (`tts_service.py:505`).
14 câu ≈ 7 giây. 60 câu ≈ **30 giây mỗi giọng**.

Nguy hiểm hơn con số: `_warm_fillers` dựng tiếng cho giọng mới **ngay lúc cuộc gọi
bắt đầu**, chạy nền (`backend/api/websocket.py:286`). 30 giây TTS chạy nền sẽ giành
GPU với chính cuộc gọi đang sống.

Nên **mở rộng kho bắt buộc đi kèm cache ra đĩa**. Không thì tính năng tự bắn vào chân.

### 3. `latency_metrics` không lưu câu đệm đã dùng

`backend/models/db.py:475` chỉ ghi `stt_ms, rag_ms, ttfa_ms, total_ms`. Muốn thống
kê lặp phải thêm cột. Đã có sẵn cơ chế nâng cấp bảng ở `db.py:319` (`_ADDED_COLUMNS`).

## Quyết định đã chốt với bên A

| Câu hỏi | Chốt |
|---|---|
| Mục tiêu | Cả chống lặp lẫn chọn theo ngữ cảnh |
| Mức bám ngữ cảnh | Nêu **chủ đề chung**, không nêu số liệu cụ thể |
| Kho câu để ở đâu | Quản lý trong UI |
| Nguồn câu | Em soạn sẵn + nút "AI sinh thêm câu" |
| Hướng kỹ thuật | Kho mở rộng + cache ra đĩa + lưới từ khoá |

**Không train mô hình nào.** Chọn câu bằng lưới từ khoá. LLM chỉ chạy ở các nút
offline, không bao giờ trong cuộc gọi.

### Hướng đã cân nhắc và loại

**Ghép mảnh `[mở đầu] × [thân]`** (6 × 10 = 60 tổ hợp từ 16 lần dựng tiếng) — loại.
Dự án đã đo được đúng loại hỏng này: cắt/ghép mảnh TTS sinh ngữ điệu kết câu ở giữa
câu và nghe rõ mối nối. Câu đệm là thứ khách nghe **đầu tiên mỗi lượt** — chỗ tệ
nhất để đặt một mối nối.

**Giữ cache trong RAM, chỉ thêm câu** — loại. Trần thực tế ~20-25 câu; chia cho
5-6 chủ đề × 3 rổ độ dài thì mỗi ô còn 1-2 câu, quay lại đúng chỗ đang lặp.

## Thiết kế

### A. Kho câu thành dữ liệu — `data/fillers.json`

```json
{
  "chu_de": [
    { "id": "ho_so", "ten": "Hồ sơ, thủ tục",
      "tu_khoa": ["hồ sơ", "giấy tờ", "thủ tục", "cần những gì", "chuẩn bị gì"] }
  ],
  "cau": [
    { "id": "ho_so_01",
      "text": "Dạ, phần hồ sơ thì anh chị chờ em chút để em xem lại cho kỹ nhé",
      "chu_de": "ho_so", "hop_cau_hoi": true }
  ]
}
```

**Không khai báo độ dài.** Cùng một câu, giọng khác nhau ra số ms khác nhau — rổ độ
dài **đo lúc dựng tiếng, tính riêng theo từng giọng**. Người thêm câu chỉ gõ chữ.

`hop_cau_hoi` giữ đúng ý nghĩa cũ của `FILLER_HOP_CAU_HOI`
(`streaming_pipeline.py:60`) — một cờ, không phải chiều phân loại thứ ba.

#### Phân bổ câu cố ý lệch

Chia đều 7 chủ đề × 3 rổ = 21 ô; 60 câu rải ra mỗi ô còn 3 câu → **lặp y như cũ,
chỉ tốn công hơn**. Nên:

| Rổ | Nội dung | Số câu |
|---|---|---|
| Ngắn (< 800ms) | chỉ `chung` — "Dạ", "Vâng ạ" quá ngắn để nêu chủ đề | ~8 |
| Vừa (800–1500ms) | chỉ `chung` | ~10 |
| Dài (≥ 1500ms) | `chung` ~10 + mỗi chủ đề 4–5 câu | ~40 |

Chủ đề **chỉ có ở rổ dài** — đúng chỗ đang lặp nặng nhất (hiện chỉ 2 câu vượt
1800ms), và cũng là rổ duy nhất đủ chỗ nói ra chủ đề mà không gấp gáp.

**Hệ quả cố ý, đừng đọc nhầm thành lỗi:** khi đường đang nhanh (`min_ms` thấp, ví dụ
đường chat 900ms), khoảng "vừa khít" là `[900, 1700]` nên đa số câu được chọn là
`chung`, ít khi nêu chủ đề. Đúng như vậy: đường nhanh thì không có chỗ cho một câu
dài nêu chủ đề, mà nhét vào thì chính câu đệm thành thứ gây trễ. Hai rổ giao nhau ở
khoảng 1500–1700ms nên chuyển tiếp vẫn mượt, không phải vách đứng.

### B. Quản lý chủ đề — bốn lớp

**Lớp 1 — Chủ đề là dữ liệu.** Nằm trong cùng `fillers.json`, sửa trong UI. Thêm
chủ đề mới không đụng code, không restart.

**Lớp 2 — Gieo mầm từ kho tri thức.** Nút *"Quét kho tri thức"*: đọc đề mục
`##`/`###` trong `knowledge/` (API sẵn có: `backend/api/knowledge.py:153`), đưa LLM
gom thành chủ đề + từ khoá đề xuất, người dùng tick duyệt.

Vì sao đáng làm: tài liệu hiện có đã sẵn đề mục khớp gần đúng chủ đề — "Điều kiện
vay", "Hồ sơ cần thiết", "Tôi có thể vay tối đa bao nhiêu?", "Thời gian phê duyệt
hồ sơ vay bao lâu?". Chủ đề vì thế bám đúng sản phẩm bên A đang bán; bên A thêm sản
phẩm mới thì quét lại là có.

**Lớp 3 — Bồi từ khoá từ cuộc gọi thật.** Nút *"Học từ cuộc gọi"*: quét
`conversation_turns` (`db.py:109`) lấy câu khách nói, lọc những câu **không khớp chủ
đề nào**, gom cụm hay lặp, đề xuất từ khoá còn thiếu.

Đây là thứ duy nhất trong tính năng xứng đáng gọi là "train", và học từ dữ liệu thật.

**Hạn chế phải nói rõ:** chỉ có giá trị khi DB đã có kha khá cuộc gọi thật. Chạy lúc
DB trống thì ra rác. → **Làm sau cùng**, sau khi ba lớp kia chạy và đã gọi thật vài
chục cuộc.

**Lớp 4 — Bảng sức khoẻ kho.** Lưới chủ đề × rổ, mỗi ô hiện số câu, ô dưới 4 câu tô
đỏ. Kèm thống kê 7 ngày: câu nào bị dùng nhiều nhất, chủ đề nào hay gặp nhất. Đây là
chỗ biến việc quản lý thành "thông minh" — nhìn thấy phải thêm câu vào đâu thay vì đoán.

### C. Dựng tiếng và cache ra đĩa

F5 chạy **đúng một lần cho mỗi cặp (câu, giọng)**, không bao giờ trong cuộc gọi.

| Lúc nào | Chuyện gì xảy ra |
|---|---|
| Lưu câu mới trong UI | F5 dựng ngay (người dùng đang ngồi trước máy, chờ ~0.5s là bình thường) → ghi `data/fillers_wav/<giọng>/<id>_<vân tay>.wav` |
| Khởi động backend | **Đọc đĩa vào RAM.** Không gọi F5 lần nào |
| Trong cuộc gọi | Trả bytes có sẵn trong RAM → gửi thẳng. GPU không bị đụng tới |

Chi phí: F5 xuất 24 kHz 16-bit mono → 60 câu × ~2s ≈ **5,8 MB RAM mỗi giọng**;
5 giọng ≈ 29 MB. Khởi động đọc 60 file WAV từ SSD ≈ vài chục ms, thay cho ~30 giây
gọi F5.

#### Vân tay — bỏ qua là thành bẫy im lặng

Tên file mang `hash(text + giọng + nfe + speed + đoạn mẫu)`. Lệch vân tay → dựng lại
đúng câu đó.

Vì sao bắt buộc: đổi `nfe` hay `speed` trong cài đặt thì câu trả lời thật đọc theo
tham số mới, còn câu đệm vẫn là tiếng cũ → **khách nghe hai chất giọng nối liền nhau
ngay đầu mỗi lượt**. Không có gì báo lỗi, log vẫn sạch. Vân tay là thứ duy nhất bắt được.

Móc vào `drop_voice` (`tts_service.py:355`) vốn đã dọn cache theo giọng.

#### Lần chạy đầu, đĩa còn trống

Dựng nền **theo thứ tự ưu tiên**: nhóm `chung` trước (cuộc gọi tới ngay lúc đó vẫn
có câu để dùng), rồi tới các chủ đề. `pick_filler` dùng những gì đã sẵn sàng, thiếu
thì rơi về tầng hẹp hơn — **không bao giờ chờ TTS**.

### D. Luật chọn

Chuỗi việc lúc chọn, toàn bộ **dưới 1ms** (khuôn đã đo trong chính dự án: lưới từ
khoá tra dữ liệu ~1ms, đúng 9/9 — `streaming_pipeline.py:610`):

| Bước | Việc | Tốn |
|---|---|---|
| 1 | Đọc `session.spec_stt[1]` — biến sẵn trong RAM | ~0 |
| 2 | Bỏ dấu chuỗi ~60 ký tự (khuôn `voicemail_detect.py:80`) | vài chục µs |
| 3 | Quét ~50 từ khoá bằng `in` | vài chục µs |
| 4 | Lọc câu theo chủ đề → rổ → ít dùng nhất | vài chục µs |
| 5 | Tra dict lấy bytes WAV | ~0 |

**Bốn tầng ưu tiên**, rơi dần khi tầng trên rỗng:

1. Đúng chủ đề + đúng kiểu lượt + độ dài vừa khít
2. `chung` + đúng kiểu lượt + độ dài vừa khít
3. `chung` + độ dài vừa khít
4. Bất kỳ, lấy câu **dài nhất** — giữ hành vi đã sửa đúng ở `tts_service.py:579`

Ba điểm khác bản hiện tại:

**a) Biết khách hỏi hay kể, thay vì đoán.** Hiện suy từ `session.turn_count > 0` và
code tự ghi chú đó là phỏng đoán (`streaming_pipeline.py:519`). Giờ đã có phiên âm →
bắt bằng lưới từ để hỏi ("bao nhiêu", "thế nào", "được không", "mấy"…). Cũng ~0ms,
nhưng đúng.

**b) "Vừa khít" chứ không chỉ "đủ dài".** Hiện chỉ đòi `ms >= min_ms`. Cần che 900ms
mà bốc trúng câu 2600ms thì câu trả lời thật bị đẩy lùi 1700ms **vô ích** — lỗi ngược
với lỗi cũ nhưng vẫn là lỗi. Luật mới: ưu tiên khoảng `[min_ms, min_ms + 800ms]`,
rỗng thì mới nới.

**c) Chống lặp bằng đếm, không bằng "tránh 3 câu vừa dùng".**
`session.dem_filler[id] += 1`; mỗi lượt chọn ngẫu nhiên **trong nhóm có số đếm nhỏ
nhất**. Nhóm 10 câu → bảo đảm dùng hết 10 câu mới lặp lại câu đầu, chắc chắn chứ
không phải xác suất. Nhóm co lại còn 2 câu vẫn luân phiên đúng, không kẹt. Bỏ được
tham số "nhớ mấy câu".

Số đếm thuộc **về phiên**, reset mỗi cuộc gọi — khách mới thì không việc gì phải
tránh câu đã dùng với khách trước. Thay `session.filler_vua_dung`
(`streaming_pipeline.py:526`).

Chủ đề đoán trật (phiên âm cụt, nghe nhầm) thì cùng lắm câu đệm nêu hơi lệch chủ đề,
không sai sự thật — đó chính là lý do chốt "nêu chủ đề chung" chứ không nêu số liệu.

Giữ nguyên: `_FILLER_BO_QUA_MS = 700` (đường nhanh thì khoảng lặng ngắn nghe tự nhiên
hơn câu đệm thừa) và `_filler_min_ms` (lấy TTFA gần đây của chính đường đó).

### E. API + UI

`backend/api/fillers.py`:

| Route | Việc |
|---|---|
| `GET /api/fillers` | Chủ đề + câu + trạng thái tiếng theo giọng |
| `POST/DELETE /api/fillers/cau` | Thêm/sửa/xoá câu — lưu là dựng tiếng ngay, trả về số ms |
| `POST/DELETE /api/fillers/chu-de` | Thêm/sửa/xoá chủ đề + từ khoá |
| `GET /api/fillers/nghe/{id}` | Nghe thử |
| `POST /api/fillers/dung-lai` | Dựng lại tiếng (một giọng / toàn bộ) |
| `GET /api/fillers/suc-khoe` | Lưới chủ đề × rổ + thống kê dùng |
| `POST /api/fillers/quet-tri-thuc` | LLM đọc `knowledge/` → đề xuất chủ đề + từ khoá |
| `POST /api/fillers/sinh-cau` | LLM sinh thêm câu cho một chủ đề + rổ |
| `POST /api/fillers/hoc-tu-cuoc-goi` | Quét `conversation_turns` → đề xuất từ khoá thiếu |

Ba route cuối chạy **offline**, không nằm trong đường gọi.

UI: trang **Câu đệm** — bảng câu lọc theo chủ đề, nghe thử từng câu, lưới sức khoẻ,
ba nút offline.

## Ranh giới các phần

| Phần | Việc | Phụ thuộc |
|---|---|---|
| `services/filler_store.py` | Đọc/ghi `fillers.json`, xác thực dữ liệu | không |
| `services/filler_topic.py` | Lưới từ khoá → `chu_de`; nhận diện câu hỏi | `filler_store` |
| `tts_service` (sửa) | Cache đĩa + vân tay + `pick_filler` mới | `filler_store` |
| `streaming_pipeline` (sửa) | `_send_filler` gọi `filler_topic` rồi `pick_filler` | hai cái trên |
| `api/fillers.py` | Route CRUD + 3 nút offline | tất cả |
| Trang UI | Bảng + lưới sức khoẻ | `api/fillers.py` |

Danh sách `FILLER_PHRASES` / `FILLER_HOP_CAU_HOI` cứng trong `streaming_pipeline.py`
bị gỡ, chuyển thành dữ liệu khởi tạo của `fillers.json`. `startup.py:82` và
`websocket.py:17` đổi sang nạp từ `filler_store`.

## Chia mốc

Spec này lớn. Chia bốn mốc, **mốc nào xong cũng chạy được và có ích ngay**, không
phải chờ hết mới thấy khác biệt.

| Mốc | Gồm | Xong thì được gì |
|---|---|---|
| **1** | `filler_store` + `fillers.json` (~60 câu soạn sẵn) + cache đĩa & vân tay + luật chọn mới | **Hết lặp.** Đây là thứ bên A đang kêu. Chưa có UI, sửa câu bằng cách sửa file |
| **2** | `filler_topic` (lưới từ khoá) + `_send_filler` chọn theo ngữ cảnh + nhận diện câu hỏi | Câu đệm bám chủ đề |
| **3** | `api/fillers.py` + trang UI + bảng sức khoẻ + nút quét kho tri thức + nút sinh câu | Bên A tự quản lý, không cần đụng code |
| **4** | Cột `filler_id` trong `latency_metrics` + thống kê dùng + nút học từ cuộc gọi | Kho tự bồi theo cuộc gọi thật |

Mốc 4 **phải để sau cùng** — nó cần dữ liệu cuộc gọi thật mới có nghĩa (xem Lớp 3).

## Kiểm chứng

Đo bằng số, không tin cảm giác:

| Kiểm | Đạt khi |
|---|---|
| Lưới từ khoá | Bộ câu mẫu → đúng chủ đề mong đợi |
| Chống lặp | Nhóm 5 câu, gọi 5 lần → ra **đủ 5 câu khác nhau** |
| Vân tay | Đổi `nfe` → dựng lại, **không** dùng tiếng cũ |
| Cache đĩa | Dựng xong, khởi động lại → **không gọi F5 lần nào** |
| Độ dài vừa khít | `min_ms=900` và có sẵn câu 2600ms → **không** chọn câu đó |
| Đo thật | Mô phỏng 10 lượt, đếm số câu đệm khác nhau. Hiện tại **2**; đạt khi ≥ **8** |

## Việc KHÔNG làm

- Không train / fine-tune mô hình nào.
- Không gọi LLM trong cuộc gọi.
- Không ghép mảnh audio (lý do ở trên).
- Không để câu đệm nêu số liệu cụ thể (lãi suất, hạn mức) — phiên âm cụt hoặc nghe
  nhầm là nói sai ngay câu đầu tiên.
