---
name: gui-file-nghe
description: Gửi file audio của dự án cho người dùng nghe và so sánh trên điện thoại. Dùng khi họ yêu cầu nghe thử, gửi bản ghi/TTS, so sánh A/B, hoặc cần đánh giá chủ quan chất lượng giọng; không dùng số đo âm thanh để thay kết luận nghe thực tế.
---

# Gửi audio để người dùng nghe

Đưa file qua trang nghe của dự án, gắn nhãn đủ rõ để người dùng biết chính xác họ đang nghe bản nào. Các chỉ số như RMS, SNR, spectral centroid hoặc CER chỉ giúp khoanh vùng; không được dùng chúng để khẳng định chủ quan rằng một giọng “hay”, “mượt”, “rõ” hoặc “tự nhiên” hơn.

## Gửi file

Chạy từ gốc repository:

```bash
scripts/gui_nghe.sh 'C:/duan/chat-ai/tmp_la.wav' 'A: giọng heu, nfe 12, tốc 0.90'
scripts/gui_nghe.sh ./ket_qua.wav 'B: sau khi gộp mảnh'
```

Script tự kéo file từ Windows nếu đường dẫn bắt đầu bằng ký tự ổ đĩa; file trên Mac được sao chép trực tiếp. Dùng URL mà script in ra, không mặc định IP ghi nhớ sẵn. Nếu cần gửi ngay trong Codex desktop và file ở máy hiện tại, có thể kèm liên kết phát audio bằng đường dẫn tuyệt đối, nhưng trang nghe vẫn là lựa chọn chính cho điện thoại.

## Nhãn và đối chứng

- Nhãn là bắt buộc và phải nêu biến đang so sánh: giọng, `nfe`, tốc độ, bước xử lý hoặc bản gốc/bản sửa.
- Khi đánh giá thay đổi, gửi bản A và B trong cùng lượt. Tránh nhãn mơ hồ như `test`, `file mới`, `wav1`.
- Nói rõ đoạn cần nghe và câu hỏi cần trả lời, ví dụ: “Nghe cụm ‘ba trăm sáu mươi triệu’ ở khoảng giây 4; B có bớt kim loại hơn A không?”
- Sau khi gửi, chờ phản hồi nghe của người dùng trước khi kết luận hoặc tiếp tục tinh chỉnh theo chất lượng chủ quan.

## Khi trang nghe không vào được

Kiểm tra lần lượt:

```bash
launchctl list | grep com.hainc.nghe
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8123/
tail -5 logs/may_chu_nghe.log
launchctl kickstart -k gui/$(id -u)/com.hainc.nghe
```

URL đúng nằm trong output của `gui_nghe.sh` hoặc log. Khi ở ngoài nhà, iPhone phải bật Tailscale; trong cùng mạng có thể dùng địa chỉ Wi-Fi được ghi trong log.

## Bất biến cần giữ

- Không chép tay file vào `nghe/`; luôn dùng `scripts/gui_nghe.sh` để giữ nhãn và thứ tự thời gian.
- Không thêm `nghe/` vào git.
- Không tuyên bố đã tự nghe file nếu chưa có công cụ audio thực sự phát/nhận biết nội dung.
- Khi giao phần việc audio cho agent khác, nhắc rõ phải dùng `$gui-file-nghe`; chỉ tên công việc không đảm bảo agent biết cần xin đánh giá nghe từ người dùng.

Các thành phần liên quan: `scripts/gui_nghe.sh`, `scripts/may_chu_nghe.py`, thư mục ngoài git `nghe/`, và launchd service `com.hainc.nghe`.
