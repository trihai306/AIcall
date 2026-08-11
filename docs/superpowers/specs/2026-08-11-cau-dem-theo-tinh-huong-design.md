# Câu đệm theo tình huống

Ngày 2026-08-11. Trạng thái: đã chốt hướng, chưa viết mã.

## Vấn đề

Người dùng nghe cuộc gọi thật và nêu ba lỗi:

1. **Câu đệm nói trớt vấn đề khách vừa nói.** Khách hỏi lãi suất mà máy đệm "dạ em nắm được rồi" — nghe như gạt đi.
2. **Nghe lặp, máy móc.** 42 câu nhưng cách nói không đổi theo tình huống.
3. **Đệm xong thì câu thật không nối mượt.** Hai đoạn rời nhau chứ không phải một lượt nói liền mạch.

Lỗi 1 có nguyên nhân rõ trong mã: việc chọn câu đệm **không đọc phiên âm của khách** lấy một lần. Nó chỉ lọc theo cờ `hop_cau_hoi`, mà cờ đó cũng chỉ *suy* từ `session.turn_count > 0`. Chú thích tại `_send_filler` ghi thẳng: *"(Mốc 2 sẽ đọc session.spec_stt để biết chắc thay vì đoán.)"* — đây chính là mốc 2 đó.

Lỗi 3 có hai nguyên nhân riêng biệt:
- `PHIEN_BAN` không được tăng khi `bo_dau_cau_cho_f5` bị vô hiệu hoá ngày 2026-08-11, nên 42 tệp tiếng cũ đọc theo cách xoá dấu còn câu trả lời thật đọc theo cách giữ dấu. **Đã sửa** (`PHIEN_BAN = 4`), không thuộc phạm vi spec này.
- Nguyên nhân cấu trúc: câu đệm là một phát ngôn F5 riêng nên nó tự hạ giọng kết câu, rồi câu trả lời lại mở đầu như phát ngôn mới. Cùng gốc với lỗi chỗ nối mảnh. **Spec này chữa nguyên nhân thứ hai.**

## Hiện trạng

| Khâu | Cơ chế hiện tại |
|---|---|
| Kho | `data/fillers.json` — 42 câu, **1 chủ đề `chung`, không từ khoá** |
| Khi phát | `_send_filler` là `await` đầu tiên của lượt, trước cả STT |
| Chọn độ dài | `can_che_ms`: max TTFA 6 lượt gần nhất × 1,25, sàn 1800ms (thoại) / 2000ms (chat) |
| Chọn câu | vừa khít → đủ dài → dài nhất; trong mỗi tầng bốc câu **ít dùng nhất** |
| Bỏ đệm | khi dự đoán trễ < 700ms |
| Tiếng | dựng sẵn lúc khởi động, cache trong RAM, vân tay `(PHIEN_BAN, text, giọng, nfe, speed, ref_text)` |

Mô hình dữ liệu **đã có sẵn** `ChuDe` với trường `tu_khoa` nhưng chưa dùng.

Điểm nối sẵn có: `speculate()` chạy khi khách **còn đang nói** — cứ ~100ms tiếng mới là phiên âm tạm một lần, cất vào `session.spec_stt` ngay sau STT trước mọi bước khác. `speculate(ngay=True)` chạy lại trên toàn câu ngay khi khách vừa ngừng tiếng.

## Trục chọn hiện nay là ĐỘ DÀI — đây là ràng buộc chi phối cả thiết kế

`chon()` chọn câu vừa khít quãng trễ dự đoán, dải 700–2500ms. 42 câu nằm trong **một** rổ nên luôn có câu vừa cỡ.

Chia 42 câu thành 20 rổ theo tình huống thì mỗi rổ còn ~2 câu, không phủ nổi dải độ dài, và `chon()` rơi xuống tầng chót "lấy câu dài nhất" — tức quay lại đúng chuyện khách nghe hụt im lặng, thứ câu đệm sinh ra để chặn.

**Kết luận: thêm trục tình huống là NHÂN số câu phải soạn, không phải chia.** Thiết kế dưới đây tránh phép nhân đó bằng cách ghép hai mẩu.

## Phạm vi

**Trong phạm vi**
- Kho tình huống có thể soạn bằng tay, ~20 tình huống
- Phân loại tình huống bằng embedding trên phiên âm dở, chạy trong `speculate`
- Ghép mẩu mở đầu riêng theo tình huống với đuôi dùng chung, sinh thành **một** phát ngôn F5
- Tham số `speed` riêng theo tình huống, áp cho **cả câu đệm và câu trả lời** của lượt đó

**Ngoài phạm vi**
- Đổi prompt / kịch bản LLM theo tình huống (máy trạng thái hội thoại — dự án riêng)
- Gọi LLM sinh chữ để phân loại (lý do ở mục Quyết định)
- Giao diện quản lý kho; v1 soạn trực tiếp file JSON

## Mô hình dữ liệu

`data/fillers.json`:

```json
{
  "tinh_huong": [
    {
      "id": "hoi_lai_suat",
      "ten": "Khách hỏi lãi suất",
      "vi_du": ["lãi suất bao nhiêu", "vay thì lãi thế nào", "một tháng trả bao nhiêu"],
      "tu_khoa": ["lãi suất", "lãi", "phần trăm"],
      "mo_dau": ["Dạ về lãi suất thì,", "Dạ lãi suất bên em thì,"],
      "doc": { "speed": 1.12 }
    }
  ],
  "duoi": [
    { "id": "d_ngan", "text": "anh chị chờ em một chút ạ.", "hop_cau_hoi": true }
  ]
}
```

- `vi_du` — bắt buộc, tối thiểu 2 câu. Dùng để nhúng và so cosine.
- `tu_khoa` — không bắt buộc. Lọc thô và dự phòng khi model nhúng chết.
- `mo_dau` — **rỗng thì rơi về đuôi trần, tức đúng hành vi hôm nay.**
- `doc.speed` — không có thì lấy tốc của giọng.
- `duoi[]` — rổ dùng chung, phải phủ liền mạch dải 700–2500ms. 42 câu hiện có chuyển hết vào đây.
- `hop_cau_hoi` trên `duoi[]` — **giữ nguyên và vẫn có việc.** Nó lọc những đuôi kiểu "em nắm được rồi" vốn không hợp khi khách vừa hỏi. Lọc này độc lập với tình huống: tình huống nói khách đang hỏi VỀ CÁI GÌ, còn cờ này nói câu đuôi có hợp với dạng câu hỏi hay không. Khác biệt so với hôm nay: điều kiện bật lọc thôi *suy* từ `session.turn_count > 0` mà đọc chính phiên âm dở — có dấu hỏi hoặc từ hỏi thì bật.

Hành vi hiện tại trở thành **trường hợp suy biến** của thiết kế mới. Đây là điểm giữ rủi ro thấp: mọi đường xuống cấp đều dẫn về nó.

Xác thực khi nạp (ném `LoiKho` nêu rõ mục sai, theo đúng lối `nap()` đang có):
- `id` trùng
- `vi_du` rỗng hoặc dưới 2 câu
- `text` rỗng
- `mo_dau` không kết thúc bằng dấu phẩy (xem mục Ghép chuỗi)

## Luồng lúc chạy

**Lúc khởi động**
1. Nạp kho, xác thực.
2. Nhúng toàn bộ `vi_du` bằng model embedding **mà RAG đã nạp** — không nạp thêm model nào.
3. Dựng tiếng cho toàn bộ `duoi[]` (đuôi trần) — đây là bộ bảo đảm luôn có cái để phát.
4. Dựng tiếng các tổ hợp `mo_dau × duoi` **ở nền**, không chặn khởi động.

**Khi khách đang nói** — trong `speculate()._run()`, ngay sau khi `session.spec_stt` được cất:
5. Nhúng phiên âm dở, so cosine với vector `vi_du`, lấy argmax nếu điểm ≥ ngưỡng.
6. Ghi `session.tinh_huong = (số_byte_đã_thấy, id_tình_huống, điểm)`.

Không `await` ở đường găng nào. Theo đúng triết lý của `speculate`: *"Đoán trượt thì bỏ, chạy lại như thường."*

**Khi vào lượt** — `_send_filler`:
7. Đọc `session.tinh_huong`. Nếu độ phủ audio < ngưỡng thì coi như không có.
8. Lấy tập ứng viên = **các tổ hợp đã có tiếng trong cache** của tình huống đó, mỗi ứng viên mang độ dài TỔNG đo được của chính clip đã ghép.
9. Chạy `chon()` như hiện nay trên tập đó — luật vừa khít / đủ dài / dài nhất và luật bốc câu ít dùng nhất giữ nguyên.
10. Tập rỗng (chưa dựng xong tổ hợp nào cho tình huống này) → **dùng rổ đuôi trần và hẹn dựng ở nền.**

Chọn theo **độ dài tổng của clip đã ghép**, không phải "độ dài đuôi trừ độ dài mẩu mở đầu". Độ dài tiếng của mẩu mở đầu không biết được từ chuỗi chữ, mà clip ghép thì đã đo sẵn khi dựng — đúng cách `_filler_ms` đang làm cho 42 câu hiện tại. Đây cũng là lý do khoá cache phải là `(giọng, id_tình_huống, id_đuôi)` chứ không phải `(giọng, id_câu)`.

## Luật cứng về tiếng câu đệm

> Tiếng câu đệm chỉ được lấy từ cache. Không bao giờ sinh trên đường găng.

Chờ sinh tiếng là phá đúng mục đích của câu đệm. Mọi trường hợp thiếu đều xuống cấp về đuôi trần, thứ luôn có sẵn từ bước 3.

## Ghép chuỗi

Ghép thành **một chuỗi** rồi đưa cho F5 một lần, không nối hai đoạn tiếng. Nối tiếng là tái tạo đúng lỗi chỗ nối mảnh: F5 sinh mỗi phát ngôn với ngữ điệu kết câu riêng.

`mo_dau` phải kết thúc bằng **dấu phẩy** để F5 nghỉ ngắn tại đó thay vì hạ giọng kết câu — dấu câu nay đi tới được F5 vì `BO_DAU_CAU = False`. Ràng buộc này được xác thực khi nạp kho.

Số tổ hợp: 20 tình huống × ~6 đuôi = 120, cộng 6 đuôi trần, cho mỗi giọng. Khoảng 96 giây GPU một lần cho mỗi giọng.

`van_tay` đã gồm `text` và `speed`, nên tổ hợp mới tự có vân tay mới. **Không cần tăng `PHIEN_BAN`.**

## Tham số đọc theo tình huống

`doc.speed` áp cho cả câu đệm và câu trả lời của lượt đó. `synthesize()` đã nhận `speed=` và `speed` đã nằm trong khoá cache câu, nên chỉ cần truyền xuống.

Giá phải trả, ghi lại cho rõ: **cache câu bị chia theo tình huống** nên tỉ lệ trúng cache giảm. Cần đo lại tỉ lệ trúng sau khi triển khai.

## Tách module

Giữ nguyên nguyên tắc dự án đang có: logic chọn câu đệm **không import torch** để test được không cần GPU.

| Tệp | Việc | Cần GPU |
|---|---|---|
| `filler_store.py` | schema mới, xác thực, vân tay | không |
| `filler_pick.py` | chọn theo độ dài, ưu tiên tình huống, ghép chuỗi | không |
| `filler_situation.py` *(mới)* | cosine argmax + ngưỡng, thuần numpy | không |
| `tts_service.pick_filler` | tra cache, quy giọng lạ | có |
| `speculate` / `_send_filler` | nhúng, ghi phiên, đọc phiên | có |

## Xuống cấp có kiểm soát

| Hỏng ở đâu | Xuống cấp thành |
|---|---|
| Model nhúng không dùng được | từ khoá; không khớp thì rổ chung |
| Không tình huống nào vượt ngưỡng | rổ chung |
| Phân loại quá cũ (độ phủ thấp) | rổ chung |
| Tổ hợp thiếu tiếng trong cache | đuôi trần + hẹn dựng nền |
| `fillers.json` sai | `LoiKho` lúc khởi động, nêu rõ mục sai |

Không đường nào dẫn tới khách nghe im lặng.

## Kiểm thử

**Phải làm trước, không phải cùng lúc:** sửa 5 test đỏ trong `tests/test_filler_pick.py`. Chúng kỳ vọng hành vi trước khi `can_che_ms` có biên 1,25 và trước khi `mac_dinh` thành sàn; tên `test_lay_max_cua_ba_luot_gan_nhat` còn nói "3 lượt" trong khi mã lấy `[-6:]`. Mã là cố ý và có số đo biện minh trong docstring — **test cũ, không phải mã sai**. Xây tính năng lên một bộ test đang nói dối thì hồi quy sau này không ai bắt được.

Test mới, tất cả chạy được không cần GPU:

- `test_filler_situation.py` — argmax; dưới ngưỡng trả `None`; hoà điểm; danh sách rỗng; vector lệch chiều.
- `test_filler_store.py` — từng nhánh xác thực: `id` trùng, `vi_du` dưới 2 câu, `text` rỗng, `mo_dau` không kết bằng phẩy.
- `test_filler_pick.py` (thêm) — ưu tiên câu thuộc tình huống; rơi về rổ chung khi rổ tình huống không có câu vừa độ dài; độ dài mục tiêu trừ đúng độ dài mẩu mở đầu; chuỗi ghép đúng khoảng trắng và dấu.

Đo trên máy Win sau khi triển khai:
- tỉ lệ phân loại đúng, đối chiếu bằng tai trên bản ghi thật
- độ phủ audio lúc `_send_filler` đọc phân loại — để **chốt ngưỡng bằng số thay vì đoán**
- tỉ lệ trúng cache câu trả lời, trước và sau khi chia theo tình huống
- TTFA trước/sau, để chắc phân loại không lọt vào đường găng

## Quyết định và lý do

**Không dùng LLM sinh chữ để phân loại.** Ba lý do, cả ba từ ghi chép đo được của chính dự án:
- Prompt tư vấn giết chết việc gọi hàm; phải tách lượt định tuyến riêng.
- `OLLAMA_NUM_PARALLEL=2` từng làm đuôi trễ **gấp ba**, mà phân loại lúc khách đang nói là chạy song song với việc hâm LLM.
- Phân loại **không bao giờ được chờ**; `_send_filler` là `await` đầu tiên của lượt.

Embedding tốn ~10ms, dùng model RAG đã nạp, và phân loại được cả câu diễn đạt khác từ khoá.

**Không chia 42 câu thành 20 rổ.** Lý do ở mục "Trục chọn hiện nay là ĐỘ DÀI".

## Chưa có số, phải đo rồi chốt

- **Ngưỡng độ phủ audio** để coi phân loại là còn dùng được. Tạm 50%, ghi độ phủ vào metrics rồi chỉnh theo số thật. Chưa đo.
- **Ngưỡng điểm cosine** để nhận một tình huống. Tạm 0,55; chốt sau khi có bộ câu khách thật để đối chiếu. Chưa đo.
- **Số đuôi cần thiết** để phủ liền mạch dải 700–2500ms. Tạm 6, kiểm bằng cách đo độ dài tiếng thật của từng đuôi sau khi dựng.

## Rủi ro

- **Phân loại giữa câu bị lệch khi khách đổi ý giữa lượt** ("lãi suất bao nhiêu… à không, hồ sơ cần gì"). Giảm nhẹ bằng ngưỡng độ phủ; không loại bỏ được hoàn toàn. Chọn sai mẩu mở đầu tệ hơn không có mẩu nào, nên khi lưỡng lự phải nghiêng về rổ chung.
- **Chia cache câu trả lời theo tình huống làm giảm tỉ lệ trúng**, tức tăng thời gian sinh. Phải đo.
- **20 tình huống soạn tay sẽ chồng chéo `vi_du`**, làm điểm cosine sát nhau. Cần đo ma trận lẫn lộn giữa các tình huống trước khi tăng thêm.
