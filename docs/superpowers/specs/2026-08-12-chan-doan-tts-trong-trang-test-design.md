# Chẩn đoán TTS ngay trong trang Test giọng nói

Ngày 2026-08-12.

## Vì sao

Ngày 2026-08-12 người dùng báo năm lỗi giọng đọc: đọc cách quãng dù không có
dấu câu, đoạn sau đọc giãn giữa các từ, lắp từ, đọc sai từ, và nghe như đè lên
nhau. Bốn lỗi đầu truy ra cùng một gốc — `thoi_luong_ep` cấp dư 34% thời lượng,
và F5 không đọc chậm lại tương ứng mà lấy im lặng tiêu chỗ thừa.

Việc truy ra gốc phải làm qua SSH sang máy Windows, viết ba script đo, chạy mấy
chục phút. Người dùng không tự làm lại được. Mà đây là loại lỗi sẽ quay lại mỗi
khi đổi giọng, đổi `speed`, hay đổi cỡ mảnh — vì mỗi giọng có một sàn phát âm
riêng.

Mục tiêu: đưa đúng phép đo đó vào trang **Test giọng nói** để người dùng tự dò
và tự chốt, không cần gọi tới ai.

## Phạm vi

Có:

- Đo và hiện số chẩn đoán cho mỗi lần tổng hợp trên trang Test giọng nói.
- So sánh A/B theo **hai hệ số cấp thời lượng** (cùng một giọng), bên cạnh chế
  độ so sánh hai giọng đang có.
- Cho STT nghe lại và bôi đỏ chữ bị lắp/đọc sai.
- Nút chốt hệ số vào cấu hình.

Không có:

- Không đụng `streaming_pipeline` hay đường cuộc gọi thật.
- Không đo trên bản ghi cuộc gọi đã lưu (việc khác, trang Báo cáo).
- Không tự động chọn hệ số tốt nhất. Tai người quyết định, máy chỉ đưa số.

## Kiến trúc

Bốn phần, mỗi phần một việc:

```
chan_doan_tts.py   đo trên mảng PCM        không import torch, test không cần GPU
tts_service.py     hệ số thành đặt được    truyền theo lời gọi, không đổi biến chung
voices.py          /test-tts trả thêm số   dùng lại _cat_manh_nhu_pipeline sẵn có
index.html+app.js  hiện số, chọn chế độ    thêm vào khối A/B đang có
```

### 1. `backend/services/chan_doan_tts.py` — mới

Hàm thuần, nhận `np.ndarray` hoặc PCM int16, trả số. **Không import torch, kể
cả gián tiếp** — cùng lý do đã ghi ở đầu `filler_store.py`: module này phải chạy
được trên máy không GPU để test.

| hàm | trả về | dùng để |
|---|---|---|
| `quang_lang(x, sr, nguong_ms)` | `[(bat_dau_s, dai_ms)]` | tìm chỗ im lặng nằm giữa |
| `giay_co_tieng(x, sr)` | float | mẫu số của nhịp phát âm |
| `doi_chieu(goc, nghe)` | `(lap, sai, [(loai, tu)])` | so bản STT với chữ gốc |
| `chan_doan(x, sr, chu, cap_giay)` | dict | gói cả bốn số lại |

Ngưỡng "thế nào là lặng" lấy **đúng** định nghĩa của `cat_lang_bia`: RMS theo
khung 20ms, so với đỉnh của chính mảnh (20% là ngưỡng rộng, 7% là đáy phải
chạm). Không đặt ngưỡng tuyệt đối — quãng nghỉ của F5 không im tuyệt đối, nó có
hơi thở rất nhỏ, và bản đầu của `trim_silence` đã mắc đúng bẫy này.

Ngưỡng đếm lỗ là **150ms**, không phải 200ms: `cat_lang_bia` bóp quãng bịa
xuống đúng 200ms, đo ở ngưỡng 200 thì chính cái nó vừa để lại không được đếm.

### 2. Hệ số cấp thời lượng thành thứ đặt được

`thoi_luong_ep(text, dai_ref_giay, speed, he_so=None)` — `None` nghĩa là lấy
mức đang lưu.

`F5TTSService` thêm hai phương thức, viết theo đúng khuôn `he_so_thoai` /
`dat_he_so_thoai` đang có: đọc từ một file nhỏ trên đĩa, chặn trong khoảng, dọn
bộ nhớ đệm giọng khi đặt lại.

```
he_so_cap() -> float          đọc file, thiếu thì trả HE_SO_BU_LANG
dat_he_so_cap(v) -> float     ghi file, chặn [0.75, 1.15], xoá cache
```

Sàn 0.75 là mức thấp nhất đã đo, và chính nó đã bắt đầu sai chữ (cấp dư chỉ còn
7%, hết chỗ dự trữ thì F5 nhồi cho kịp) — nên đó là biên chứ không phải mức nên
dùng. Trần 1.15 vì trên đó là quay lại đúng lỗi đang chữa (1.11 đo ra 12 quãng
bịa / 6080ms).

`synthesize(..., he_so=None)` truyền thẳng xuống `_synthesize_sync`.

**Tuyệt đối không đổi biến toàn cục để đo.** `F5TTSService` dùng chung với
cuộc gọi đang chạy; đổi biến chung là khách đang nghe điện thoại bị đổi nhịp
giữa câu. Đây là cùng một luật đã ghi cho `voice` ở đầu class.

### 3. `/api/voices/test-tts`

Thêm hai trường form:

- `he_so: float | None` — rỗng thì dùng mức đang chạy.
- `nghe_lai: bool = True` — cho PhoWhisper nghe lại.

Trả thêm một khối, phần còn lại của response giữ nguyên:

```json
"chan_doan": {
  "cap_giay": 22.19, "noi_giay": 16.44, "cap_du_pc": 35,
  "lo": [{"tai_s": 3.2, "dai_ms": 480}],
  "so_lo": 8, "tong_lo_ms": 2520,
  "nhip_phat_am": 341, "nhip_tho": 295,
  "he_so": 0.85,
  "nghe_lai": {"text": "...", "lap": 0, "sai": 2,
               "chi_tiet": [["sai", "phẩy"], ["lap", "anh"]]}
}
```

`nghe_lai` gọi PhoWhisper ở `127.0.0.1:8178`. Server không chạy hoặc quá hạn thì
`nghe_lai: null` kèm `loi`, phần đo quãng lặng vẫn trả bình thường — một nửa
hỏng không được kéo cả trang chết.

### 4. Endpoint chốt hệ số

```
GET  /api/voices/he-so-cap   -> {he_so, tran, giai_thich}
POST /api/voices/he-so-cap   -> {ok, he_so, da_don_kho_dem}
```

POST phải dọn kho câu đệm dựng sẵn — xem phần Bẫy bên dưới.

### 5. Vân tay kho câu đệm phải có hệ số

`van_tay(text, giong, nfe, speed, ref_text)` hiện **không** có hệ số cấp thời
lượng. Trước hôm nay không sao vì hệ số là hằng số trong code, đổi nó là phải
sửa file và người sửa còn nhớ tăng `PHIEN_BAN`.

Cho phép đổi từ UI thì cái nhớ đó biến mất. Không sửa chỗ này thì mỗi lần bấm
"Dùng mức này", câu đệm cũ trên đĩa vẫn đọc nhịp cũ và nối thẳng vào câu trả
lời nhịp mới — khách nghe hai nhịp khác nhau ngay đầu mỗi lượt, log vẫn sạch,
không có gì báo lỗi. Đúng cái bẫy im lặng mà docstring của `van_tay` đã mô tả.

Nên: thêm `he_so` vào tham số của `van_tay`, và `dat_he_so_cap` dọn kho.

### 6. Giao diện

Trong khối "So sánh A / B" đang có, thêm nút gạt chế độ:

- **Hai giọng** — như hiện tại, hai `<select>` giọng.
- **Hai hệ số** — một `<select>` giọng dùng chung, hai ô số cho hệ số A và B,
  mặc định điền mức đang chạy và mức đang chạy trừ 0.15.

Dưới mỗi ô A/B, sau `<audio>`, thêm khối chẩn đoán:

```
cấp dư 16%   ·   8 lỗ / 2520ms   ·   nhịp 341   ·   nghe được 295
máy nghe lại: "...bảy phảy chín phần trăm..."      2 chữ sai
```

(số trong ví dụ là mức 0.85 đo được ngày 2026-08-12; mức 1.11 cũ cho
cấp dư 35%, 11 lỗ / 2900ms, nhịp 297)

Chữ sai bôi đỏ, chữ lắp bôi vàng, ngay trong câu.

Ở chế độ hai hệ số, mỗi ô có nút **"Dùng mức này"** → POST, rồi hiện lại số hệ
số đang chạy.

**Một dòng cảnh báo cố định dưới khối chẩn đoán**, không phải tooltip:

> Số "lỗ" gồm cả quãng nghỉ đúng ở dấu phẩy lẫn quãng F5 tự bịa — máy không tách
> được hai loại. Dùng để so A với B, đừng đọc như điểm tốt/xấu.

Đây không phải câu rào đón. Đo trên đoạn 4 câu: 8 lỗ thì khoảng 6 là ở dấu
phẩy. Thiếu dòng này thì người đọc sẽ đi tối ưu cho con số về 0, mà về 0 nghĩa
là giọng đọc không nghỉ ở dấu phẩy nào cả — tệ hơn hẳn.

## Xử lý lỗi

| tình huống | xử lý |
|---|---|
| PhoWhisper không chạy | `nghe_lai: null` + `loi`, phần đo còn lại vẫn trả |
| tiếng ra toàn im lặng | đã có lưới sẵn trong `test_tts`, giữ nguyên, bỏ qua chẩn đoán |
| mảnh quá ngắn, `thoi_luong_ep` trả None | `cap_giay: null`, `cap_du_pc: null`, các số khác vẫn tính |
| hệ số ngoài khoảng | chặn về biên, trả về giá trị đã chặn để UI hiện đúng |

## Test

`tests/test_chan_doan_tts.py` — chạy được không cần GPU, bơm PCM dựng sẵn:

- quãng lặng 500ms chèn giữa hai đoạn tiếng → tìm đúng vị trí và độ dài
- quãng lặng ở hai ĐẦU không được tính là lỗ
- tiếng nhỏ đều (không chạm đáy 7%) không bị đếm nhầm là lặng
- `doi_chieu` phân biệt lắp từ ("anh anh chị") với sai từ ("phảy" vs "phẩy")
- mảng rỗng, mảng toàn im lặng, mảng ngắn hơn một khung

`tests/test_thoi_luong_ep.py` — thêm:

- `he_so` truyền vào ghi đè mức đang lưu
- hệ số ngoài khoảng bị chặn về biên
- `van_tay` đổi khi hệ số đổi, giữ nguyên khi hệ số giữ nguyên

## Thứ tự làm

1. `chan_doan_tts.py` + test — chạy được ngay trên Mac, không cần Windows.
2. `thoi_luong_ep` nhận `he_so`, `he_so_cap`/`dat_he_so_cap`, vân tay — + test.
3. `/test-tts` trả `chan_doan`, endpoint hệ số.
4. Giao diện.
5. Đẩy sang Windows, khởi động lại, tự bấm thử qua trình duyệt.

## Ghi chú về hai bản code

Máy Windows `C:/duan/chat-ai` **không phải** git repo và đã lệch xa bản trong
git: bên đó có `BO_DAU_CAU`, `CAT_THEO_CAU`, hệ câu đệm `CauDuoi`/`Kho` mà
repo không có. Mọi thay đổi phải viết theo bản Windows và đẩy từng file, không
được đồng bộ cả thư mục — ngày 2026-08-12 đã lỡ ghi đè
`tests/test_thoi_luong_ep.py` bên đó đúng theo kiểu này.
