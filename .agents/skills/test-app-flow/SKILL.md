---
name: test-app-flow
description: Smoke test ứng dụng desktop VoiceBank AI gồm Electron shell, FastAPI, WebSocket và frontend. Dùng khi cần chạy thử app desktop, kiểm tra sau thay đổi trong `desktop/`, `frontend/` hoặc `backend/`, hoặc xác minh luồng điều hướng/chat; dùng `test-web-win` cho web Windows và `nhin-man-win` cho UI native trên Windows.
---

# Smoke test app VoiceBank AI

App phát triển dùng entry `desktop/app/main.js`; `desktop/main.js` là bản cũ. Trên Mac, Electron dùng backend port 8000; bản Windows thật dùng 8100. Chọn môi trường theo yêu cầu và ghi rõ môi trường trong báo cáo.

## Chọn bề mặt kiểm thử

- Renderer/web và WebSocket trên Mac: browser tại `http://127.0.0.1:8000` cho kiểm tra DOM/console ổn định.
- Electron shell, preload IPC, loading/error page, file picker hoặc hành vi cửa sổ trên Mac: điều khiển app native bằng computer-use/CUA.
- Web trên Windows/GPU: dùng `$test-web-win`.
- Electron/cửa sổ native trên Windows: dùng `$nhin-man-win` sau khi bảo đảm app đã chạy.

Browser không chứng minh được IPC hoặc hành vi native Electron; app native không thay thế bằng chứng API/DOM khi cần kiểm tra logic renderer.

## 1. Kiểm tra trạng thái trước khi khởi động

```bash
curl -s --max-time 2 http://127.0.0.1:9222/json/version
curl -s --max-time 2 http://127.0.0.1:8000/api/health
```

Không khởi động chồng nếu app đã chạy. Nếu cần dùng tiến trình hiện có, không dọn nó khi kết thúc.

## 2. Khởi động có quản lý

Chạy `npm run dev` trong `desktop/` bằng một terminal/session được Codex giữ lại để có thể đọc log và gửi Ctrl-C khi xong. Dev mode mở CDP port 9222. Chờ health port 8000 với timeout hữu hạn; lần đầu nạp model có thể lâu. Trang `desktop/app/pages/loading.html` trong lúc chờ không phải bằng chứng lỗi. Nếu chuyển sang error page hoặc quá timeout, đọc log của session trước khi test UI.

Không dùng `pkill` rộng để dọn mọi Electron/uvicorn trên máy. Chỉ dừng session/process mà skill đã tạo, trừ khi người dùng yêu cầu đóng app đang chạy sẵn.

## 3. Kiểm tra nền tảng

Xác minh:

- HTTP `/api/health` trả thành công.
- `#statusText` là `Đã kết nối`.
- `#sessionId` khác `—`, chứng minh WebSocket đã nhận message `connected` hai chiều.
- Console renderer không có lỗi mới.

Nếu backend trả lỗi service/model, kiểm tra `/api/setup/status`; báo đây là vấn đề môi trường khi bằng chứng cho thấy dependency chưa sẵn sàng, không sửa frontend theo phỏng đoán.

## 4. Kiểm tra luồng liên quan

### Điều hướng

Đọc các nút `button[data-page]` từ DOM hiện tại, click từng trang cần thiết và xác minh `#page-<name>` hiển thị. App hiện có nhiều hơn 9 trang, vì vậy không dùng danh sách 9 tab trong tài liệu cũ. Các trang gọi API khi mở; xem network/console sau mỗi nhóm trang.

### Hội thoại

UI chính hiện chỉ cho nói qua `#micBtn`; `#textInput` vẫn có trong DOM nhưng bị ẩn để phục vụ test nội bộ. Chọn một trong hai cách phù hợp:

- Test người dùng thật: thao tác micro, cấp quyền khi được yêu cầu, nói/dùng audio phù hợp và xác minh transcript, phản hồi, audio, `#turnCount` và metrics.
- Smoke test text có kiểm soát: qua JavaScript evaluation của browser, đặt giá trị cho `#textInput` rồi gọi `sendText()`. Đây là thao tác test, không phải vá DOM; không dùng evaluation để sửa trạng thái hoặc che lỗi.

Sau lượt hoàn chỉnh, xác minh `#turnCount` tăng, `#valTotal` khác `—`, `#chat` có câu người dùng và phản hồi. Bong bóng system error là bằng chứng backend trả `type:error`; đọc setup status và log để phân loại.

### Luồng chuyên biệt

Chỉ chạy CRUD danh bạ, thiết bị, huấn luyện, model hoặc các trang khác khi thay đổi/yêu cầu chạm tới chúng. Với thao tác làm đổi dữ liệu, dùng dữ liệu test dễ nhận biết và chỉ dọn đúng dữ liệu do lượt test tạo ra.

## 5. Bằng chứng và dọn dẹp

Chụp ảnh cho thay đổi giao diện; dùng DOM, HTTP, console và log cho logic. Báo từng luồng pass/fail, giá trị quan sát được và phần bỏ qua. Kết thúc bằng cách dừng đúng terminal/session đã khởi động; giữ app chạy nếu người dùng yêu cầu xem tiếp.
