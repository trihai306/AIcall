# Chọn đoạn mẫu và tốc độ cho giọng AI

Tài liệu này thay `thu-lai-giong-mau.md`. Bản cũ mới chỉ nắm được một nửa vấn đề
(đoạn mẫu ngắn sinh âm rác); phần còn lại — vì sao giọng AI **nghe không giống
người thật** — tìm ra ngày 2026-08-09.

## Hai lỗi khác nhau, hay bị lẫn làm một

| Triệu chứng | Nguyên nhân | Chữa bằng |
|---|---|---|
| Bịa chữ ở đầu câu (*"hiếu… nhìn… cá nhân…"*) | Đoạn mẫu **ngắn dưới 3s** | Dùng clip 4–6s |
| Đúng chất giọng nhưng **nghe ra người khác** | `speed` bóp nhịp quá xa nhịp thật | Chọn clip có nhịp gốc gần nhịp cần, để `speed` sát 1.0 |

## F5 KHÔNG hề clone kém — đây là số đo

Đo bằng cosine giữa vector MFCC trung bình (`scripts/doi_chung_giong.py`):

```
                giong_heu  giong_nam     fosd_1   nam_moi1
  giong_heu        0.992      0.704      0.733      0.733
  giong_nam        0.698      0.995      0.885      0.995
  fosd_1           0.731      0.891      0.993      0.886
```

Đường chéo (F5 sinh từ chính đoạn mẫu đó) là **0.992–0.995**; so với người khác
chỉ **0.70–0.73**. F5 chép đúng âm sắc, không bàn cãi.

> Cặp `giong_nam`↔`nam_moi1` lẫn nhau vì hai **đoạn mẫu** vốn đã giống nhau
> 0.992 — cùng một người, không phải lỗi F5.

**Đừng dùng trọng tâm phổ (spectral centroid) để kết luận "giống hay không".**
Nó nén cả âm sắc vào một con số nên mù; đo bằng nó từng dẫn tới kết luận sai là
"F5 không tái tạo được đoạn mẫu". Luôn có **đối chứng người khác** trước khi tin
một thước đo độ giống.

## Thủ phạm thật: nhịp nói

Tai người nhận ra một người qua **nhịp** nhiều hơn qua âm sắc. MFCC lấy trung
bình theo thời gian nên mù hoàn toàn với nhịp — nó "đạt" trong khi tai nghe
"sai người".

Đo nhịp gốc các clip (`scripts/do_nhip_doan_mau.py`, âm tiết/phút sau khi cắt lặng):

```
  giong_heu (clip cũ 2.21s)  297   <- nhanh nhất trong 15 giọng
  heu_a 281   heu_b 289   heu_c 211   heu_d 261   heu_e 251
  fosd_1 195  giong_nam 177  nam_moi1 186  nam_moi2 143
```

Clip cũ nói 297; ép `speed=0.64` để về 180 cho hợp telesales tức bắt F5 chạy ở
**61% nhịp thật**. Cùng chất giọng, sai nhịp 39% → nghe ra người khác.

## Cấu hình đang chạy

`giong_heu` = clip `heu_c` (5.40s, nhịp gốc 211), `giong_heu.speed` = **0.90**.

| | Clip cũ 2.21s @ 0.64 | Clip `heu_c` @ 0.90 |
|---|---|---|
| Nhịp ra | 180 âm tiết/phút | **206** |
| % nhịp thật của người đó | 61% | **98%** |
| Âm rác (STT nghe lại) | **3/3 lượt** | **0/3** |
| Vượt trần biên độ | **2/3** | **0/3** |

Bản cũ giữ ở `models/tts/ref_voices/giong_heu.wav.bak-20260809` (và `.txt.bak-…`).
Hoàn lại thì chép đè ngược rồi xoá `giong_heu.speed`.

## Bẫy: `speed` KHÔNG tỉ lệ thẳng với nhịp ra

Công thức thời lượng của F5 chia theo `len(ref_text.encode())` — số **BYTE**, mà
tiếng Việt có dấu là 2–3 byte/chữ. Hai clip cùng số âm tiết nhưng khác số dấu sẽ
ra hai nhịp khác nhau ở cùng `speed`. Ví dụ đo thật:

```
  heu_a  nhịp gốc 281,  speed 0.68  ->  247  (đoán tuyến tính: 191)
  heu_d  nhịp gốc 261,  speed 0.73  ->  261  (đoán tuyến tính: 190)
```

Lệch tới 37%. **Đừng suy ra, hãy đo** bằng `scripts/do_nhip_doan_mau.py`.

## Quy trình khi thêm hoặc đổi giọng

1. Cắt clip **4–6 giây**, một câu tiếng Việt bình thường, không số, phòng yên.
   Cách người đó đọc trong clip sẽ quyết định cách AI đọc mọi câu.
2. Đặt `<tên>.wav` + `<tên>.txt` (chép **chính xác** câu đã đọc, đủ dấu) vào
   `models/tts/ref_voices/`.
3. Đo nhịp gốc: `.venv\python.exe scripts\do_nhip_doan_mau.py`
4. Chọn `speed` sao cho nhịp ra vừa tai **và** `speed` càng gần 1.0 càng tốt.
   Ghi vào `<tên>.speed`. Nếu phải hạ dưới ~0.8 thì clip đó nói quá nhanh so với
   nhu cầu — tìm đoạn khác trong bản thu chứ đừng bóp tiếp.
5. Kiểm sạch: `.venv\python.exe scripts\do_am_rac.py --giong <tên>`
   Đạt khi **0/5 âm rác** và **0/5 vượt trần**.
6. Khởi động lại — nhớ cờ `-Restart`, vì `start_services.ps1` chỉ so **code**,
   không so file giọng, nên không có cờ này nó sẽ bỏ qua:

```
powershell -ExecutionPolicy Bypass -File C:\duan\chat-ai\scripts\start_services.ps1 -Detached -Restart
```

Tiếng câu đệm dựng sẵn mang vân tay gồm cả câu mẫu và tốc, nên thay xong hệ
thống **tự dựng lại toàn bộ 42 câu**. Không phải xoá tay.

## Còn muốn giống hơn nữa?

Đổi clip mẫu và tốc là hết mức của zero-shot. Muốn giọng ra thật sự là một người
cụ thể thì phải **fine-tune trên chính giọng đó** (như `finetuned/giong_nam` đang
có). Đó là việc lớn: cần dữ liệu sạch và một buổi train.

Đã kiểm và **loại**: chuyện checkpoint không phải nguyên nhân. Cùng đoạn mẫu,
cùng câu, bản fine-tune `giong_nam` và bản gốc ViVoice cho kết quả gần như trùng
nhau — không có chuyện fine-tune kéo mọi giọng về giọng nam.
