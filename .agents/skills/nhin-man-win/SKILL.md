---
name: nhin-man-win
description: Xem và thao tác desktop Windows `admin-pc` qua SSH bằng ảnh chụp và tọa độ. Dùng cho cửa sổ native/Electron, hộp thoại, khay hệ thống hoặc màn hình Windows mà browser trên Mac không thấy; không dùng thay HTTP, log hoặc browser khi các kênh đó đủ để kiểm tra.
---

# Xem và điều khiển màn hình Windows

Dùng `scripts/man_win.sh` để chuyển lệnh vào desktop session đang đăng nhập trên `admin-pc`. Mỗi thao tác phải theo vòng lặp: chụp ảnh → xem ảnh bằng công cụ đọc ảnh của Codex → lấy tọa độ từ ảnh nguyên kích thước → thao tác → chụp lại để xác nhận.

## Lệnh

```bash
scripts/man_win.sh chup
scripts/man_win.sh bam 330 236
scripts/man_win.sh bam2 330 236
scripts/man_win.sh phai 330 236
scripts/man_win.sh chuot 330 236
scripts/man_win.sh go 'xin chào'
scripts/man_win.sh phim '{ENTER}'
```

Lệnh `chup` in đường dẫn ảnh cục bộ, thường là `/tmp/man_hinh_win.png`. Mở đúng file đó bằng công cụ xem ảnh (`view_image` khi có), không suy đoán giao diện từ log hoặc từ lần chụp trước.

## Chọn đúng công cụ

- Kiểm tra dịch vụ: dùng HTTP health endpoint.
- Đọc log hoặc tiến trình: dùng SSH/PowerShell.
- Kiểm thử web: dùng `$test-web-win` và browser qua tunnel.
- Chỉ dùng skill này cho UI native, cửa sổ Electron, hộp thoại Windows, trạng thái đăng nhập hoặc khay hệ thống.

## Bất biến kỹ thuật

- SSH trên Windows chạy ở Session 0 và không có desktop. Không thay `schtasks /it` trong script bằng lệnh `CopyFromScreen`/`SendInput` trực tiếp qua SSH.
- Ảnh phải giữ nguyên kích thước. Tọa độ click là 1:1 với ảnh; không lấy tọa độ từ ảnh đã thu nhỏ.
- Kích thước `VirtualScreen` đọc trong Session 0 có thể sai. Lấy kích thước từ ảnh vừa chụp.
- Script chờ file kết quả đổi timestamp. Không thay bằng khoảng ngủ cố định rồi đọc kết quả cũ.
- Lệnh và văn bản tiếng Việt được truyền qua file/base64 để tránh lỗi nhiều tầng quoting và encoding.

## Chẩn đoán nhanh

| Triệu chứng | Kiểm tra |
|---|---|
| `The handle is invalid` | Tác vụ đang chạy ở Session 0 thay vì desktop session |
| Ảnh đen | Màn hình Windows đang khóa |
| Click trượt | Ảnh/tọa độ cũ hoặc cửa sổ đã di chuyển; chụp lại |
| PowerShell che app | Tác vụ thiếu `-WindowStyle Hidden` |
| Tiếng Việt sai dấu | Dữ liệu không đi qua file base64 |
| Tác vụ tạo được nhưng không chạy | Kiểm tra user `/ru Admin` và `query session` |

Các file liên quan: `scripts/man_win.sh`, `scripts/tac_vu_man.ps1`, `scripts/chup_man_win.ps1`, `scripts/dieu_khien_man_win.ps1`.
