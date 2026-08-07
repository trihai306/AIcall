---
name: test-app-flow
description: Chạy và kiểm thử end-to-end app desktop VoiceBank AI (Electron + FastAPI) qua electron MCP - khởi động app, kiểm tra kết nối WebSocket, gửi 1 lượt chat, duyệt 9 tab, đọc log lỗi, chụp màn hình, rồi dọn tiến trình. Dùng skill này BẤT CỨ KHI NÀO người dùng muốn chạy thử / test / smoke test / kiểm tra app, hỏi "app còn chạy được không", "test luồng chat", "thử lại giao diện", "kiểm tra sau khi sửa", "chạy app lên xem", hoặc sau khi bạn vừa sửa code trong desktop/, frontend/ hay backend/ và cần tự xác minh thay vì nhờ người dùng nhìn hộ. Cũng dùng khi người dùng nói run app, test the app, verify the UI, check if it still works, e2e test, smoke test.
---

# Test luồng app VoiceBank AI

App gồm 2 phần chạy cùng nhau: **Electron shell** (`desktop/app/main.js`) tự spawn **backend FastAPI** (`backend/main.py`, port 8000), rồi load UI từ `http://127.0.0.1:8000` (chính là `frontend/index.html`). UI nói chuyện với backend qua WebSocket `/ws/call/{session_id}`.

Bạn điều khiển app qua các tool `electron_*` của MCP server `electron`, kết nối bằng Chrome DevTools Protocol ở **port 9222**. Port này chỉ mở khi app chạy với cờ `--dev`.

Điều đó dẫn tới nguyên tắc quan trọng nhất: **MCP server không tự khởi động được app** (bản này không có tool launch). Bạn phải tự chạy app bằng Bash trước, rồi mới dùng tool.

## Bước 0 — Kiểm tra app đã chạy chưa

Luôn làm bước này trước. Khởi động chồng lên một app đang chạy sẽ tạo tiến trình mồ côi và làm port 8000 xung đột.

```bash
curl -s --max-time 2 http://127.0.0.1:9222/json/version | head -3 || echo "CHUA CHAY"
```

Nếu đã chạy: nhảy thẳng xuống Bước 2. Nếu chưa: Bước 1.

## Bước 1 — Khởi động app

```bash
cd desktop && node launcher.js --dev > /tmp/electron-test.log 2>&1 &
```

Chạy nền và ghi log ra file, vì stdout của app trộn cả log backend Python (`[srv] ...`) — đó là nguồn duy nhất để đọc lỗi phía server.

Rồi chờ port CDP mở (thường vài giây):

```bash
for i in $(seq 1 30); do curl -s --max-time 1 http://127.0.0.1:9222/json/version >/dev/null && break; sleep 1; done
```

**Lần boot đầu backend có thể mất tới 5 phút** vì phải nạp model embedding/TTS — `main.js` chờ tối đa 300s. Trong lúc đó cửa sổ hiển thị `pages/loading.html`. Đừng kết luận app hỏng khi thấy trang loading; hãy poll health:

```bash
for i in $(seq 1 60); do curl -s --max-time 2 http://127.0.0.1:8000/api/health && break; sleep 5; done
```

## Bước 2 — Bắt đúng cửa sổ

`list_electron_windows` để xem target. App mở DevTools ở dev mode nên sẽ có nhiều hơn một target — cái bạn cần là target `type: page` có title **VoiceBank AI**.

Xác nhận đã ở đúng màn hình bằng `electron_get_url`:

| URL thấy được | Nghĩa là |
|---|---|
| `http://127.0.0.1:8000/` | Đã vào app, test tiếp được |
| `.../pages/loading.html` | Backend chưa sẵn sàng, chờ thêm |
| `.../pages/error.html` | Backend chết hẳn — đọc `/tmp/electron-test.log`, dừng test UI |

## Các luồng cần kiểm

Chạy theo thứ tự; luồng sau phụ thuộc luồng trước. Sau mỗi luồng gọi `read_electron_logs` để bắt lỗi JS phía renderer.

### A. Kết nối WebSocket

Đây là điều kiện sống còn của mọi thứ khác — không có WS thì chat không chạy.

- `electron_query_text_by_selector` `#statusText` → phải là **"Đã kết nối"**
- `electron_query_text_by_selector` `#sessionId` → phải khác `—`

`#sessionId` chỉ được điền khi server trả message `connected`, nên nó là bằng chứng WS thông hai chiều, chắc hơn là nhìn cái chấm màu.

### B. Một lượt chat hoàn chỉnh

```
electron_fill_input       #textInput  ← "Lãi suất gửi tiết kiệm 6 tháng bao nhiêu?"
electron_click_by_selector button[onclick="sendText()"]
electron_wait_for_function  document.getElementById('turnCount').textContent !== '0'   (timeout 60000)
```

Nút gửi không có `id`, nên bám vào `onclick`. Có thể thay bằng `electron_press_key` Enter vì `#textInput` bắt phím Enter.

Xác minh sau khi xong:
- `#turnCount` ≥ 1
- `#valTotal` khác `—` (metrics từ `turn_complete` đã về)
- `#chat` chứa câu hỏi vừa gửi và một bong bóng trả lời

**Phân biệt lỗi app và thiếu model.** Nếu xuất hiện bong bóng `system` màu lỗi, đó là backend trả `type: error` — thường do thiếu Ollama / PhoWhisper / TTS chứ không phải bug UI. Kiểm tra bằng `curl -s http://127.0.0.1:8000/api/setup/status` rồi báo là vấn đề môi trường, đừng đi sửa code frontend.

### C. Điều hướng 9 tab

Các tab: `chat`, `contacts`, `devices`, `benchmark`, `voice`, `training`, `models`, `settings`, `logs`.

Với từng tab: `electron_click_by_selector` `button[data-page="<tên>"]`, rồi `electron_query_visible_by_selector` `#page-<tên>` phải `true`. Mỗi trang tự gọi API riêng khi mở, nên đây cũng là cách quét nhanh xem endpoint nào vỡ — đọc `read_electron_logs` sau vòng lặp.

### D. Danh bạ (chỉ khi đụng tới phần này)

Điền `#contactPhone`, `#contactName` → `electron_click_by_text` "Thêm vào danh bạ" → khối `#contactStats` phải đổi số.

## Nguyên tắc khi test

**`electron_eval` chỉ để chẩn đoán, không để sửa.** Nó là lối thoát cuối cùng khi không có tool chuyên dụng nào đọc được thứ bạn cần. Nếu thấy UI sai, sửa file nguồn trong `frontend/` hoặc `backend/` rồi test lại — vá DOM bằng eval tạo ảo giác đã xong việc trong khi bug vẫn nguyên.

**Sửa xong không cần khởi động lại toàn bộ.** `frontend/` được FastAPI phục vụ tĩnh, chỉ cần reload cửa sổ. Sửa `backend/` hoặc `desktop/app/main.js` thì mới phải tắt và chạy lại.

**Chụp màn hình khi báo cáo thay đổi giao diện.** `electron_take_screenshot` (tên đúng là vậy, không phải `take_screenshot`). Với thay đổi logic thì log và giá trị DOM là bằng chứng tốt hơn ảnh.

## Dọn dẹp

Luôn dọn khi test xong, kể cả khi test thất bại giữa chừng — tiến trình còn sống sẽ giữ port 8000 và 9222, làm lần test sau hỏng theo cách rất khó đoán.

```bash
pkill -f "remote-debugging-port=9222"; pkill -f "uvicorn backend.main:app"; sleep 1
pgrep -fl "uvicorn backend.main" || echo "da don sach"
```

Giữ app chạy nếu người dùng nói rõ là họ muốn tự xem tiếp.

## Báo cáo

Nêu kết quả từng luồng kèm bằng chứng cụ thể (giá trị DOM đọc được, dòng log, mã lỗi) — không nói chung chung "app chạy ổn". Luồng nào bỏ qua thì nói rõ đã bỏ và vì sao.

| Luồng | Kết quả | Bằng chứng |
|---|---|---|
| A. WebSocket | ✅ | `#statusText` = "Đã kết nối", session `a3f2...` |
| B. Chat 1 lượt | ❌ | bong bóng system: "Ollama không phản hồi" |
| C. 9 tab | ✅ | tất cả `#page-*` hiển thị, log sạch |
