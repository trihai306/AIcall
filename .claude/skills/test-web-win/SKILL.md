---
name: test-web-win
description: Sửa code trên Mac rồi đẩy sang máy Windows admin-pc qua Tailscale, khởi động lại dịch vụ và tự kiểm thử web thật (http://localhost:8100 qua SSH tunnel) bằng browser tool. Dùng skill này khi người dùng nói "test trên máy Windows", "check bên web test", "chạy thử máy thật", "kiểm tra trên GPU", "đẩy code sang win", "sync sang máy Windows", "test thực tế", "xem trên máy kia có chạy không", hoặc sau khi bạn vừa sửa backend/ hay frontend/ mà cần xác minh trên môi trường có CUDA thay vì nhờ người dùng nhìn hộ. Cũng dùng khi user nói deploy to windows, remote test, test on real machine, check the live web.
---

# Test web thật trên máy Windows (qua Tailscale)

Dự án này chạy ở **hai nơi khác nhau, không đồng bộ tự động**:

| | Mac (máy đang code) | Windows `admin-pc` (máy test thật) |
|---|---|---|
| Đường dẫn | `/Users/hainc/duan/freelancer/chat-ai` | `C:\duan\chat-ai` |
| Port backend | 8000 (`.env`) | **8100** (`.env` riêng) |
| Thiết bị | CPU | **CUDA — RTX 5070, 12GB** |
| STT/TTS/Ollama | thường không đủ | chạy đầy đủ |
| Git | không có repo | không có repo |

Hai máy **không cùng LAN**, chỉ đi qua Tailscale (`ssh win` → `100.117.154.82`, key sẵn, không mật khẩu). Vì không có git ở cả hai đầu nên **đồng bộ code là việc thủ công của bạn** — sửa file trên Mac xong mà không đẩy sang thì máy Windows vẫn chạy code cũ, và bạn sẽ test nhầm rồi kết luận sai.

Ý nghĩa thực tế: đây là nơi duy nhất kiểm chứng được hành vi thật của STT/TTS/LLM. Kết quả đo trên Mac không nói lên điều gì về độ trễ hay chất lượng.

## Bước 0 — Preflight (luôn làm trước)

Một lệnh duy nhất trả lời cả ba câu hỏi: tunnel có chưa, backend sống không, và **đang nói chuyện với đúng máy Windows hay không**.

```bash
curl -s -m 8 http://127.0.0.1:8100/api/health
```

Đọc trường `platform` trong kết quả:

| Kết quả | Nghĩa | Làm gì |
|---|---|---|
| `"platform":"Windows"` + `"device":"cuda"` | Đúng máy, sẵn sàng | Sang Bước 1 |
| `"platform":"Darwin"` | **Đang trúng backend trên chính Mac** — sai máy | Tắt backend Mac hoặc đổi port, đừng test tiếp |
| Không kết nối được | Chưa có tunnel | Mở tunnel bên dưới |

Mở tunnel khi thiếu:

```bash
ssh -f -N -o ExitOnForwardFailure=yes -L 8100:127.0.0.1:8100 win
```

Báo `Address already in use` nghĩa là tunnel đã có sẵn — đó là tin tốt, đi tiếp, đừng giết nó.

Nếu `ssh win` treo hoặc từ chối, kiểm tra Tailscale trước khi nghi ngờ SSH:

```bash
/Applications/Tailscale.app/Contents/MacOS/Tailscale status | grep admin-pc
```

Phải thấy `active`. Máy Windows đang ngủ/tắt là nguyên nhân phổ biến nhất.

**Vì sao phải dùng tunnel thay vì gõ thẳng `http://100.117.154.82:8100`:** browser tool chặn đọc DOM của site không phải localhost (mỗi thao tác đòi người dùng bấm duyệt). Qua tunnel nó thành `localhost` nên bạn dùng được đầy đủ `read_page`, `read_console_messages`, `computer`, `javascript_tool` mà không phiền người dùng.

## Bước 1 — Đẩy code sang Windows

Mặc định đẩy **đúng những file vừa sửa**, không đồng bộ cả cây thư mục. Đường dẫn Windows viết bằng dấu `/`:

```bash
scp backend/services/tts_service.py win:C:/duan/chat-ai/backend/services/tts_service.py
```

Nhiều file / cả thư mục thì gói tar rồi bung qua SSH (đã kiểm chứng an toàn với file nhị phân):

```bash
tar --exclude='__pycache__' --exclude='.venv' -czf - backend frontend \
  | ssh win 'cmd /c tar -xzf - -C C:/duan/chat-ai'
```

`cmd /c` là bắt buộc: shell mặc định của SSH trên Windows là PowerShell, nó không an toàn với luồng nhị phân qua stdin.

**Tuyệt đối không đẩy** những thứ này — mỗi cái đều đã hoặc sẽ làm hỏng máy Windows:

| Không đẩy | Lý do |
|---|---|
| `.env` | Windows dùng `PORT=8100`, đè bằng bản Mac (8000) là mất web ngay |
| `.venv/` | Virtualenv Windows có `python.exe` + torch CUDA riêng, đè là hỏng toàn bộ |
| `models/` | Hàng GB, và bản CT2 của PhoWhisper chỉ có trên Windows |
| `data/`, `logs/` | Dữ liệu chạy thật của máy đó, đè là mất |

## Bước 2 — Áp dụng thay đổi

Cách áp dụng phụ thuộc bạn sửa gì. Đừng restart khi không cần — mỗi lần restart tốn khoảng **60–90 giây** nạp lại model.

**Chỉ sửa `frontend/`** (HTML/CSS/JS): không cần restart. Backend đọc thẳng từ đĩa (`StaticFiles(directory="frontend")` và `FileResponse` cho `index.html`). Đẩy file xong chỉ cần tải lại trang ở Bước 3.

**Sửa `backend/` hoặc `whisper_server/`**: phải restart. Lưu ý `start_services.ps1` **bỏ qua tiến trình đang chạy**, nên gọi start không thôi sẽ không nạp code mới — bắt buộc stop trước:

```bash
ssh win 'cd C:\duan\chat-ai; .\scripts\stop_services.ps1; .\scripts\start_services.ps1 -Detached'
```

Script giữ nguyên Ollama (thêm `-All` vào stop nếu thật sự cần tắt luôn). Rồi chờ tới khi sống hẳn:

```bash
for i in $(seq 1 30); do curl -s -m 5 http://127.0.0.1:8100/api/health && break; sleep 5; done
```

Chỉ coi là xong khi `services` báo `stt/llm/tts/rag` đều ok — cổng mở trước lúc model nạp xong.

## Bước 3 — Kiểm thử web thật

Mở khung trình duyệt (lần đầu trong phiên):

```
preview_start  →  url: http://localhost:8100
```

Đã mở rồi thì `navigate` tới `http://localhost:8100` để tải lại (bắt buộc sau khi sửa frontend).

Xác nhận UI đã bắt được backend — chờ trạng thái `Đã kết nối` rồi mới thao tác:

```
javascript_tool → document.querySelector('[class*="status"]').innerText
```

Sau đó test như người dùng thật: `read_page` để lấy `ref` của các nút và ô nhập, `computer` để gõ/bấm, `read_console_messages` để bắt lỗi JS. Các phần tử chính của trang: ô nhập câu hỏi, nút gửi, chọn kịch bản (vay tín chấp / vay mua nhà / thẻ tín dụng / tiết kiệm), chọn giọng đọc.

WebSocket `/ws/call/{session_id}` chạy tốt qua tunnel — không cần cấu hình gì thêm.

**Đừng kết luận về độ trễ từ Mac.** Đường Tailscale hiện đi qua DERP relay (~100–140ms), cộng thêm vào mọi phép đo. Muốn số liệu thật thì đo ngay trên máy Windows (`scripts/measure_v2.ps1`), đừng bấm giờ qua tunnel.

## Bước 4 — Đọc log khi có lỗi

Nguồn sự thật nằm ở máy Windows, không phải màn hình trình duyệt:

```bash
ssh win 'Get-Content C:\duan\chat-ai\logs\backend.log -Tail 40'
```

| File | Chứa gì |
|---|---|
| `logs\backend.log` | FastAPI + uvicorn + toàn bộ log service (STT/TTS/RAG) |
| `logs\pho-server.log` | PhoWhisper STT |
| `logs\ollama.log` | Ollama |
| `logs\_run\*.bat` | Lệnh thật đã dùng để khởi chạy — xem khi nghi start sai tham số |

Log mới boot có thể còn 0 byte do đệm; chờ vài giây rồi đọc lại thay vì kết luận dịch vụ chết.

## Lệnh trên Windows: cạm bẫy hay gặp

Shell mặc định là **PowerShell**, không phải bash:

| Đừng dùng | Dùng thay thế |
|---|---|
| `head` / `tail` | `Select-Object -First N` / `Get-Content -Tail N` |
| `grep` | `Select-String` |
| `curl` | **không tồn tại trên máy này** — kiểm tra HTTP từ Mac qua tunnel |
| `rsync` | không có — dùng `scp` hoặc tar pipe ở Bước 1 |
| Ống nhị phân qua PowerShell | bọc `cmd /c` |

Đã có sẵn trên Windows: `git`, `scp`, `tar`, `ssh`.

ExecutionPolicy là `RemoteSigned` — file `.ps1` đẩy bằng `scp` chạy bình thường. Nếu gặp lỗi bị chặn (thường do file tải từ internet có dấu Zone), gỡ bằng `Unblock-File <đường dẫn>`.

## Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân thường gặp |
|---|---|
| Sửa code rồi mà hành vi y hệt cũ | Chưa đẩy file, hoặc gọi `start` mà quên `stop` trước |
| `platform: Darwin` trong health | Đang test nhầm backend trên Mac |
| Web trắng / không kết nối | Backend chưa nạp xong model — chờ hết 90s rồi mới nghi lỗi |
| `ssh win` treo | Máy Windows ngủ, hoặc Tailscale rớt |
| Web hỏng ngay sau khi sync | Lỡ đè `.env` — Windows phải là `PORT=8100` |
| Trình duyệt đòi duyệt từng thao tác | Đang mở bằng IP `100.117.154.82` thay vì `localhost` qua tunnel |
