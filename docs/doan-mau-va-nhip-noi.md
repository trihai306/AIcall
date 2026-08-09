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

## Ép chậm hơn nhịp thật thì F5 TỰ CHÈN QUÃNG DỪNG

Đây là mắt xích quan trọng nhất, tìm ra 2026-08-09 sau khi người dùng kêu *"tự
nhiên một câu nó dừng xong nó mới bật lên và tự nhiên đọc bị chậm"*.

Công thức thời lượng của F5 cấp khung theo `speed`. Đặt `speed` thấp hơn nhịp
thật của người trong đoạn mẫu là bắt F5 **kéo giãn** tiếng cho đầy khung — và nó
lấp chỗ thừa bằng **quãng dừng bịa giữa câu**.

Đo trên câu 34 âm tiết **không có dấu nào ở giữa** (nên mọi quãng lặng > 250ms
đều là bịa), 10 lượt mỗi mức, `scripts/chon_toc_theo_ban_goc.py`:

| speed | nhịp ròng | lệch so với người thật (287) | lượt có dừng bịa |
|---|---|---|---|
| 0.90 | 222 | −65 | **4/10**, dài nhất 580ms |
| 1.10 | 252 | −35 | 1/10 |
| 1.20 | 269 | −18 | **0/10** |
| 1.30 | 295 | +8 | **0/10** |

Đơn điệu: càng ép chậm xa nhịp thật, càng nhiều quãng dừng bịa.

**Một nguyên nhân, hai triệu chứng** — vừa "giọng không giống người thật", vừa
"dừng giữa câu". Chỉnh đúng tốc là chữa cả hai.

#### Nhưng chỉnh tốc CHƯA đủ — mảnh dài vẫn bịa

Sau khi đặt `speed` 1.20, bản ghi hội thoại thật 111 giây vẫn còn **19 quãng lặng
300–1600 ms nằm SÂU TRONG LÒNG một mảnh** (không phải chỗ nối mảnh). Mảnh dài
nhất lúc đó là **11,5 giây tiếng**.

Đã đuổi qua bốn giả thuyết và **sai cả bốn**: `nfe` thấp, checkpoint fine-tune,
dấu `/` và `-` trong `CMND/CCCD`, và độ dài văn bản (F5 thuần sạch 0/8 tới 52 âm
tiết). Cách chữa thật đơn giản hơn nhiều: **đừng đưa cho F5 đoạn dài**.

Đo cùng một đoạn văn, cùng lúc Ollama đang sinh token
(`scripts/thu_manh_5_tu.py`):

| Cách cắt | Mảnh | Tiếng đầu | Tổng sinh | Quãng lặng > 250 ms |
|---|---|---|---|---|
| Dấu câu (cũ) | 6 | 467 ms | 5,14s | 1 (580 ms) |
| 8 từ | 11 | 574 ms | 8,27s | **0** |
| **5 từ** | 18 | 724 ms | 12,82s | **0** |
| 3 từ | 29 | 648 ms | 19,36s | 3, kèm **21 lần sinh không kịp phát** |

Có cả ngưỡng trên lẫn ngưỡng dưới. Mảnh dài thì F5 bịa; mảnh quá ngắn thì sinh
không kịp phát. Đã chốt **5 từ** (người dùng nghe cả bốn bản rồi chọn), giá phải
trả là 2,5 lần thời gian GPU.

Cài ở `backend/pipeline/text_chunker.py`, hàm `tach_manh()`. Xem
`tests/test_cat_manh_5_tu.py`.

### Và cuối cùng: bỏ hẳn cái nó bịa, thay vì tìm cách ngăn

Cắt 5 từ hạ 19 xuống 9 quãng, nhưng không hết. Sau **năm** giả thuyết sai liên
tiếp về nguyên nhân, cách hiệu quả nhất hoá ra là không cần biết nguyên nhân:
soi tiếng sau khi sinh rồi **bóp mọi quãng lặng giữa mảnh dài quá ngưỡng**.

Ngưỡng lấy từ đo thật, không chọn cho đẹp (10 lượt mỗi bản, đúng cấu hình đang
chạy — `scripts/do_nghi_dau_phay.py`, `scripts/do_nghi_dau_cham.py`):

| | Quãng dài nhất |
|---|---|
| Không dấu nào ở giữa | 0 ms |
| 1 dấu phẩy | 160 ms |
| **1 dấu chấm** | **320 ms** |
| 2 dấu chấm | 260 ms |
| **Quãng BỊA** (đo trên bản ghi thật) | **380 – 1600 ms** |

Nên **360 ms** là chỗ tách, bóp về **200 ms**.

**Đã thử 260 ms và SAI**: nghỉ thật ở dấu chấm chạm 320 ms nên ngưỡng đó cắt
nhầm ranh giới câu, hai câu dính vào nhau. Chỉ đo dấu phẩy (tối đa 160 ms) thì
không lộ ra điều này — **phải đo riêng dấu chấm**.

Đo đối chứng an toàn: cho STT nghe lại **cả hai bản** rồi so bản chép —
**0/16 lượt rụng chữ**. Cài ở `cat_lang_bia()` trong `tts_service.py`, đặt sau
`trim_silence` và **trước** khi đổi tần số. Xem `tests/test_cat_lang_bia.py`.

## Đo nhịp thật thì phải đo trên CẢ bản thu, và phải lấy nhịp RÒNG

Hai cái bẫy, đã mắc cả hai:

**Bẫy 1 — đo trên một đoạn 5 giây.** Một lát cắt có thể rơi vào chỗ người ta nói
nhanh hoặc chậm bất thường. Chính vì thế clip cũ đo ra 297 âm tiết/phút trong khi
các clip khác cắt từ **cùng bản thu** lại cho 211–289. Đo trên toàn bộ 20,2 phút
bằng `scripts/do_nhip_ban_goc.py` mới ra con số thật.

**Bẫy 2 — lấy nhầm nhịp thô.** Hai con số khác nhau rất xa:

| | Trung vị | Khoảng |
|---|---|---|
| nhịp **thô** (âm tiết / tổng thời gian) | 220 | 201–255 |
| nhịp **ròng** (âm tiết / thời gian CÓ TIẾNG) | **287** | 259–329 |

Phải so với **nhịp ròng**: F5 chỉ sinh phần có tiếng, còn quãng nghỉ giữa câu đã
được chèn riêng bằng code (`nhip_nghi_sau` trong `streaming_pipeline`). Lấy nhịp
thô thì AI nói chậm hơn người thật rồi lại bị chèn thêm nghỉ — đúng chỗ sai cũ.

### Bẫy khi ĐO quãng dừng: đừng dùng câu có dấu phẩy

Bản đo đầu tiên dùng câu có dấu phẩy rồi đếm quãng lặng > 250ms và gọi đó là
"trôi giọng". **Sai**: F5 nghỉ ở dấu câu là ĐÚNG, đo được 140–310ms mỗi chỗ.
Đếm lại thì số quãng nghỉ bám sát số dấu phẩy (22 âm tiết có 1 phẩy ra 1,2 nghỉ;
32 âm tiết có 2 phẩy ra 2,2 nghỉ) — tức là đang đo dấu câu chứ không đo lỗi.

Câu thử phải **không có dấu nào ở giữa**. Và phải lặp **ít nhất 10 lượt**: F5 lấy
mẫu ngẫu nhiên, 4 lượt cho ra 1/4 và 4/4 ở cùng một cấu hình.

## Cấu hình đang chạy

`giong_heu` = clip `heu_c` (5.40s), `giong_heu.speed` = **1.20**.

| | Clip cũ 2.21s @ 0.64 | `heu_c` @ 0.90 | `heu_c` @ **1.20** |
|---|---|---|---|
| Nhịp ròng | – | 222 | **269** |
| Lệch so với người thật (287) | – | −65 | **−18** |
| Dừng bịa giữa câu (34 âm tiết) | – | 4/10 | **0/10** |
| Âm rác đầu câu | **3/3 lượt** | 0/3 | **0/5** |
| Vượt trần biên độ | **2/3** | 0/3 | **0/5** |

Chọn 1.20 chứ không 1.30 dù 1.30 khớp người thật hơn: 1.30 cho 283 âm tiết/phút
nghe được, hơi nhanh cho telesales. 1.20 vẫn sạch 0/10 mà dễ nghe hơn.

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
