# Triển khai Gipformer cho cuộc gọi — 12/09/2026

## Kết quả xác nhận cuối

Backend Windows sau lần nạp lại cuối báo `status=ok`, `stt_engine=gipformer`,
STT và LLM sẵn sàng, TTS đã nạp. Giao diện Benchmark hiển thị đúng
`Gipformer-1.5-65M-FP32`, trạng thái đã kết nối.

Phiên kiểm thử âm thanh WebSocket `92a6cad4` đã hoàn tất ba lượt, có bản
nhận dạng, câu trả lời, sự kiện âm thanh và đủ ba lượt khách trong lịch sử.
Câu “em muốn vay bốn trăm triệu thì thủ tục như thế nào” nay được định tuyến
`ho_so_can_thiet`, trả lời về căn cước và xác nhận thu nhập/sao kê theo tài liệu,
không còn lặp câu hạn mức. Kết quả chi tiết:
[gipformer_ws_92a6cad4.json](results/gipformer_ws_92a6cad4.json).
Đây là xác minh âm thanh qua backend, không phải cuộc gọi qua nhà mạng;
không dùng các số TTFA có bộ nhớ đệm này làm độ trễ nghe thực tế trên điện thoại.

Đã thử gửi một lệnh gọi lại số thử theo yêu cầu nhưng công cụ chặn lệnh trước
khi có kết quả thực thi. Kiểm tra ngay sau đó: không có cuộc gọi đang chạy,
số lần gọi vẫn là 86 và phiên gần nhất của số thử vẫn là `d9b57f0b`.
**Chưa thực hiện được cuộc gọi mới bằng Gipformer.** Người dùng có thể bấm
Gọi tại số thử trong Danh bạ gọi để đánh giá bản đã triển khai.

## Cấu hình đã chọn trên Windows

- `STT_ENGINE=gipformer`; model `Gipformer-1.5-65M-FP32`, CPU 4 luồng,
  `modified_beam_search`, tại `C:\duan\chat-ai\models\stt\gipformer1.5-fp32`.
- Dùng đúng bốn file đã benchmark, kiểm SHA-256 từng file. Nguồn model:
  `g-group-ai-lab/gipformer1.5-65M-rnnt`, revision
  `65b6b319ecd0fe5875b5afa701eeae84f6f608fa`.
- Cài `sherpa-onnx==1.13.8` và `sherpa-onnx-core==1.13.8` vào môi trường
  Windows, với `--no-deps`; không nâng các thư viện ML khác.
- PhoWhisper ở cổng 8178 vẫn phục vụ chức năng cần mốc thời gian từng từ.
  Nhận dạng trong cuộc gọi đi thẳng vào Gipformer ở backend, không qua
  các prompt, luật sửa chữ hay điểm logprob của PhoWhisper.

## Kiểm tra tiếng nói

Cổng âm học kiểm tra có lời nói trước khi giải mã. Silero chạy cục bộ,
ngưỡng 0,20, tối thiểu 64 ms; chỉ dùng để quyết định có giải mã hay không.
Khi có tiếng nói, giữ nguyên toàn đoạn, không cắt/ghép theo các đoạn Silero.
Resample một lần trên toàn đoạn, giống phép A/B trước đó. Không trộn hai kênh.

Kiểm tra qua đúng `STTService` mới trên Windows:

- 25 đoạn âm thanh từ ba cuộc gọi cũ: các câu hỏi nghiệp vụ giữ kết quả
  như Gipformer FP32 chưa thêm cổng âm học; 9 đoạn trước đó chỉ cho “ừ” nay
  bị lọc. **Chưa nghe xác minh 9 đoạn này, không khẳng định tất cả là nhiễu.**
- 4/4 mẫu đối chứng không lời nói (hai độ dài im lặng, nhiễu nhỏ, âm đơn 450 Hz)
  trả chuỗi rỗng, thay vì sinh “ừ”.
- 12/12 mẫu tiếng nói tổng hợp cục bộ, gồm “ừ”, “vâng”, “không”, “a lô”,
  “bốn trăm”, “không vay nữa”, ở mức bình thường và giảm biên độ còn 20%,
  vẫn có nhận dạng khớp các câu thử. Đây không phải đánh giá giọng người thật.
- Hai yêu cầu nhận dạng đồng thời giữ kết quả riêng biệt.
- Bộ hồi quy Windows: **104 passed**, không có failed/skipped/error trong
  lần chạy nhóm test được chọn.

Không có bản chép lời người nghe xác minh: chưa tính WER/CER hay phần trăm
nghe đúng. Các độ trễ offline không phải độ trễ nói-xong-đến-tai qua điện thoại.

## Lỗi phát hiện khi thử đủ luồng âm thanh

Lần thử WebSocket đầu (`bb3dd2e6`) đưa ba WAV khách nói qua backend đang chạy,
không nhập chữ thay âm thanh. STT nhận được câu hỏi thủ tục, nhưng nhánh
`nhu_cau_vay` lại trả lời hạn mức do câu còn chứa số tiền 400 triệu.

Đã mở rộng nhận dạng câu hỏi thủ tục/hồ sơ “như thế nào”, “ra sao”, “cần gì”
ở nhánh hồ sơ đứng trước nhánh xác nhận số tiền. Chỉ trả dữ liệu trong mục
hồ sơ của tài liệu; thiếu mục này thì trả lại đường truy xuất, không tự bịa
và không đổi câu hỏi thành hạn mức. Thêm sáu ca hồi quy cho lỗi này.

Các script kiểm tra:

- `scripts/kiem_gipformer_tich_hop.py`: 25 WAV, mẫu không tiếng và đồng thời.
- `scripts/kiem_gipformer_cau_ngan.py`: các mẫu câu ngắn từ TTS cục bộ.
- `scripts/kiem_gipformer_ws.py`: ba WAV qua STT/LLM/TTS của backend đang chạy;
  có kiểm tra lịch sử và nhánh trả lời thủ tục. Phiên test được gắn tên
  `TEST Gipformer audio - khong goi`; không xoá lịch sử thật.

## Bảo toàn và quay lại cấu hình cũ

Chỉ đồng bộ file liên quan. Đã đối chiếu bản Windows của các file đang có
trước khi ghi; không ghi đè các thay đổi không liên quan. Chỉ ba khoá STT
trong `.env` Windows được thay, không chép `.env` từ Mac.

Sao lưu nguyên `.env` trước thay đổi tại:
`C:\duan\chat-ai\logs\_run\env_before_gipformer_1789182712029673200.bak`.
Không đưa bản sao có thể chứa thông tin bí mật này vào báo cáo hay đồng bộ ra ngoài.

Để chỉ quay lại engine cũ mà giữ các cài đặt khác: đổi `STT_ENGINE=phowhisper`
trong `.env` Windows, kiểm tra không có cuộc gọi, rồi stop/start backend.
PhoWhisper và model cũ không bị gỡ.

Đã sao lưu log trước hai lần nạp lại dịch vụ trong cùng thư mục đánh giá.
Các bản ghi gốc và ba phiên gọi thật không bị sửa/xoá; âm thanh không gửi
lên dịch vụ nhận dạng bên ngoài.
