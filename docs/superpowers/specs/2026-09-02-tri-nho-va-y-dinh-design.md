# Trí nhớ hội thoại và phân biệt ý định

Ngày 2026-09-02. Bên A nêu hai vấn đề, đo ra sáu.

## 1. Việc cần làm

Bot phải **nhớ được cuộc nói chuyện**, và phải phân biệt được khách **hỏi**
hay **chê** — thay vì đọc lại đúng bảng lãi mà khách vừa chê.

## 2. Đọc được từ dự án

Đo trên máy Windows bằng chính `qwen2.5:7b` đang chạy (`prompt_eval_count`
của Ollama, không phải ước lượng):

| | Token | % cửa sổ |
|---|---|---|
| Lời dặn hệ thống, không tri thức | 1053 | 51% |
| Lời dặn + tri thức tra được (top_k=2) | **1414** | **69%** |
| Chừa cho câu trả lời (`LLM_MAX_TOKENS=150`) | 150 | 7% |
| **Còn cho hội thoại** | **484** | 24% |

Một lượt hỏi–đáp ~75 token → **nhớ được ~6 lượt**, sau đó Ollama cắt phần đầu
**không báo gì**. `.env` trên Windows không đặt `LLM_NUM_CTX` nên lấy mặc định
2048 ở `backend/config.py:18`.

Đo trên bộ phân loại tình huống thật (`chon_tinh_huong`, 30 tình huống):

| Khách nói | Bot hiểu | Điểm |
|---|---|---|
| "lãi suất bao nhiêu" (hỏi) | hoi_lai_suat | 1.000 |
| "lãi cao thế" (**chê**) | hoi_lai_suat | 0.923 |
| "lãi cao quá em ơi" (**chê**) | hoi_lai_suat | 0.849 |
| "cơ chế thế nào" | *không nhận ra* | 0.622 |
| "vay như nào" | hoi_lai_suat | 0.832 |

Kho 30 tình huống **không có mục nào cho việc khách chê**.

Thêm một tình huống "chê lãi" thì tách được **8/8** trên câu trọn, biên
0.05–0.10. Nhưng câu đệm chạy trên câu **cụt**: `"lãi cao kh…"` (khách đang
nói "không", tức HỎI) bị chấm CHÊ, biên 0.026. Nên riêng thêm ví dụ là
không đủ — cần tín hiệu độc lập với chữ.

Khác:
- `session.history` gom đủ và gửi nguyên vẹn cho mô hình. Code đúng; cửa sổ hẹp.
- Bảng `conversation_turns` đã lưu đủ; hàm đọc (`db.py:617`) chỉ phục vụ báo cáo.
- `session.tinh_huong` chỉ dùng chọn câu đệm, không đi tiếp sang mô hình.
- Kho tình huống và `knowledge/*.md` là hai kho rời, khớp bằng tay.

## 3. Giả định tôi chốt thay bên A

| Chốt | Nếu sai thì đổi gì |
|---|---|
| Nới cửa sổ lên 8192, **không đụng nội dung lời dặn** ở mốc 1 | Lời dặn là vùng đã tốn nhiều công chỉnh (9 lỗi trả lời sai đã sửa). Cắt nó có thể làm hỏng chất lượng đang có. Nếu VRAM không cho phép nới thì mới quay lại cắt lời dặn, và phải đo lại chất lượng |
| Cổng ngữ cảnh dựa vào **lời bot đã nói**, không dựa lời khách | Lời bot là chữ mình sinh ra, sạch 100%, không qua tai máy méo |
| Cổng chỉ **bật thêm** nhóm chê, không tắt nhóm hỏi | Khách vẫn được hỏi lại lãi lần hai |
| Bảng hỏi-đáp **bổ sung**, tra trước, trượt thì rơi về tri thức cũ | Bên A đã chốt 2026-09-02 |
| Nhóm chê **đọc thẳng** lời thoại trong bảng, không qua mô hình | Lời xử lý phản đối đụng cam kết với khách, cần đúng từng chữ |
| Bảng dùng lại `bge-m3` đang chạy | Không nạp thêm mô hình, VRAM không đổi |

## 4. Cách làm và cái giá

**Nới cửa sổ** 2048 → 8192: bộ nhớ đệm khoá-giá trị của qwen2.5-7B tốn
~56 KB mỗi token, nên thêm ~340 MB VRAM. Phải đo thật, không suy ra.

**Bỏ bẫy im lặng**: đọc `prompt_eval_count` có sẵn trong phản hồi Ollama,
ghi vào số đo mỗi lượt, kêu lên khi vượt 85% cửa sổ. Không ước lượng,
không thêm chi phí.

**Phân biệt hỏi/chê**: thêm nhóm tình huống chê, và một cổng ngữ cảnh
`session.da_tu_van` — chỉ bật nhóm chê sau khi bot đã thật sự nói về chủ đề đó.

**Cái giá:** thêm một lần chấm điểm trước khi gọi mô hình (~30–60ms CPU,
phải đo). Bảng hỏi-đáp phải có người soạn — code chỉ dựng chỗ.

## 5. Chỗ tôi hiểu khác lời bên A

- Bên A nói "thêm phân tích context cuộc trò chuyện". Tôi **không** để mô hình
  đọc lại cả hội thoại để suy đoán — chậm và không chắc. Dùng đúng một cờ:
  *bot đã tư vấn chủ đề đó chưa*. Hẹp hơn lời nói, nhưng chính là ví dụ bên A
  đưa ra, và chắc chắn đúng vì không đi qua tai máy.
- Kế hoạch trình bày là "nới cửa sổ **+ rút gọn lời dặn**". Tôi **tách phần rút
  gọn ra khỏi mốc 1** — xem mục 3, dòng đầu.

## 6. Phải chốt trước khi làm tiếp

- Nhóm chê làm sẵn 4 mục: chê lãi cao, chê phí cao, chê hạn mức thấp, so sánh
  ngân hàng khác. Thiếu mục nào bên A bổ sung.
- Lời thoại xử lý phản đối: tôi viết bản nháp, **người phụ trách nghiệp vụ phải
  duyệt** — nói sai chỗ này là chuyện cam kết với khách.
- "Không xem lại được cuộc cũ" (mốc 6): cần biết nút xem chi tiết **báo lỗi**,
  **trống trơn**, hay bên A chưa thấy nó ở đâu.

## Thứ tự làm (bên A duyệt 2026-09-02)

1. **Nới cửa sổ nhớ** + bỏ bẫy im lặng — gốc rễ
2. **Phân biệt hỏi/chê** — lỗi khách nghe thấy rõ nhất
3. **Nối lại phiên khi tải lại trang**
4. **Bảng hỏi-đáp có cột câu đệm**
5. **Nhớ cuộc gọi trước**
6. **Xem lại cuộc cũ** — sau khi biết nó hỏng kiểu gì

## Nghiệm thu bằng số đo

| Mốc | Đo bằng |
|---|---|
| 1 | ✅ **XONG 2026-09-02.** Cửa sổ 2048 → 8192. VRAM 4.6 → 5.2 GB (card còn trống 3.4 GB). Tốc độ sinh chữ **không đổi**: 8.75 → 8.71 ms/chữ. 782 test xanh trên máy Windows |
| 2 | ✅ **XONG 2026-09-04.** `scripts/thu_hoi_hay_che.py`: **21/23**, chê nhầm khi chưa tư vấn = **0**. Kết quả trùng nhau trên Mac và Win. 792 test xanh |
| 3 | Tải lại trang giữa cuộc, lượt kế tiếp bot vẫn nhắc đúng thứ vừa nói |


## Đã đảo ngược trong lúc làm

| **Ngưỡng cảnh báo: 85% cửa sổ → đếm số lượt chứa được** | Lý do cũ nghe hợp lý: "sắp đầy thì kêu". Nhưng cấu hình hỏng thật (1414 + 150 trên 2048) mới chiếm **76%** — mọi ngưỡng quanh 85% đều cho nó lọt, trong khi nó chỉ nhớ nổi 6 lượt. Thước đo đúng là *chứa được mấy lượt so với một cuộc tư vấn thật*. Xem `services/cua_so_nho.py`. |
| **VRAM tăng 500 MB → 600 MB** | Ước lượng theo lý thuyết (56 KB/token) ra 340 MB; đo thật ra 600 MB. Vẫn nhận vì card còn trống 3.4 GB. |
| **Chọn 8192 chứ không 4096** | 4096 tưởng đủ (33 lượt) nhưng tính theo lượt NGẮN 75 token. Lượt thật ~150 token → 4096 chỉ cho 17 lượt, **dưới** mức 20 lượt cần. |

## Đo được trong lúc xác minh

Chạy thật qua `stream_response` với 10 lượt lịch sử + tri thức: lời dặn + hội thoại
= **1957 token**. Ở cửa sổ 2048 thì còn đúng **0 token** — Ollama đang cắt bỏ hoàn
toàn phần đầu. Đây là bằng chứng trực tiếp cho lỗi "nói chuyện một lúc là bot quên".


## Mốc 2 - ghi thêm sau khi làm

**Không thêm cột vào bảng `tinh_huong`.** Ánh xạ điều kiện (`DIEU_KIEN_NGU_CANH`,
3 dòng) để trong code. Lý do: bảng đó đang có dữ liệu thật trên máy chạy, nâng
cấp cơ sở dữ liệu cho một ánh xạ gần như không đổi là đắt hơn cái nhận được.
Đánh đổi: thêm tình huống chê mới qua trang quản lý thì phải sửa thêm trong code
— `tests/test_ngu_canh_luot.py` bắt được nếu quên.

**Ghi chủ đề trong `add_turn`, không ghi ở đường thoại.** Ba đường (gọi ra, gọi
vào, chat) đều đi qua đó; vá từng chỗ là chắc chắn sót một chỗ.

**Khách cắt lời thì rút lại chủ đề của lượt đó.** Bot mới nói "Dạ lãi suất bên
em" mà bị cắt thì khách CHƯA NGHE mức lãi nào. Vẫn tính là đã tư vấn thì cổng mở
sớm, và câu hỏi lãi ngay sau đó bị chấm thành chê.

**`so_sanh_ben_khac` cố ý không có điều kiện.** Khách so sánh ngay từ lượt đầu là
chuyện thường, và đo được nó không lẫn với "hỏi lãi" (0.638, dưới ngưỡng).

### Hai câu còn sai, đều KHÔNG do cổng ngữ cảnh

| Câu | Ra | Vì sao |
|---|---|---|
| "bên em lãi bao nhiêu phần trăm" | *không nhận ra* (0.705) | Dưới ngưỡng 0.75 → rơi về rổ chung, đúng hành vi cũ, không tệ hơn |
| "nhắc lại lãi suất giúp anh" | `xin_gui_tai_lieu` (0.841) | Lỗi sẵn có của kho: "nhắc lại / gửi" lẫn với xin tài liệu. Sửa bằng cách chỉnh `vi_du`, không thuộc mốc này |

### Cái giá đã trả

Thêm 4 tình huống × 4 mẩu mở đầu = **672 clip câu đệm phải dựng mới**
(16 mẩu × 42 câu đuôi). Log máy Win: `5082 đọc từ đĩa, 672 dựng mới, tổng 5754`.
Dựng xong trong ~3 phút, làm chủ động lúc khởi động lại chứ không để rơi vào
lúc có cuộc gọi thật.
