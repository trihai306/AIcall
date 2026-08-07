# Hướng dẫn sử dụng — Bot autocall AI

Tài liệu cho người vận hành. Phần kỹ thuật xem [ARCHITECTURE.md](ARCHITECTURE.md),
phần đối chiếu hợp đồng xem [DAC_TA_TINH_NANG_CON_THIEU.md](DAC_TA_TINH_NANG_CON_THIEU.md).

---

## 1. Khởi động

```bash
bash scripts/start_services.sh
```

Mở trình duyệt: **http://localhost:8000**

Hệ thống chạy **offline hoàn toàn** — không cần Internet, trừ đúng một việc:
gửi báo cáo qua Telegram (mục 8).

Màn hình đầu tiên là **Tổng quan**: cuộc gọi hôm nay, chiến dịch đang chạy,
trạng thái máy điện thoại.

---

## 2. Thanh điều hướng

| Nhóm | Có gì | Ai dùng |
|------|-------|---------|
| **Vận hành** | Tổng quan · Hội thoại · Danh bạ gọi · Báo cáo | Hàng ngày |
| **Cấu hình** | Kịch bản · Nguồn dữ liệu · Giọng nói · Thiết bị · Cài đặt | Lúc thiết lập |
| **Hệ thống** | Phiên gọi · Test giọng · Training · Cài Model · Benchmark · Logs | Kỹ thuật |

---

## 3. Kịch bản — bot nói gì

**Cấu hình → Kịch bản**

Một kịch bản quyết định: bot xưng tên gì, làm ở đâu, chào thế nào, luật riêng
của ngành, ví dụ hỏi–đáp, khi nào nối máy cho người thật.

**Các luật chung không sửa được ở đây** và đó là chủ ý: tối đa 2 câu mỗi lượt,
cấm bịa số (mọi con số phải lấy từ tài liệu), cấm liệt kê quá hai thứ, đoán ý
khi bản ghi sai chính tả. Mỗi luật là bản vá cho một lỗi đã xảy ra thật.

### Tạo kịch bản cho ngành mới

1. Bấm **+ Kịch bản mới**
2. Điền tên tổ chức, tên nhân viên, câu chào
3. **Luật riêng của ngành** — mỗi dòng một luật. Ví dụ ngành bảo hiểm:
   `Không được hứa chắc chắn về quyền lợi chi trả.`
4. **Ví dụ hỏi–đáp** — dạy mô hình ĐỘ DÀI câu trả lời.
   > ⚠️ Đừng đặt con số thật vào ví dụ. Mô hình sẽ chép nguyên con số đó ra trả
   > lời khách. Đây là lỗi đã xảy ra thật: ví dụ ghi "6.5%" trong khi tài liệu
   > ghi 7.9%, và bot báo cho khách mức thấp hơn 1.4 điểm phần trăm.
5. Bấm **Lưu**, rồi **Chạy thử** để xem bot trả lời thế nào trước khi gọi thật.

### Mang kịch bản sang máy khác

**Tải form mẫu** → điền → **Nhập từ file**. Hoặc **Xuất file** từ kịch bản có sẵn.

---

## 4. Danh bạ và chiến dịch

**Vận hành → Danh bạ gọi**

### B1 — Nạp số

**Nhập danh sách** → chọn file CSV (xuất từ Excel) hoặc dán danh sách số.

Hệ thống tự nhận các cột `phone`, `name`, `product`, `note` (kể cả tiêu đề tiếng
Việt: "Số điện thoại", "Họ tên"…). **Ba cột lạ đầu tiên** được giữ nguyên tên và
trở thành cột lọc trong báo cáo — ví dụ "Chi nhánh", "Nhóm khách".

Số điện thoại được chuẩn hoá tự động: `0912 345 678`, `+84912345678`,
`0084912345678` được hiểu là cùng một thuê bao.

### Nhập số từ chiến dịch cũ

**Nhập từ chiến dịch khác** → chọn chiến dịch nguồn → chọn trạng thái
(`busy`, `no_answer`).

> Số được **chuyển** sang chiến dịch mới, không nhân bản — một số chỉ nằm ở một
> chiến dịch tại một thời điểm. Lịch sử các lần gọi cũ vẫn tra được đầy đủ.

### B2 + B3 — Cấu hình rồi chạy

Chọn một chiến dịch ở hàng chip, khối **Chạy chiến dịch tự động** hiện ra:

| Mục | Ý nghĩa |
|-----|---------|
| Kịch bản | Bot nói theo kịch bản nào |
| Giọng đọc | Giọng TTS |
| Máy gọi | Chọn nhiều máy để gọi song song (giữ Ctrl) |
| Số cuộc gọi cùng lúc | Không vượt quá số máy đã chọn |

Bấm **Cài đặt khác** để mở phần B3:

- **Ngày bắt đầu / kết thúc**
- **Khung giờ chạy** — mặc định 08:00–11:30 và 13:30–17:00, thứ 2–6.
  Ngoài khung giờ hệ thống tự đợi, tới giờ tự chạy tiếp. Cuộc gọi đang nói khi
  hết giờ được **nói nốt**, không cắt ngang.
- **Gọi lại khi**: không bắt máy / máy bận / vào hộp thư thoại — kèm số lần tối
  đa và giãn cách (phút).
- **Khi vào hộp thư thoại**: tắt máy ngay (mặc định) hoặc vẫn nói tiếp.
- **Nhận diện giới tính** và **Ghi âm cuộc gọi**.

Bấm **Bắt đầu**. Cài đặt được lưu tự động trước khi chạy.

**Tạm dừng** không cắt cuộc đang nói — nó chỉ ngừng nhận số mới.

Tắt app giữa chừng thì chiến dịch chuyển sang *tạm dừng*, không mất số nào. Mở
lại bấm **Tiếp tục**.

---

## 5. Nhận cuộc gọi đến

**Cấu hình → Thiết bị → Nhận cuộc gọi đến**

Bật cho từng máy, chọn kịch bản inbound và số giây đợi trước khi bắt máy (mặc
định 2 giây — bắt ngay hồi chuông đầu nghe rất máy móc).

Khi có cuộc gọi tới, bot bắt máy, chào **một câu ngắn** rồi im để khách nói.
Số đã có trong danh bạ thì bot chào đích danh: *"Dạ em chào anh Nam ạ, em nghe ạ."*

Chỉ máy trong phone farm (kết nối ADB) làm được.

---

## 6. Chuyển tiếp cho người thật

Khai trong **Kịch bản**: số điện thoại chuyên viên + điều kiện chuyển tiếp.

| Điều kiện | Khi nào kích hoạt |
|-----------|-------------------|
| Khách đòi gặp người thật | Khách nói "cho tôi gặp nhân viên", "đây là máy hay người?"… |
| Bot bí 2 lượt liên tiếp | Bot phải nói "em sẽ ghi nhận…" hai lượt liền |
| Không có tài liệu 2 lượt liên tiếp | Tra kho tri thức không ra gì |
| Vượt số lượt tối đa | Cuộc gọi dài hơn `max_turns` |

**Liên tiếp**, không phải cộng dồn — khách hỏi lạc đề rồi quay lại chủ đề là
chuyện bình thường.

Bot **luôn báo trước** khi nối máy. Nếu chuyên viên bận, bot quay lại xin lỗi
khách chứ không để khách chờ trong im lặng.

---

## 7. Báo cáo

**Vận hành → Báo cáo**

Lọc theo: khoảng thời gian · chiến dịch · kết quả · chất lượng · nhãn ·
thời lượng · giới tính · hướng gọi · tìm trong nội dung hội thoại.

### Chất lượng — hệ thống tự chấm

| Giá trị | Nghĩa |
|---------|-------|
| Có phản hồi | Khách nói từ 2 lượt trở lên |
| Ít phản hồi | Khách nói đúng 1 lượt |
| Không phản hồi | Bắt máy nhưng không nói gì |
| Dập máy | Bắt máy rồi cúp trong 10 giây |
| Hộp thư thoại | Máy trả lời tự động |
| Không nghe máy | Không ai bắt / máy bận |

### Nhãn — người dùng bấm

Ba nhãn có sẵn: **Quan tâm**, **Không quan tâm**, **Follow chăm sóc thêm**.

Chọn nhiều dòng rồi dùng ô **Gắn nhãn hàng loạt**.

AI có đề xuất nhãn (hiện mờ, có dấu `?`) nhưng **không tự gắn** — nhãn chính
thức luôn do người dùng quyết.

### Ghi âm

Nghe ngay trong bảng. File là **stereo hai kênh**: trái là khách, phải là bot —
nghe lại biết ngay ai nói gì kể cả khi hai bên nói đè lên nhau.

### Tóm tắt ý chính

Chạy tự động sau mỗi cuộc gọi (xếp hàng, không làm chậm cuộc gọi tiếp theo).
Bấm **Tóm tắt các cuộc còn thiếu** để chạy bù cho dữ liệu cũ.

### Xuất Excel

**Xuất CSV** xuất đúng tập đang lọc, không phải chỉ trang đang xem.

---

## 8. Gửi báo cáo qua Telegram

**Cấu hình → Cài đặt → Gửi báo cáo qua Telegram**

Lấy token và chat_id:

1. Nhắn `@BotFather` trên Telegram, gõ `/newbot`, lấy **token**
2. Nhắn một câu bất kỳ cho bot vừa tạo
3. Mở `https://api.telegram.org/bot<TOKEN>/getUpdates`, lấy **chat.id**

Ba loại tin, tick chọn từng loại:
- **Mỗi cuộc** — sau mỗi cuộc gọi thành công
- **Cuối ngày** — tổng hợp lúc 18:00
- **Xong chiến dịch**

Bấm **Gửi thử** để kiểm tra ngay. Nếu sai token, hệ thống báo đúng lỗi Telegram
trả về.

> Gửi tin thất bại **không bao giờ** làm dừng chiến dịch.

---

## 9. Nguồn dữ liệu ngoài

**Cấu hình → Nguồn dữ liệu**

Hai chế độ khác hẳn nhau:

### Tri thức chung (`rag`)

Bảng giá, biểu phí, danh mục sản phẩm. Mỗi dòng thành một mẩu văn bản, nạp vào
kho tri thức, bot **tìm gần đúng theo nghĩa**.

Thêm nguồn → **Xem trước** để kiểm cột → **Nạp lại**. Nạp xong có hiệu lực ngay
ở cuộc gọi kế tiếp, không cần khởi động lại.

### Tra theo khách (`lookup`)

Dư nợ, đơn hàng, hồ sơ. Khai **cột khoá** (ví dụ `so_dien_thoai`), hệ thống
khớp **chính xác** theo số điện thoại của khách đang gọi và chèn thông tin đó
vào ngữ cảnh trước khi bot trả lời.

Chế độ này đọc thẳng từ file mỗi lần tra — sửa file Excel là có hiệu lực ngay,
không cần nạp lại.

> Chỉ nhận **đường dẫn file trên máy**. Đường dẫn `http://` bị từ chối — hệ
> thống chạy offline 100% theo hợp đồng.

---

## 10. Giọng nói

- **Cấu hình → Giọng nói** — quản lý giọng có sẵn
- **Hệ thống → Test giọng** — nghe thử
- **Hệ thống → Training giọng** — thu 60 câu theo kịch bản rồi fine-tune giọng riêng

Vùng miền: đặt `STT_VUNG_MIEN` trong `.env` (`bac` / `trung` / `nam`, để trống
là không mồi). **Đo trước khi bật:**

```bash
python scripts/do_vung_mien.py --so-sanh-moi
```

Mồi vùng miền lợi hại lẫn lộn — nó nghiêng bộ nhận dạng về chính tả chuẩn của
vùng đó, nhưng câu nào không thuộc miền đó lại dễ bị kéo lệch. Chỉ bật khi số đo
nói là có lợi.

---

## 11. Xử lý sự cố

| Triệu chứng | Nguyên nhân thường gặp |
|-------------|------------------------|
| Bấm số nhưng không ai nghe máy, mọi số đều vậy | SIM hết tiền · máy đang khoá màn hình · hộp chọn SIM đang hiện. Ba thứ này nhìn từ hệ thống giống hệt nhau — cầm máy lên xem. |
| Khách nói mà bot im | Máy chủ Whisper chưa chạy: `bash whisper_server/start.sh` |
| Bot trả lời nhưng không có tiếng | TTS nạp hỏng — xem **Logs**. Hệ thống vẫn chạy ở chế độ chỉ văn bản. |
| Bot đọc sai số tiền / lãi suất | Kiểm mục **Ví dụ hỏi–đáp** trong kịch bản: có con số thật trong đó không? |
| Chiến dịch không chạy dù đã bấm Bắt đầu | Đang ngoài khung giờ — dòng tiến độ ghi rõ lúc nào mở lại. |
| Không có bản ghi âm | Chiến dịch tắt "Ghi âm", hoặc máy không phải loại ADB |
| Ổ đĩa đầy | **Cài đặt → Ghi âm cuộc gọi → Dọn ổ đĩa** |
| Chưa nhận cuộc gọi đến | Máy phải là loại ADB, và phải bật riêng cho từng máy |

**Logs** (Hệ thống → Logs) là nơi xem đầu tiên khi có gì đó không như mong đợi.

---

## 12. Sao lưu

Toàn bộ dữ liệu nằm trong hai chỗ:

| Đường dẫn | Nội dung |
|-----------|----------|
| `data/app.db` | Danh bạ, chiến dịch, kịch bản, lịch sử cuộc gọi, nhãn, tóm tắt |
| `data/recordings/` | File ghi âm, chia theo ngày |

Chép hai thư mục này là sao lưu đủ. Nâng cấp phiên bản **không cần xoá
`app.db`** — hệ thống tự bổ sung cột mới khi khởi động.
