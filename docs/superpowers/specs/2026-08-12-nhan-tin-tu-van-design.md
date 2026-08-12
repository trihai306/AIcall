# Nhắn tin tư vấn — trang kiểm thử bằng chữ

**Ngày:** 12/08/2026 · **Trạng thái:** đã làm xong

## Vấn đề

App chỉ tư vấn được bằng tiếng: gọi điện qua phone farm, và trang *Hội thoại*
dùng micro. Khi sửa kịch bản hoặc kho tri thức, muốn biết AI trả lời ra sao thì
phải nói vào micro từng lượt — chậm, và không thấy được **vì sao** nó trả lời
như vậy.

Hai lỗi tái diễn nhiều nhất (xem `docs/DAC_TA_TINH_NANG_CON_THIEU.md` và ghi chú
lỗi trả lời sai) đều là lỗi *không nhìn thấy được*:

- **RAG lạc sản phẩm** — top-k kéo về tài liệu sản phẩm bên cạnh, LLM lấy số ở
  đó. Đo được: đang tư vấn vay tín chấp (7.9%) mà đọc ra 6.5% của vay mua nhà.
- **Tưởng model trả lời** trong khi câu đó ra từ bảng cứng `luot_thuong_gap` —
  sửa prompt cả buổi không đổi được gì.

## Phạm vi

Công cụ **kiểm thử nội bộ**. Không lưu báo cáo, không đếm vào thống kê phiên
gọi, không gửi Telegram, không phục vụ khách thật.

## Quyết định

| Câu hỏi | Chốt |
|---|---|
| Kênh | Khung chat chữ ngay trong app, không đụng SIM |
| Vị trí | **Trang riêng "Nhắn tin"**, không sửa trang Hội thoại |
| Phát tiếng | Mặc định chỉ chữ; mỗi câu trả lời có nút **nghe thử** |
| Hiện thêm | Nguồn RAG + điểm khớp · cờ đường đi · số đo từng chặng · lưới chặn |

**Vì sao trang riêng.** Trang Hội thoại *cố ý* bỏ ô gõ chữ — chú thích tại
`frontend/index.html` ghi rõ: *"Gọi điện thật thì khách không gõ được, nên bỏ
hẳn ô nhập để mọi thứ đo được đều là số của đường thoại."* Hiện lại ô gõ ở đó là
xóa chính lý do ấy.

## Kiến trúc

```
Trang Hội thoại ──ws #1──┐
  (micro, thuần thoại)   │
                         ├─► /ws/call/{sid} ─► process_turn()           [KHÔNG ĐỔI]
Trang Nhắn tin ──ws #2──┘                  └─► process_text_turn(soi=True)
  (gõ chữ, phiên riêng)                          │
                                                 ├─ bỏ câu đệm
                                                 ├─ bỏ sinh tiếng
                                                 └─ RAG trả kèm chi tiết
```

**Nguyên tắc:** đường thoại không đổi hành vi. Mọi thứ mới là nhánh rẽ có cờ,
mặc định tắt.

### Bốn mảnh thay đổi

**1. `rag_service.py` — thôi vứt điểm khớp**

`retrieve()` cũ hỏi ChromaDB lấy `distances` + `metadatas` rồi trả về mỗi chuỗi
ghép, vứt cả hai. Thêm `retrieve_chi_tiet()` trả `(ngữ_cảnh, chi_tiết)` với mỗi
phần tử `{doan, diem, nguon, bi_loc}`; `retrieve()` gọi lại nó rồi bỏ phần chi
tiết — một nguồn sự thật, không nhân đôi logic.

`_loc_theo_san_pham` (trả danh sách đã lọc) đổi thành `_mat_na_loc` (trả mặt nạ
`True`=giữ). Nhìn phần còn lại thì không suy ra được đoạn nào bị bỏ, mà chính
đoạn bị bỏ mới là dấu vết của lỗi lạc sản phẩm.

`diem = 1 - distance` (collection dùng `hnsw:space=cosine`). Thiếu `distance`
thì để `None`, **không** bịa số 0 — 0 nghĩa là khớp hoàn hảo.

**2. `streaming_pipeline.py` — cờ `soi`**

`process_text_turn(..., soi=False)` và `_generate_response(..., soi=False)`.
Khi `soi=True`:
- bỏ `_send_filler` (câu đệm chỉ có nghĩa khi khách đang chờ **tiếng**)
- bộ tiêu thụ TTS đặt `song = [None] * len(dan)` thay vì gọi F5. Vòng cắt mảnh
  và sự kiện `response_chunk` giữ nguyên, nên chữ hiện ra đúng từng mảnh y như
  đường thoại — chỉ bỏ đúng phần chiếm GPU.
- `metrics["rag_nguon"]` + `metrics["rag_truy_van"]`

**3. `websocket.py` — loại tin `text_soi`**

Tách hẳn loại tin thay vì thêm cờ vào `text`: trang Hội thoại và các chỗ gọi
`sendText()` cũ không phải biết gì về chế độ soi, nên không có đường nào bật
nhầm nó cho đường thoại.

**4. `frontend` — trang `page-messaging`**

WebSocket **riêng** (`msgWs`, phiên riêng). Dùng chung `ws` của app.js là hai
trang đổ vào cùng một `CallSession`: lịch sử lẫn nhau và AI coi lượt gõ với lượt
nói là một cuộc. Đăng ký qua lớp bọc `switchPage` trong `trang_moi.js` theo đúng
quy ước file đó.

Ô chọn giọng cho nút *nghe thử* nhét vào mảng `selectors` của `loadVoices()` sẵn
có — đoạn chọn giọng mặc định ở đó đã phải chữa lỗi chọn nhầm giọng một lần rồi,
viết lại lần hai là mời lỗi đó quay lại.

## Ràng buộc đã gặp

- **Không build lại được Tailwind** (`npx` offline). Mọi lớp CSS dùng trong trang
  mới đều đã đối chiếu với `frontend/tailwind.css` biên dịch sẵn. Lớp **không**
  có, đã tránh: `px-1.5`, `max-w-[75%]`, `line-through`, `italic`, `pl-2`.
  `.btn`, `.btn-primary`, `.chip` nằm ở `style.css` viết tay nên dùng được.
- Chip phiếu soi **không** dùng lớp `.chip`: `style.css` nạp sau `tailwind.css`
  nên `.chip{color}` đè mọi lớp `text-*`.

## Kiểm chứng

`tests/test_rag_chi_tiet.py` — 6 test, không cần pytest-asyncio (gọi bằng
`asyncio.run`), không nạp ChromaDB/bge-m3 thật.

Chạy thật trên Mac (LLM `qwen2.5:3b`, **TTS và STT không nạp được**) — chính môi
trường đó chứng minh chế độ soi không phụ thuộc TTS:

- Câu *"vay tín chấp cần giấy tờ gì ạ"* → tái hiện đúng ca đo ghi trong docstring
  `_mat_na_loc`: `vay_mua_nha.md` xếp **hạng cao hơn** (0.657) `vay_tin_chap.md`
  (0.611), và lưới lọc bắt đúng — phiếu soi hiện **ĐÃ LỌC**.
- Log: `Turn complete (soi): TTFA=-ms ... 2 mảnh (đã cắt, không sinh tiếng)`.
- Đường `text` cũ chạy song song: `rag_nguon` **không** có trong `metrics` →
  dữ liệu chẩn đoán không rò sang đường thoại.
- Toàn bộ suite: 300 qua, 12 lỗi **có sẵn từ trước** ở `test_thoi_luong_ep.py`
  (thuộc `tts_service.py`, không liên quan — đã đối chứng trên code gốc).

## Bẫy đã mắc khi làm

**Chế độ soi dựng lại đúng cái log gây hiểu nhầm đã tốn một buổi truy lỗi.**
Bỏ câu đệm khiến lượt rơi xuống nhánh cuối và in
`WARNING: KHÔNG có filler → khách chờ im lặng` — trong khi chế độ soi không có
khách và không có tiếng nào để chờ. Chú thích ngay phía trên nhánh đó đã cảnh báo
chính xác chuyện này. Đã thêm nhánh `elif soi` riêng.

### Đã kiểm trên máy Windows thật (RTX 5070, stt/llm/tts/rag đều ok)

| Việc | Kết quả |
|---|---|
| Lượt soi | `tổng 742ms` (Mac 4836ms), `TTFA=-ms` — không sinh tiếng |
| Lưới lọc | `vay_mua_nha.md` (0.657) xếp **trên** `vay_tin_chap.md` (0.611) → **ĐÃ LỌC** |
| Câu trả lời | *"sao kê lương **3 tháng**"* — đúng vay tín chấp, không lấy **6 tháng** của mảnh bị lọc |
| Nút nghe thử | `POST /api/voices/test-tts` 200 · `giong_heu` · 5170ms tiếng sinh trong 460ms (RTF 0.089) |
| Ô chọn giọng | 15 giọng, tự chọn đúng `giong_heu (mặc định)` |
| Test suite | **281 qua, 0 lỗi** (bỏ `test_chia_ca_luot.py` — việc đang treo, xem ghi chú Windows) |

Bản bị lọc ghi *"sao kê lương 6 tháng"* còn câu trả lời nói *"3 tháng"* — đây là
bằng chứng trực tiếp lưới lọc đã chặn đúng con số của sản phẩm khác, tức lỗi mà
trước đây chỉ đoán được thì giờ nhìn thấy.

## Bổ sung: thanh trượt tốc đọc

Thêm vào header trang Nhắn tin: `TỐC [────] 1.38 ↺`, đồng bộ theo giọng đang
chọn. Dùng lại API sẵn có `POST/DELETE /api/voices/{ten}/speed`. Đổi tốc xong
đọc lại NGAY chính câu AI vừa trả lời (không phải câu mẫu cố định) — chỉnh tốc
mà không nghe lại thì phải mò.

`width` và `accent-color` đặt **inline**: lớp `w-24`/`accent-violet-500` mà trang
Giọng nói dùng KHÔNG có trong `tailwind.css` biên dịch sẵn, nên thanh trượt bên
đó đang mất cả cỡ lẫn màu.

Giọng chưa biết tốc thì **khoá thanh và hiện `—`**, không hiện 1.00: hiện số bịa
rồi người dùng kéo từ đó là ghi đè tốc thật bằng một số vô căn cứ.

### Bẫy đã mắc: chỉnh tốc nghe ra tốc CŨ

Bản đầu tạo `new Audio().play()` mới mỗi lần mà **không dừng cái đang chạy**. Kéo
thanh vài nhịp là các bản tiếng chồng lên nhau, và người nghe kết luận *"chỉnh
tốc không ăn, vẫn ra tốc cũ"* — thật ra tiếng tốc cũ vẫn đang phát đè lên tiếng
tốc mới. Người dùng báo đúng triệu chứng này ngay lần dùng đầu.

Dừng thẻ Audio thôi **chưa đủ**: yêu cầu gửi trước có thể về SAU yêu cầu mới, lúc
đó nó chưa phát nên không có gì để dừng. Phải có thêm số thứ tự lượt.

Sửa: một thẻ `msgTieng` dùng chung + biến đếm `msgLuotPhat`. Mỗi chỗ phát lấy số
lượt TRƯỚC khi gọi mạng; `msgPhatTieng` bỏ bản nào không phải lượt mới nhất.
`msgDungTieng()` gọi ở: thả thanh trượt, bấm nghe thử, xóa hội thoại, rời trang.

### Lỗi có sẵn mà thanh trượt này làm lộ ra

`/api/voices` báo tốc **khác nhau tuỳ giọng đã được nạp vào RAM hay chưa**, với
mọi giọng không có tệp `.speed` riêng:

| Giọng | Trước khi dùng | Sau khi dùng 1 lần |
|---|---|---|
| `heu_b` | 1.06 | **1.0** |

Không tệp nào bị ghi. Nguyên nhân ở `toc_do_cua`: nhánh `voice not in self._voices`
vốn chỉ để chữa *tên phiên cũ đã xoá*, nhưng `list_voices` duyệt các tệp `.wav`
CÓ THẬT, nên mọi giọng chưa nạp đều mượn nhầm `.speed` của giọng mặc định
(`giong_heu` = 1.06) thay vì rơi về `settings.f5tts_speed` = 1.0.

Cùng họ với lỗi `F5TTS_SPEED=0.64` đã chữa ở `f4c6614`. **Chưa sửa** — sửa thì
phải bó nhánh mượn kia lại chỉ cho tên không ứng với tệp `.wav` nào, và việc đó
đổi hành vi cuộc gọi nên cần chốt riêng.

## Bổ sung: phiên web giờ mang kịch bản thật

Trang Nhắn tin sinh ra để **kiểm thử**, nhưng `websocket.py` tạo phiên **không
kèm kịch bản** — đo được `scenario_id: ""`. Nên toàn bộ trang Hội thoại / Nhắn
tin chạy bằng `bank_name`/`agent_name` trong `.env`, tức **kiểm thử trên một cấu
hình khác cuộc gọi thật**. Đổi tên tổ chức trong kịch bản rồi thử trên web vẫn
nghe tên cũ, không log nào nhắc.

Đã sửa: phiên web nạp `scenarios_db.resolve("")`, và ba đường xưng tên gom về
`scenarios_db.ten_to_chuc` / `ten_nhan_vien`:

| Đường | Trước | Sau |
|---|---|---|
| `llm_service.build_system_prompt` | tự đọc kịch bản | dùng chung hàm |
| bảng lượt thường gặp (`streaming_pipeline`) | `settings.bank_name` | dùng chung hàm |
| câu mở đầu cuộc gọi (`phone_call_service`) | `settings.bank_name` | dùng chung hàm |

Trước đó ba đường lệch nhau: trong **cùng một cuộc gọi**, câu chào sẵn xưng một
tên còn câu mô hình sinh xưng tên khác.

`config.bank_name`/`agent_name` giữ lại nhưng **chỉ để gieo mầm** (`ensure_default`
khi bảng còn trống) và làm lưới cuối. `tests/test_ten_to_chuc.py` dùng
`inspect.getsource` chặn việc đọc thẳng `settings.*` quay lại.

**Kiểm chứng:** đặt kịch bản thành *"Ngân hàng Thử Nghiệm"* trong khi `.env` vẫn
ghi *"Quân đội"*, **không restart** → chat trả lời *"Ngân hàng Thử Nghiệm"*.
Trước bản sửa nó sẽ trả lời *"Quân đội"*.

## Việc còn lại

- **Nhánh này thiếu 1 commit của `main`** (`09a2184`, kéo 225 file từ Windows về).
  Đó là lý do trên Mac có 12 lỗi ở `test_thoi_luong_ep.py` còn Windows thì không:
  máy Windows chạy bản `tts_service.py` của `main`, nhánh này chưa có. Rebase lên
  `main` trước khi gộp.
- `09a2184` có sửa `backend/api/websocket.py`. Bản đẩy sang Windows đã **hoà giải**
  (giữ nguyên phần của `main`, chỉ nối thêm khối `text_soi`), không đè mất.
