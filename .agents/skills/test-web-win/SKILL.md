---
name: test-web-win
description: Đồng bộ thay đổi cần thiết sang Windows `admin-pc`, áp dụng code và kiểm thử web thật qua SSH tunnel `localhost:8100`. Dùng cho smoke/E2E web trên GPU hoặc khi người dùng yêu cầu deploy/sync/test trên Windows; không dùng IP Tailscale trực tiếp cho browser nếu tunnel localhost hoạt động.
---

# Kiểm thử web trên Windows

Mac là máy sửa code; Windows tại `C:\duan\chat-ai` là môi trường thật có CUDA. Hai cây code không tự đồng bộ. Chỉ ghi sang Windows khi việc deploy/sync/test Windows nằm trong yêu cầu hiện tại.

## 1. Xác nhận đúng máy

```bash
curl -s -m 8 http://127.0.0.1:8100/api/health
```

Chỉ tiếp tục khi response cho thấy `platform` là Windows và thiết bị mong đợi là CUDA. `platform: Darwin` nghĩa là port đang trúng backend Mac. Nếu chưa có tunnel:

```bash
ssh -f -N -o ExitOnForwardFailure=yes -L 8100:127.0.0.1:8100 win
```

`Address already in use` có thể nghĩa là tunnel đã tồn tại; xác minh lại bằng health response thay vì giết process ngay. Nếu SSH lỗi, kiểm tra Tailscale và trạng thái `admin-pc`.

## 2. Đồng bộ có chọn lọc

Đẩy đúng file vừa sửa khi có thể:

```bash
scp frontend/app.js win:C:/duan/chat-ai/frontend/app.js
scp backend/main.py win:C:/duan/chat-ai/backend/main.py
```

Với nhiều file, dùng tar qua `cmd /c`:

```bash
tar --exclude='__pycache__' --exclude='.venv' -czf - backend frontend \
  | ssh win 'cmd /c tar -xzf - -C C:/duan/chat-ai'
```

Không đẩy `.env`, `.venv/`, `models/`, `data/` hoặc `logs/`. Windows dùng cấu hình/port/model riêng.

## 3. Áp dụng thay đổi

- Chỉ `frontend/`: không restart; tải lại trang.
- `backend/` hoặc `whisper_server/`: stop rồi start để process nạp code mới.

```bash
ssh win 'Set-Location C:\duan\chat-ai; .\scripts\stop_services.ps1; .\scripts\start_services.ps1 -Detached'
```

Poll health có timeout tới khi các service liên quan báo sẵn sàng. Nếu quá hạn, đọc log thay vì tiếp tục test trên trạng thái nửa khởi động.

## 4. Test bằng browser của Codex

Mở `http://localhost:8100` bằng computer-use/browser hiện có. Với CUA, lần gọi đầu phải là entry point hợp lệ theo tài liệu tool, ví dụ `cua.getBrowser({ url: "http://localhost:8100" })` khi người dùng không chỉ định browser; sau đó dùng các API được tool trả về để đọc UI, click, nhập liệu, chờ trạng thái và xem console.

Xác minh tối thiểu:

- `/api/health` vẫn là Windows/CUDA sau khi mở trang.
- Trạng thái UI chuyển thành `Đã kết nối` và `#sessionId` khác `—`.
- Luồng bị thay đổi hoạt động qua thao tác người dùng thực tế.
- Không có lỗi JavaScript mới trong console và request liên quan trả về hợp lệ.
- Với điều hướng, lấy danh sách `button[data-page]` từ DOM hiện tại rồi xác minh trang `#page-<name>` tương ứng; không đóng đinh danh sách tab cũ.

WebSocket `/ws/call/{session_id}` đi qua tunnel. Không dùng độ trễ quan sát từ Mac làm số liệu hiệu năng thật vì Tailscale/DERP có thể cộng độ trễ; đo tại Windows bằng script chuyên dụng khi cần.

## 5. Chẩn đoán và báo cáo

Đọc nguồn sự thật trên Windows:

```bash
ssh win 'Get-Content C:\duan\chat-ai\logs\backend.log -Tail 80'
```

Phân biệt lỗi môi trường/model với lỗi frontend. Báo luồng nào đã chạy, bằng chứng DOM/HTTP/console, lỗi cụ thể và luồng nào bỏ qua. Không nói “web ổn” nếu mới chỉ thấy trang tải được.
