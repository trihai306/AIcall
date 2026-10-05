# Kiểm chứng nối câu đệm — 12/09/2026

## Thay đổi đã triển khai trên Windows

- Câu trả lời cố định được bỏ phần chào lặp trước cả bước cắt chữ, sinh tiếng và tra cache. Không thay số liệu, chủ đề hoặc điều kiện của câu trả lời.
- Bản tiếng độc lập và bản nối sau câu đệm có mã cache riêng, không xoá lẫn nhau khi làm nóng cache.
- Vế đầu có thể gộp qua dấu phẩy trong phần thời gian câu đệm còn phát. Không gộp qua dấu chấm; không thêm thời gian chờ gom đầu lượt khi không có câu đệm.
- Nhịp nghỉ ở chỗ nối trừ phần lặng đã trôi qua. Đây là ước lượng từ lịch gửi audio, không phải phép đo tại tai người nghe.
- Nội dung gắn với gói audio chứa toàn bộ chữ của bản tiếng gộp/cached. Chữ câu đệm được chụp trước khi gửi để tránh bị phiên khác thay đổi.

## Bằng chứng

- Mac: 470 passed, 1 cảnh báo deprecation từ ChromaDB; Windows: 470 passed trong 4,01 giây, không fail/skip/error. Lần Windows đầu chưa chạy test vì thiếu `test_bot_lap_chu_de.py`; đã bổ sung đúng tệp này rồi chạy thành công.
- Bộ kiểm thử gồm 16 trường hợp chạy qua consumer thật với TTS/cache giả có đánh dấu từng waveform, tách biệt với kiểm tra model thật bên dưới.
- Backend Windows/CUDA, Gipformer, LLM, TTS thật: 9/9 phiên hoàn tất; 8 phiên chữ có phát tiếng và 1 phiên audio ghi sẵn qua STT. Đã thử cache miss và hit, lưu lịch sử, không có sự kiện lỗi.
- Chín phiên đều bỏ phần “Dạ” lặp sau câu đệm. Chữ gắn với gói audio, các mảnh phản hồi và lịch sử khớp nhau. Đây là kiểm tra metadata và đầu vào TTS, không phải phiên âm/đánh giá bằng tai đối với audio sinh ra.
- Không có khoảng thiếu gói ở ranh giới câu đệm → nội dung trong mô phỏng hàng đợi FIFO của 9 phiên. Con số này không bao gồm nhịp nghỉ chèn trong waveform và không chứng minh đường điện thoại không có khoảng lặng.
- Web: mở Hội thoại, trạng thái “Đã kết nối”, mã phiên `a9fedfff`; gửi câu thử 275 triệu/24 tháng ở Nhắn tin, thấy phản hồi đúng, không có lỗi JavaScript. Không kiểm thử mọi trang của ứng dụng.

Bản đối chứng: `filler_join_before_1789195783484173700.json`.
Bản sau sửa: `filler_join_after_1789197141648144300.json`.

## Nghe A/B

Hai file dùng cùng câu hỏi về 275 triệu và cùng câu đệm “Dạ em nói rõ cho anh chị phần này luôn nhé,”, lấy từ các gói audio backend thật theo thứ tự FIFO. Đây không phải bản thu tại đầu điện thoại.

- A: `nghe/20260912-141450_a-tra-tr-c-s-a-c-u-m-v-nhu-c-u-vay-275-t.wav`.
- B: `nghe/20260912-141457_b-sau-sb-sau-s-a-b-d-l-p-v-gh-p-v-u-275.wav`.
- Trang nghe do `scripts/gui_nghe.sh` trả về: `http://100.64.195.48:8123` (HTTP nội bộ kiểm tra trả 200).

Chưa có đánh giá nghe chủ quan của người dùng đối với B; không khẳng định giọng đã tự nhiên hơn. Không gọi điện mới trong lần sửa này, không thay model/nfe/cấu hình giọng, không sửa nội dung các cuộc gọi đã lưu.

## Triển khai và khôi phục

Đã dừng/khởi động lại dịch vụ khi máy điện thoại báo idle. Backup Windows: `C:/duan/chat-ai/logs/_run/filler_join_before_20260912_b1/`.

SHA-256 Mac và Windows đã đối chiếu:

- `backend/pipeline/noi_cau_dem.py`: `dd6659c6bc68fa27a8e643c6e1165b6f691c042033f157e16283d845eeed6017`.
- `backend/pipeline/streaming_pipeline.py`: `2ac4c1990a6a94c85790bf479bf1a756fc7b814b3fc2b9db8ad9bbfdfd5b3da7`.
