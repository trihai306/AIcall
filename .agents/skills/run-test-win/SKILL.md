---
name: run-test-win
description: Chạy pytest của dự án trên Windows `admin-pc` qua SSH. Dùng khi người dùng yêu cầu test trên Windows/GPU, khi test phụ thuộc CUDA, TTS, STT, Ollama hoặc dịch vụ thật; không thay thế bằng kết quả mock/skip trên Mac.
---

# Chạy pytest trên Windows

Windows là môi trường xác nhận cho hành vi phụ thuộc GPU và các model thật. Có thể chạy unit test độc lập nền tảng trên Mac để phản hồi nhanh, nhưng không dùng chúng thay cho test Windows khi phạm vi cần CUDA/TTS/STT/LLM.

| Môi trường | Đường dẫn | Đặc điểm |
|---|---|---|
| Mac | `/Users/hainc/duan/freelancer/chat-ai` | máy sửa code, thiếu một số model/runtime |
| Windows | `C:\duan\chat-ai` | `ssh win`, RTX 5070 12 GB, dịch vụ thật |

## 1. Preflight

```bash
ssh win "echo 'Connected'; python --version"
```

Nếu kết nối lỗi hoặc treo, kiểm tra `admin-pc` trong Tailscale trước khi đổi cấu hình SSH.

## 2. Đồng bộ đúng thay đổi

Đẩy những file cần cho test, không đồng bộ mù toàn bộ repository:

```bash
scp backend/services/tts_service.py win:C:/duan/chat-ai/backend/services/tts_service.py
scp tests/test_tts_service.py win:C:/duan/chat-ai/tests/test_tts_service.py
```

Khi có nhiều file:

```bash
tar --exclude='__pycache__' --exclude='.venv' --exclude='*.pyc' \
  --exclude='models' --exclude='data' --exclude='logs' \
  -czf - backend tests | ssh win 'cmd /c tar -xzf - -C C:/duan/chat-ai'
```

Không đẩy `.env`, `.venv/`, `models/`, `data/` hoặc `logs/`. PowerShell không an toàn cho stdin nhị phân nên tar pipe phải đi qua `cmd /c`.

## 3. Nạp code mới khi cần

- Chỉ thay `tests/`: không restart dịch vụ.
- Thay `backend/` hoặc `whisper_server/`: stop rồi start; gọi start một mình có thể giữ process cũ.

```bash
ssh win 'Set-Location C:\duan\chat-ai; .\scripts\stop_services.ps1; Start-Sleep -Seconds 2; .\scripts\start_services.ps1 -Detached'
```

Poll `http://127.0.0.1:8100/api/health` qua tunnel hoặc `Invoke-WebRequest` trên Windows cho tới khi backend và các service cần thiết sẵn sàng. Việc nạp model có thể mất 30–90 giây; đặt timeout hữu hạn và đọc log nếu quá hạn.

## 4. Chạy test có phạm vi

Ưu tiên case/file liên quan trước, sau đó mở rộng suite nếu rủi ro thay đổi yêu cầu:

```bash
ssh win 'Set-Location C:\duan\chat-ai; .\.venv\Scripts\python.exe -m pytest tests/test_tts_service.py -v --tb=short'
ssh win 'Set-Location C:\duan\chat-ai; .\.venv\Scripts\python.exe -m pytest tests/test_streaming_pipeline.py::test_chunking_sentence_boundary -v --tb=short'
ssh win 'Set-Location C:\duan\chat-ai; .\.venv\Scripts\python.exe -m pytest tests/ -v --tb=short'
```

Dùng `-s` khi cần output chẩn đoán, `-x` khi fail đầu tiên đủ để quyết định, và `-k pattern` để lọc. Nếu test treo, dùng timeout của phiên shell hoặc dừng có kiểm soát rồi xem `logs\backend.log`; không chờ vô hạn.

## 5. Báo cáo bằng chứng

Nêu số `passed/failed/skipped/error`, tên case fail, expected/actual từ assertion, môi trường Windows đã dùng, và bước sync/restart đã thực hiện. Phân biệt lỗi test, lỗi setup/dependency, backend chưa sẵn sàng và lỗi sản phẩm; không tự suy diễn nguyên nhân khi traceback/log chưa chứng minh.
