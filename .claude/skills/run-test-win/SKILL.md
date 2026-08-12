---
name: run-test-win
description: Chạy pytest trên máy Windows (admin-pc) qua SSH - dùng KHI NGƯỜI DÙNG YÊU CẦU test tính năng, chạy test, kiểm tra test, verify test, hoặc sau khi sửa code backend/whisper_server/desktop cần xác minh bằng test suite. Máy Win có GPU CUDA nên đây là nơi DUY NHẤT test đúng hành vi TTS/STT/LLM thật. KHÔNG chạy test trên Mac trừ khi người dùng nói rõ "test trên máy này" hoặc "local test".
---

# Chạy test trên máy Windows qua SSH

Theo yêu cầu của dự án: **MỌI test tính năng phải chạy trên máy Windows**, không phải Mac. Lý do:

| | Mac (máy code) | Windows admin-pc (máy test) |
|---|---|---|
| GPU | không | **CUDA — RTX 5070, 12GB** |
| TTS/STT/Ollama | thiếu hoặc giả lập | **chạy đầy đủ, model thật** |
| Đường dẫn code | `/Users/hainc/duan/freelancer/chat-ai` | `C:\duan\chat-ai` |
| Kết nối | — | qua Tailscale `ssh win` |

Test trên Mac sẽ skip hầu hết case hoặc mock, cho kết quả sai lệch hoàn toàn so với thực tế.

## Nguyên tắc

- **Luôn đẩy code trước khi test.** Máy Win không tự kéo code — nếu bạn sửa file trên Mac mà quên sync thì test sẽ chạy code cũ.
- **Đừng đẩy `.env`, `.venv/`, `models/`, `data/`, `logs/`.** Mỗi máy có cấu hình riêng, đè là hỏng.
- **Test yêu cầu backend đang chạy** (hầu hết integration test gọi API). Nếu backend chết, khởi động bằng `scripts\start_services.ps1`.

## Bước 0 — Kiểm tra kết nối

```bash
ssh win "echo 'Connected'; python --version"
```

Phải thấy `Connected` và Python 3.11.x. Nếu `ssh win` treo, kiểm tra Tailscale:

```bash
/Applications/Tailscale.app/Contents/MacOS/Tailscale status | grep admin-pc
```

## Bước 1 — Đẩy code sang Windows

### Một vài file (thường gặp nhất)

```bash
scp backend/services/tts_service.py win:C:/duan/chat-ai/backend/services/tts_service.py
scp backend/pipeline/streaming_pipeline.py win:C:/duan/chat-ai/backend/pipeline/streaming_pipeline.py
```

### Nhiều file / cả thư mục

```bash
tar --exclude='__pycache__' --exclude='.venv' --exclude='*.pyc' \
    --exclude='models' --exclude='data' --exclude='logs' \
    -czf - backend tests | ssh win 'cmd /c tar -xzf - -C C:/duan/chat-ai'
```

`cmd /c` bắt buộc vì PowerShell không an toàn với stdin nhị phân.

## Bước 2 — Restart backend nếu cần

**Chỉ sửa code test (`tests/`)**: không cần restart, nhảy thẳng Bước 3.

**Sửa `backend/` hoặc `whisper_server/`**: phải restart để nạp code mới. Script `start_services.ps1` BỎ QUA nếu process đã chạy, nên BẮT BUỘC stop trước:

```bash
ssh win 'cd C:\duan\chat-ai; .\scripts\stop_services.ps1; Start-Sleep -Seconds 2; .\scripts\start_services.ps1 -Detached'
```

Chờ backend sống hẳn (30-90s do nạp model):

```bash
for i in $(seq 1 30); do ssh win 'Invoke-WebRequest -Uri http://127.0.0.1:8100/api/health -UseBasicParsing -TimeoutSec 3' 2>/dev/null && echo "Backend ready" && break; sleep 3; done
```

## Bước 3 — Chạy test

### Test tất cả

```bash
ssh win 'cd C:\duan\chat-ai; .\.venv\Scripts\python.exe -m pytest tests/ -v'
```

### Test một file

```bash
ssh win 'cd C:\duan\chat-ai; .\.venv\Scripts\python.exe -m pytest tests/test_tts_service.py -v'
```

### Test một case cụ thể

```bash
ssh win 'cd C:\duan\chat-ai; .\.venv\Scripts\python.exe -m pytest tests/test_streaming_pipeline.py::test_chunking_sentence_boundary -v'
```

### Thêm flag hữu ích

| Flag | Dùng khi |
|---|---|
| `-v` | Hiện danh sách case đang chạy (luôn dùng) |
| `-s` | Xem print/log của test (debug) |
| `-x` | Dừng ngay khi gặp fail đầu tiên |
| `--tb=short` | Traceback ngắn gọn |
| `-k pattern` | Chỉ chạy case có tên khớp pattern |

Ví dụ: chỉ chạy test TTS, dừng khi fail, hiện log:

```bash
ssh win 'cd C:\duan\chat-ai; .\.venv\Scripts\python.exe -m pytest tests/ -k tts -v -s -x'
```

## Bước 4 — Đọc kết quả

Pytest in ra:

- ✅ **PASSED**: test OK
- ❌ **FAILED**: test hỏng — đọc assertion message và traceback
- ⚠️ **SKIPPED**: bị bỏ qua (thường do `@pytest.mark.skip` hoặc thiếu dependency)
- **ERROR**: lỗi setup/teardown, không phải code test

Tổng kết ở cuối dạng `X passed, Y failed, Z skipped in Ts`.

### Khi test fail

Đọc kỹ assertion message — pytest in ra giá trị expected vs actual:

```
AssertionError: assert 236 < 200
  Expected latency < 200ms, got 236ms
```

Nếu cần thêm context, chạy lại với `-s` để thấy log backend trong lúc test chạy, hoặc đọc log file:

```bash
ssh win 'Get-Content C:\duan\chat-ai\logs\backend.log -Tail 50'
```

## Bảng chẩn đoán

| Triệu chứng | Nguyên nhân | Sửa |
|---|---|---|
| Test pass trên Mac, fail trên Win | Đúng — đó là lý do phải test trên Win | Sửa code theo kết quả Win |
| `ModuleNotFoundError` | Thiếu dependency hoặc sai venv | Kiểm tra `.venv` Win có đúng không |
| Test hỏng hàng loạt sau khi sửa | Quên restart backend | Chạy lại Bước 2 |
| `Connection refused` trong test | Backend chưa khởi động | Bước 2, chờ health OK |
| Kết quả y hệt lần trước dù đã sửa | Chưa đẩy code | Bước 1 lại |
| Test treo vô thời hạn | Backend đang nạp model | Chờ thêm 60s, hoặc check log |

## Báo cáo

Nêu rõ:
- Bao nhiêu case pass/fail/skip
- Case nào fail, lý do cụ thể (từ assertion)
- Có cần sửa code không, sửa ở đâu

Ví dụ tốt:

> Chạy `tests/test_tts_service.py` trên Win: **3 passed, 1 failed**.
> 
> - ❌ `test_latency_under_200ms` fail: latency đo được 236ms (expected <200ms)
> - Nguyên nhân: chưa bật torch.compile cho F5
> - Sửa: thêm `model = torch.compile(model)` vào `TTSService.__init__`

Ví dụ tệ:

> Test xong rồi. Có mấy cái fail nhưng không sao.
