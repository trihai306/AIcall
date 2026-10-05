# Kiểm thử ASR trên cuộc gọi thật — 12/09/2026

## Kết luận

Gipformer 1.5 là ứng viên đáng tích hợp thử: bản nhận dạng các câu hỏi về khoản vay, hạn mức, thủ tục và trả hàng tháng mạch lạc hơn rõ rệt trong những đoạn được so sánh; thời gian giải mã offline thấp hơn PhoWhisper-medium trên máy Windows hiện tại. Chưa có bản chép lời do người nghe xác minh, nên **không công bố WER/CER hay phần trăm nghe đúng**. Không đồng nhất câu đúng ngữ pháp với lời nói đúng nguyên văn.

Một điều kiện bắt buộc trước khi sử dụng thật: cả INT8 và FP32 đều sinh “Ừ” trên bốn mẫu không có lời nói. Không được thay model rồi bỏ lớp phát hiện tiếng nói hoặc coi mọi chữ “ừ” là một lượt khách nói thật.

## Dữ liệu và phương pháp

Ba cuộc gọi gần nhất có bản ghi tới cùng số thử, giờ Việt Nam:

| Phiên | Bắt đầu | Thời lượng phiên | Thời lượng bản ghi | Lượt hỏi–đáp đã lưu | Đoạn kiểm thử |
|---|---|---:|---:|---:|---:|
| bc4d83e7 | 11/09/2026 21:23:34 | 84,1 s | 79,66 s | 4 | 11 |
| fe5a9697 | 11/09/2026 23:43:50 | 59,2 s | 54,92 s | 3 | 5 |
| d9b57f0b | 12/09/2026 09:22:04 | 93,0 s | 87,76 s | 6 | 9 |

Tổng bản ghi 222,34 giây. Trích 25 đoạn, tổng 107,10 giây, từ **kênh trái — âm thanh khách thô**. Không trộn giọng bot, không lọc nhiễu, không gửi bản ghi ra dịch vụ ngoài. Các đoạn này có thể chứa tiếng đáp ngắn, nhiễu hoặc âm báo; không được gọi chúng là 25 lượt hội thoại đã xác minh.

Bộ cắt offline dùng RMS, khung 20 ms, ngưỡng bật tối thiểu 250, tắt tối thiểu 150 theo thang int16, chờ im 660 ms, lấy trước 240 ms và đuôi 360 ms. Đây **không phải mô phỏng chính xác VAD/cắt lời/khử vọng/speculation của production**. Mỗi cấu hình nhận cùng file WAV, có SHA-256 trong manifest. Bộ giải mã được warm-up một lần, rồi đo hai lần mỗi đoạn: 200 lần nhận dạng chính, không tính warm-up và 12 lần thử đầu vào không có lời nói.

Môi trường: Windows, Python 3.11.15, RTX 5070 12 GB; dịch vụ hiện hữu vẫn chạy. PhoWhisper-medium-ct2 gọi HTTP localhost, beam 5, VAD của server tắt. Gipformer chạy CPU, 4 luồng, sherpa-onnx 1.13.8, modified_beam_search. Khâu đổi 8 kHz → 16 kHz của Gipformer chạy trên cả đoạn, không nối các khối resample rời.

Phiên bản Gipformer: `g-group-ai-lab/gipformer1.5-65M-rnnt`, revision `65b6b319ecd0fe5875b5afa701eeae84f6f608fa`. Chỉ tải ONNX và tokens, không chạy mã Python từ kho model. Model và thư viện thử đặt riêng dưới thư mục báo cáo trên Windows; không thay môi trường dịch vụ đang chạy.

## Độ trễ nhận dạng offline

Lấy trung vị hai lần chạy cho từng đoạn, sau đó tính trung bình và các phân vị trên 25 đoạn. P95 từ tập nhỏ này chỉ mô tả bộ mẫu, không đại diện mọi cuộc gọi.

| Cấu hình | Thiết bị giải mã | Trung bình | P50 | P95 | RTF |
|---|---|---:|---:|---:|---:|
| PhoWhisper-medium, prompt hiện tại | GPU | 264,13 ms | 252,49 ms | 398,14 ms | 0,06165 |
| PhoWhisper-medium, không prompt | GPU | 272,08 ms | 269,19 ms | 397,70 ms | 0,06351 |
| Gipformer 1.5 INT8 | CPU, 4 luồng | 43,13 ms | 27,81 ms | 137,94 ms | 0,01007 |
| Gipformer 1.5 FP32 | CPU, 4 luồng | 52,64 ms | 34,39 ms | 170,07 ms | 0,01229 |

INT8 thấp hơn khoảng 6,1 lần, FP32 khoảng 5,0 lần về thời gian trung bình trong phép đo này. So sánh đường giải mã offline thực tế: PhoWhisper có chi phí bọc WAV/HTTP localhost, Gipformer gọi trực tiếp và có resample. Không phải benchmark kernel thuần giữa hai thiết bị giống nhau.

**Không phải thời gian khách nói xong → nghe AI trả lời.** Chưa tính đầy đủ phát hiện hết lời, cache/speculation, LLM, TTS, hàng đợi và điện thoại. Log cuộc gọi hiện có TTFA pipeline trung bình khoảng 1,38–1,42 giây mỗi phiên; đó cũng không phải phép đo trực tiếp tại tai người nghe. STT 0 ms trong log cũ có thể do dùng bản nhận dạng đã tính trước, không có nghĩa nhận dạng miễn phí.

## Đối chiếu nội dung

Đây là các giả thuyết của model trên cùng audio, **không phải lời khách đã được người nghe xác minh**. Gipformer được chuyển chữ thường để dễ đọc, không sửa nội dung.

| Mẫu và vị trí trong bản ghi | PhoWhisper, prompt hiện tại | Gipformer 1.5 INT8 |
|---|---|---|
| d9b57f0b_03, 10,44–13,14 s | anh muốn tư vấn về khoảng cách liên minh | ừ anh muốn tư vấn về khoản vay bên mình |
| d9b57f0b_04, 19,50–23,66 s | nghề ngồi ngay kín chép hạm nước bên mình và bên kia | ừ anh muốn vay tín chấp hạn mức bên mình là bao nhiêu |
| d9b57f0b_05, 31,88–34,06 s | đại vua đã vay bốn trăm | anh muốn vay bốn trăm |
| d9b57f0b_07, 56,80–58,60 s | đường anh mướn ngay cùng trăm triệu | anh muốn vay bốn trăm triệu |
| d9b57f0b_08, 67,16–69,60 s | em vay vốn trăm triệu tỷ thủ tục nhiều lắm | em muốn vay bốn trăm triệu thì thủ tục như thế nào |
| fe5a9697_04, 15,80–29,40 s | anh muốn vay bốn trăm trong mười hai tháng thì đồng loại coi nhiều em | anh muốn vay bốn trăm trong mười hai tháng thì đóng lãi bao nhiêu em |
| bc4d83e7_05, 28,50–34,36 s | hãi nguồn vay tầm bốn trăm triệu cho vòng mười hai tháng | anh muốn vay tầm bốn trăm triệu trong vòng mười hai tháng |
| bc4d83e7_07, 43,18–53,44 s | ừ thế tư vấn cho anh về khoản vay nếu anh vay sáu mươi tháng thì một tràng đông tăng nhiệm | ừ thế tư vấn giúp anh về khoản vay nếu anh vay sáu mươi tháng thì một tháng đóng bao nhiêu |

Bỏ prompt không xử lý hết lỗi: đoạn d9b57f0b_03 vẫn có “khoảng cách liên minh”; đoạn d9b57f0b_04 thành “anh muốn vay tìm chép hạng nước bên mình vào bình dương”.

INT8 và FP32 trùng văn bản 22/25 đoạn; đây là **độ đồng thuận**, không phải độ chính xác. Ba đoạn khác nhau:

| Mẫu | INT8 | FP32 |
|---|---|---|
| d9b57f0b_06 | em muốn vay bốn trăm | anh muốn vay bốn trăm |
| fe5a9697_05 | ừ tình yêu | ừ tình |
| bc4d83e7_08 | đây | ừ |

Mỗi cấu hình lặp lại hai lần cho cùng kết quả văn bản trên cả 25 đoạn. Điều đó chỉ chứng minh tính lặp lại ở lần chạy này, không chứng minh nhận dạng đúng.

Luật lọc PhoWhisper đánh dấu 7/25 giả thuyết có prompt và 8/25 không prompt là cần bỏ. Bảng trên hiển thị giả thuyết trước bước bỏ đó để so model. Bộ đo không tự động chạy lại không-prompt sau khi bị lọc, nên không được gọi các con số này là tỷ lệ mất lượt production.

## Đầu vào biết chắc không có lời nói

Bốn mẫu tự tạo, tách khỏi dữ liệu cuộc gọi: im lặng số 1 giây, im lặng số 4 giây, nhiễu trắng RMS 8 trong 3 giây (seed 20260912), sin 450 Hz RMS 1000 trong 2 giây. Gửi thẳng tới ASR, **bỏ qua VAD production**.

| Model | Kết quả |
|---|---|
| PhoWhisper, prompt hiện tại | Sinh chữ trên 4/4 mẫu. Luật confidence/repetition bỏ 2; hai mẫu còn lại vẫn ra “đó là năm một nghìn chín trăm hai mười tám” và không bị luật này chặn. |
| Gipformer INT8 | Sinh “Ừ” trên 4/4 mẫu. |
| Gipformer FP32 | Sinh “Ừ” trên 4/4 mẫu. |

Đây là bằng chứng ASR không thay thế được kiểm tra có lời nói. Không suy ra cả bốn mẫu sẽ đi qua VAD của cuộc gọi thật. Cũng không được chữa bằng cách xóa mọi chữ “ừ”, vì khách có thể đáp “ừ” thật.

## Các vấn đề hội thoại không tự hết khi đổi STT

Lịch sử phiên bc4d83e7 cho thấy AI nói hạn mức 500 triệu rồi đổi sang 300 triệu; đây là mâu thuẫn nội dung, không phải chỉ lỗi nghe. Phiên fe5a9697 hứa tính khoản trả hàng tháng rồi chuyển sang “Có chuyên viên liên hệ lại”. Phiên d9b57f0b dùng câu dự phòng về thiếu quy định khi model trả rỗng và gắn nhãn không quan tâm thiếu căn cứ. Các bản chép lưu sẵn vẫn là STT, không phải biên bản đã xác minh bằng tai.

Hướng xử lý được dữ liệu ủng hộ: tích hợp Gipformer thử có cờ chuyển lại model cũ, giữ kiểm tra tiếng nói/vọng/âm báo; dùng các đoạn đã lưu để xác minh lời chuẩn, đặc biệt số tiền, kỳ hạn, đại từ và câu ngắn; sau đó đo lại toàn tuyến âm thanh với cùng dữ liệu. Chưa thử Qwen3-ASR hay Nemotron trên bộ ghi này, nên không xếp hạng thực nghiệm hai model đó.

## Kiểm chứng và những gì đã thay đổi

`tests/test_do_asr_call_that.py`: **7 passed**, 0 failed, 0 skipped trên Windows. Kiểm tra tách đúng kênh, không coi transcript chưa xác minh là đáp án, giữ dấu tiếng Việt khi chấm, khoảng cách Levenshtein, và ranh giới đoạn âm thanh. Đây là test kỹ thuật của bộ đo, không phải 7 câu nghe đúng.

Chỉ thêm hai script chẩn đoán, một file test và các dữ liệu/báo cáo dưới `logs/asr_eval_20260912`. Không thay mã backend, cấu hình STT, lịch sử hay bản ghi gốc; không restart dịch vụ, không gọi lại. Sau phép đo, backend/STT/LLM/TTS vẫn khỏe. VRAM đầu/cuối lần lượt khoảng 9.150/9.154 MiB; Gipformer chạy CPU, không thay model đang chiếm GPU.

## Hồ sơ bằng chứng

- [Manifest, mốc cắt và SHA-256](/Users/hainc/duan/freelancer/chat-ai/logs/asr_eval_20260912/manifest.json)
- [PhoWhisper có prompt](/Users/hainc/duan/freelancer/chat-ai/logs/asr_eval_20260912/results/pho_production.json), [không prompt](/Users/hainc/duan/freelancer/chat-ai/logs/asr_eval_20260912/results/pho_none.json)
- [Gipformer INT8](/Users/hainc/duan/freelancer/chat-ai/logs/asr_eval_20260912/results/gip1.5_int8_modified_beam_search.json), [FP32](/Users/hainc/duan/freelancer/chat-ai/logs/asr_eval_20260912/results/gip1.5_fp32_modified_beam_search.json)
- [Đối chứng không có lời nói](/Users/hainc/duan/freelancer/chat-ai/logs/asr_eval_20260912/results/no_speech_controls.json)
- [Tiếng khách — cuộc gọi 09:22](/Users/hainc/duan/freelancer/chat-ai/logs/asr_eval_20260912/customer/d9b57f0b.wav)
- [Đoạn hỏi thủ tục để nghe xác minh](/Users/hainc/duan/freelancer/chat-ai/logs/asr_eval_20260912/samples/d9b57f0b_08.wav)
- [Bộ đo](/Users/hainc/duan/freelancer/chat-ai/scripts/do_asr_call_that.py), [test kỹ thuật](/Users/hainc/duan/freelancer/chat-ai/tests/test_do_asr_call_that.py)

`references.json` để trống và `human_verified=false`. Chỉ điền sau khi thực sự nghe xác minh; không lấy đầu ra Gipformer làm đáp án để tự chấm Gipformer.
