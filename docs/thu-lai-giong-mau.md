# Thu lại đoạn mẫu cho giọng `giong_heu`

## Vì sao phải thu lại

Đoạn mẫu hiện tại chỉ **2,21 giây** (sau khi cắt lặng), là file nhỏ nhất trong 10
giọng. Đo thật ngày 2026-08-08, cùng một câu, lặp 3 lần mỗi giọng, cho STT nghe
lại rồi so với chữ gốc:

| Giọng | Đoạn mẫu | Có âm rác | Vượt trần biên độ |
|---|---|---|---|
| **`giong_heu`** (đang dùng) | **2,21s** | **2/3 lượt** | **3/3** |
| `fosd_1` | 4,95s | 0/3 | 0/3 |

Đoạn mẫu ngắn thì F5 thiếu ngữ cảnh, nó **bịa ra một cụm 2–5 âm tiết ở đầu mỗi
lần sinh tiếng**. Khách nghe thành *"hiếu… nhìn… kể nhân…"* trước mỗi câu. Cụm
này rất TO (biên độ ~0,5) nên `trim_silence` không cắt được — hàm đó chỉ cắt
khoảng lặng.

## Cần thu gì

**Một đoạn 4–6 giây, cùng người đã thu `giong_heu.wav`.**

| Yêu cầu | Chi tiết |
|---|---|
| Độ dài | **4–6 giây** tiếng nói liên tục (đừng dưới 3s, đừng trên 8s) |
| Nội dung | Một câu tiếng Việt bình thường, đủ dài, **không có số** |
| Chất lượng | Phòng yên, không vang, không nhạc nền, không tiếng gõ bàn phím |
| Cách đọc | Giọng bình thường như đang tư vấn — **cách đọc này sẽ quyết định cách AI đọc mọi câu** |
| Định dạng | WAV, mono, 24000 Hz (tần số khác cũng được, hệ thống tự đổi) |

Câu gợi ý (đủ dài, đủ đa dạng âm, không số):

> *"Dạ em chào anh chị, em gọi từ ngân hàng để tư vấn về khoản vay tín chấp,
> mong anh chị dành cho em ít phút ạ."*

Đọc câu này ở nhịp bình thường sẽ ra khoảng 5–6 giây — đúng khoảng cần.

## Thay file

Đặt hai file **cùng tên** vào `models/tts/ref_voices/`:

- `giong_heu.wav` — bản thu mới
- `giong_heu.txt` — chép **CHÍNH XÁC** câu đã đọc, có dấu đầy đủ

Chép sai chữ là hỏng: F5 ước thời lượng bằng tỉ lệ *giây trên byte chữ* của đoạn
mẫu. Text không khớp tiếng thì tỉ lệ sai và tiếng sinh ra méo.

Rồi khởi động lại dịch vụ:

```
powershell -ExecutionPolicy Bypass -File C:\duan\chat-ai\scripts\start_services.ps1 -Detached
```

## Kiểm lại sau khi thay

Log khởi động **không được** còn dòng:

```
Ref audio giọng 'giong_heu' CHỈ 2.2s - NGẮN QUÁ
```

Rồi cho STT nghe lại chính tiếng AI vừa nói — đây là phép thử rẻ nhất và bắt được
thứ mà đo phổ với đo biên độ không bắt được:

```
.venv\python.exe scripts\do_am_rac.py
```

Đạt khi: **0/5 lượt có âm rác** và **0/5 vượt trần biên độ**.

## Lưu ý

Tiếng câu đệm dựng sẵn trên đĩa mang vân tay gồm cả câu mẫu, nên thay file xong
hệ thống **tự dựng lại toàn bộ 42 câu** cho giọng này ở lần khởi động kế tiếp.
Không phải xoá tay gì cả.
