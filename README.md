# AI Banking Call System

Hệ thống AI gọi điện tư vấn khách hàng - chạy 100% offline, bộ model thuần Việt.
Gọi ra theo chiến dịch, nhận cuộc gọi vào, chuyển tiếp cho người thật, ghi âm và
báo cáo. Kịch bản thay được từ giao diện nên mở sang ngành khác không cần sửa code.

**Tài liệu:** [Hướng dẫn sử dụng](docs/HUONG_DAN_SU_DUNG.md) ·
[Báo cáo thực hiện](docs/BAO_CAO_THUC_HIEN.md) ·
[Đặc tả theo hợp đồng](docs/DAC_TA_TINH_NANG_CON_THIEU.md) ·
[Kiến trúc](docs/ARCHITECTURE.md)

## Stack (100% model tiếng Việt)

| Module | Tech | Latency Target |
|--------|------|----------------|
| VAD | Silero VAD (CPU) | endpoint 220ms |
| STT | **PhoWhisper-small** (VinAI, faster-whisper CT2) | ~90ms |
| LLM | Ollama + **Vistral-7B-Chat** (Viet-Mistral, Q4) | TTFT ~70ms |
| TTS | F5-TTS-Vietnamese-ViVoice, **fine-tune giọng riêng** | chunk đầu ~130ms (nfe=8) |
| RAG | ChromaDB + bge-m3 (CPU) | ~100ms |
| **TTFA** | **Streaming pipeline + filler tức thì** | **~500-650ms** |

VRAM trên GPU 12GB (RTX 5070): PhoWhisper ~0.8GB + Vistral Q4 ~5.2GB + F5-TTS ~2.5GB ≈ 8.5GB + KV cache.

## Supported Platforms

| Platform | GPU Backend | Status |
|----------|------------|--------|
| **Windows** (WSL2 + NVIDIA) | CUDA 12.8 | Supported (khuyến nghị: RTX 5070+) |
| **Ubuntu** (NVIDIA GPU) | CUDA 12.8 | Supported |
| **macOS** (Apple Silicon M1+) | Metal / MPS | Supported (dev, chậm hơn) |
| macOS (Intel) | CPU only | Slow but works |
| Linux (no GPU) | CPU only | Slow but works |

> **RTX 50xx (Blackwell)**: bắt buộc driver NVIDIA ≥ 570 (cài trên Windows host nếu dùng WSL2) và PyTorch bản `cu128` — script cài đặt đã tự xử lý. Bản cu121/cu124 sẽ lỗi "no kernel image available".

## Quick Start

```bash
# 1. Install everything (auto-detects macOS vs Linux/WSL2)
chmod +x scripts/install/*.sh scripts/*.sh
bash scripts/install/install_all.sh

# 2. Configure
cp .env.example .env

# 3. Add reference voice for TTS (5-10 seconds recording)
#    models/tts/ref_voices/default.wav
#    models/tts/ref_voices/default.txt  (transcript)
#    Train giọng riêng (giống người thật): xem training/voice/README.md

# 4. Start all services
bash scripts/start_services.sh

# 5. Open browser: http://localhost:8000
```

### Cài model từ giao diện (thay cho bước 1)

Nếu backend chạy được mà thiếu model, mở tab **Cài Model** trong web UI:
kiểm tra model nào còn thiếu, bấm cài từng cái (hoặc "Cài tất cả còn thiếu"),
xem log tải trực tiếp, rồi bật dịch vụ Ollama / PhoWhisper ngay tại đó.
Tương đương chạy tay:

| Model | Script |
|-------|--------|
| Ollama | `bash scripts/install/03_ollama.sh` |
| LLM (`OLLAMA_MODEL` trong .env) | `ollama pull qwen2.5:3b` |
| STT PhoWhisper | `bash scripts/install/02_pho_whisper.sh` |
| TTS F5-TTS ViVoice | `bash scripts/install/07_tts_model.sh` |

## Train giọng nói riêng

```bash
# 1. Thu âm theo kịch bản training/voice/record_script.txt (001.wav ... 060.wav)
# 2. Chuẩn hoá dataset (tự sinh transcript bằng PhoWhisper nếu thiếu):
python training/voice/prepare_dataset.py --input ~/thu_am_giong
# 3. Fine-tune (cần GPU NVIDIA, ~2-4h trên RTX 5070 với 20 phút dữ liệu):
bash training/voice/train.sh ten_giong
# 4. Cập nhật .env theo hướng dẫn cuối script, restart services
```

Chi tiết: [training/voice/README.md](training/voice/README.md)

## Train LLM theo phong cách tư vấn riêng

```bash
# 1. Bỏ hội thoại mẫu (.jsonl hoặc transcript .txt dạng KH:/TV:) vào data/training/
# 2. Gom + kiểm tra:
python training/llm/make_dataset.py
# 3. Train QLoRA trên GPU (tự tạo venv riêng .venv-train):
bash training/llm/train.sh
# 4. Import vào Ollama theo hướng dẫn cuối script, đổi OLLAMA_MODEL trong .env
```

Chi tiết (khi nào nên/không nên fine-tune, format data): [training/llm/README.md](training/llm/README.md)

## App desktop trên Windows (VoiceBank-AI.exe)

Bấm đúp `C:\duan\chat-ai\VoiceBank-AI.exe`. App tự chạy `scripts/start_services.ps1
-Detached -Port 8100` (Ollama + PhoWhisper :8178 + backend :8100, kèm khoá xung GPU
và `OLLAMA_KEEP_ALIVE=-1`), hiện màn chờ có trạng thái từng dịch vụ, rồi vào giao diện
khi TTS nạp xong (~2-3 phút ở lần chạy nguội).

**File exe phải nằm trong thư mục dự án**, cạnh `backend/` và `.venv/`. Chép đi chỗ khác
là app không tìm thấy gì và vào trang lỗi — muốn bấm từ Desktop thì tạo **lối tắt**, đừng
chép file:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\tao_shortcut_desktop.ps1
```

Đóng cửa sổ **không** dừng dịch vụ (chúng chạy detached; nạp lại F5-TTS tốn 2-3 phút).
Muốn dừng hẳn: menu **Hệ thống → Dừng dịch vụ nền**.

Build lại sau khi sửa code trong `desktop/app/`:

```powershell
cd C:\duan\chat-ai\desktop
npx electron-builder --win
Copy-Item ..\dist\VoiceBank-AI.exe ..\VoiceBank-AI.exe -Force
```

Kiểm tra sau khi chạy: `powershell -ExecutionPolicy Bypass -File scripts\kiem_tra_app.ps1`
(in tiến trình, `/api/health`, PhoWhisper, xung GPU).

## Manual Start (step by step)

```bash
# Terminal 1: Ollama
ollama serve

# Terminal 2: PhoWhisper STT server
bash whisper_server/start.sh
# (fallback whisper.cpp: bash whisper_server/start.sh legacy small)

# Terminal 3: FastAPI app
source .venv/bin/activate
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

## Platform-Specific Notes

### macOS (Apple Silicon)
- GPU acceleration via **Metal/MPS** (auto-detected)
- Whisper.cpp builds with `-DGGML_METAL=1`
- PyTorch includes MPS support by default from PyPI
- Install deps via **Homebrew**

### Windows (WSL2 + NVIDIA)
- Install NVIDIA driver on **Windows host** first
- Run everything inside **WSL2** (Ubuntu 22.04)
- Whisper.cpp builds with `-DGGML_CUDA=1`
- PyTorch installed with CUDA index URL
- Browser on Windows connects to `localhost:8000` in WSL2

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Web UI |
| WS | `/ws/call/{session_id}` | Voice conversation WebSocket |
| GET | `/api/health` | Health check + system info |
| POST | `/api/sessions` | Create session |
| GET | `/api/voices` | List available voices |
| POST | `/api/benchmark/full` | Full pipeline benchmark |
| POST | `/api/benchmark/stt` | Benchmark STT only |
| POST | `/api/benchmark/llm` | Benchmark LLM only |
| POST | `/api/benchmark/tts` | Benchmark TTS only |
| GET | `/api/devices` | Thiết bị gọi ra (điện thoại/gateway/modem) |
| POST | `/api/devices` | Thêm thiết bị |
| POST | `/api/devices/{id}/check` | Kiểm tra kết nối thiết bị |
| POST | `/api/devices/{id}/test-call` | Gọi thử qua thiết bị |
| GET | `/api/phones/contacts` | Danh bạ gọi (lọc theo chiến dịch/trạng thái) |
| POST | `/api/phones/contacts/import` | Nhập CSV hoặc danh sách số |
| GET | `/api/phones/contacts/export` | Xuất danh bạ ra CSV |
| POST | `/api/phones/contacts/{id}/call` | Mở phiên AI + bấm số qua thiết bị |
| POST | `/api/phones/contacts/{id}/result` | Ghi kết quả cuộc gọi |
| POST | `/api/phones/call-next` | Gọi số chưa gọi kế tiếp trong chiến dịch |
| GET | `/api/phones/campaigns` | Danh sách chiến dịch |
| POST | `/api/phones/campaigns/{id}/start` | Chạy chiến dịch tự động |
| POST | `/api/phones/campaigns/{id}/pause` · `/resume` · `/stop` | Điều khiển chiến dịch |
| GET | `/api/phones/campaigns/{id}/progress` | Tiến độ chiến dịch |
| POST | `/api/phones/campaigns/{id}/import-from` | Nhập số từ chiến dịch khác |
| WS | `/ws/campaign/{id}` | Tiến độ chiến dịch theo thời gian thực |
| GET/POST | `/api/scenarios` | Kịch bản gọi (B1) |
| GET | `/api/scenarios/template` | Form train kịch bản thống nhất |
| POST | `/api/scenarios/{id}/test` | Chạy thử một lượt hội thoại |
| GET | `/api/reports/calls` | Báo cáo cuộc gọi, đủ bộ lọc |
| GET | `/api/reports/summary` · `/export` | Tổng hợp · xuất CSV |
| GET | `/api/reports/calls/{id}/recording` | Nghe/tải ghi âm |
| POST | `/api/reports/label` | Gắn nhãn hàng loạt |
| GET/POST | `/api/notify/channels` | Kênh Telegram |
| GET/POST | `/api/data-sources` | Nguồn dữ liệu ngoài (Excel/CSV/SQLite) |
| POST | `/api/devices/{id}/inbound/enable` | Bật bot nhận cuộc gọi đến |

## Gọi ra qua thiết bị

Hệ thống không tự nói chuyện với mạng GSM/SIP. Nó điều khiển thiết bị sẵn có
(app gateway trên điện thoại, modem USB có HTTP, tổng đài có click-to-call)
qua một link duy nhất khai trong trang **Thiết bị**:

```
http://192.168.1.50:8080/call?number={number}
```

`{number}` được thay bằng số cần gọi (gọi bằng GET). Nếu link không có
`{number}`, hệ thống POST JSON `{"number": "0912345678"}`. Thiết bị không có
link gọi vẫn quản lý được — chỉ là phải bấm số thủ công trên máy, phiên AI
vẫn được mở để tư vấn.

## Project Structure

```
chat-ai/
├── backend/
│   ├── main.py                    # FastAPI entry point
│   ├── config.py                  # Settings from .env
│   ├── core/
│   │   ├── device.py              # Auto-detect cuda/mps/cpu
│   │   ├── startup.py             # Service initialization
│   │   └── logging_config.py      # Latency logging
│   ├── services/
│   │   ├── vad_service.py         # Silero VAD
│   │   ├── stt_service.py         # Whisper.cpp client
│   │   ├── llm_service.py         # Ollama streaming
│   │   ├── tts_service.py         # F5-TTS ViVoice
│   │   ├── rag_service.py         # ChromaDB RAG
│   │   └── audio_utils.py         # PCM/WAV helpers
│   ├── pipeline/
│   │   ├── streaming_pipeline.py  # Core orchestrator
│   │   ├── session_manager.py     # Call sessions
│   │   └── text_chunker.py        # TTS chunk logic
│   └── api/
│       ├── websocket.py           # WebSocket endpoint
│       ├── calls.py               # REST API
│       └── benchmark.py           # Latency benchmarks
├── frontend/                      # Web UI (HTML/CSS/JS)
├── knowledge/                     # RAG knowledge base
├── models/                        # AI models (gitignored)
├── tools/                         # whisper.cpp, F5-TTS (gitignored)
├── scripts/install/               # Cross-platform setup scripts
└── docs/ARCHITECTURE.md           # Architecture documentation
```
