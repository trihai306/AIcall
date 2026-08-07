# Hệ Thống AI Gọi Điện Tư Vấn Khách Hàng - Offline 100%

## Lĩnh vực: Ngân hàng - Tư vấn dịch vụ vay & thẻ tín dụng
## Ngôn ngữ: Tiếng Việt
## Quy mô: 1-5 cuộc gọi đồng thời

---

## 1. Tổng Quan Hệ Thống

```
┌─────────────────────────────────────────────────────────────────┐
│                    MÁY TÍNH LOCAL (OFFLINE)                     │
│                                                                 │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │ Asterisk │◄──►│ STT      │◄──►│ LLM      │◄──►│ TTS      │  │
│  │ PBX      │    │ Whisper  │    │ Ollama   │    │ F5-TTS   │  │
│  │ (SIP)    │    │ .cpp     │    │ (Qwen3)  │    │ ViVoice  │  │
│  └────┬─────┘    └──────────┘    └────┬─────┘    └──────────┘  │
│       │                               │                         │
│       │          ┌──────────┐    ┌────┴─────┐                  │
│       │          │ Call     │    │ Training │                   │
│       │          │ Manager  │    │ Pipeline │                   │
│       │          │ (Web UI) │    │ (LoRA)   │                   │
│       │          └──────────┘    └──────────┘                   │
│       │                                                         │
│  ┌────┴─────┐                                                   │
│  │ VoIP     │                                                   │
│  │ Gateway  │◄──── Đường dây điện thoại / SIM Gateway           │
│  └──────────┘                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Luồng hoạt động chính:

```
Khách hàng nhấc máy
       │
       ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Asterisk    │────►│  Whisper.cpp │────►│  LLM         │
│  nhận audio  │     │  Audio → Text│     │  Hiểu ý      │
│  stream      │     │  tiếng Việt  │     │  + Trả lời   │
└──────────────┘     └──────────────┘     └──────┬───────┘
                                                  │
       ┌──────────────┐     ┌──────────────┐      │
       │  Asterisk    │◄────│  F5-TTS      │◄─────┘
       │  phát audio  │     │  ViVoice     │
       │  cho KH      │     │  Text→Audio  │
       └──────────────┘     └──────────────┘
```

---

## 2. Các Thành Phần Chi Tiết

### 2.1. Telephony Layer - Tổng Đài IP

| Thành phần | Công nghệ | Mô tả |
|-----------|-----------|-------|
| IP PBX | **Asterisk 20 LTS** | Tổng đài IP mã nguồn mở, xử lý SIP/RTP |
| VoIP Gateway | **GoIP / Dinstar** | Chuyển đổi GSM ↔ SIP (gắn SIM điện thoại) |
| Giao thức | SIP + RTP | Báo hiệu cuộc gọi + truyền audio |
| Codec | G.711 (PCMU/PCMA) | Codec audio chuẩn cho thoại |

**Cách hoạt động:**
- Asterisk quản lý toàn bộ cuộc gọi (dial plan, routing, recording)
- VoIP Gateway gắn SIM điện thoại, cho phép gọi đi/nhận cuộc gọi qua mạng GSM
- Audio stream được forward real-time tới module STT qua AudioSocket hoặc EAGI

**Tùy chọn Gateway phần cứng:**

| Thiết bị | Số kênh SIM | Giá tham khảo |
|----------|-------------|---------------|
| GoIP-1 | 1 SIM | ~$50-80 |
| GoIP-4 | 4 SIM | ~$150-200 |
| Dinstar UC2000-VE | 4-8 SIM | ~$200-400 |

### 2.2. Speech-to-Text (STT) - Nhận dạng giọng nói

| Thành phần | Công nghệ | Mô tả |
|-----------|-----------|-------|
| Engine chính | **Whisper.cpp** | Port C++ của OpenAI Whisper, chạy offline |
| Model khuyến nghị | `whisper-small` hoặc `whisper-medium` | Cân bằng tốc độ (<1s) và chính xác |
| VAD | **Silero VAD** | Phát hiện giọng nói chính xác, cắt silence nhanh |
| Thay thế | **Vosk** (kaldi-based) | Nhẹ hơn, latency thấp hơn, dùng khi phần cứng yếu |

**So sánh Whisper models (RTX 5070 - mục tiêu < 1s):**

| Model | VRAM | Latency (RTX 5070) | Tiếng Việt | Khuyến nghị |
|-------|------|-------------------|-----------|-------------|
| whisper-tiny | 0.5 GB | ~50ms | Kém | Không dùng |
| whisper-base | 0.5 GB | ~80ms | Trung bình | Dự phòng |
| **whisper-small** | **1 GB** | **~150ms** | **Khá tốt (90%+)** | **Tốt nhất cho tốc độ** |
| **whisper-medium** | **2 GB** | **~250ms** | **Tốt (93%+)** | **Cân bằng nhất** |
| whisper-large-v3 | 3 GB | ~500ms | Rất tốt (95%+) | Quá chậm cho mục tiêu <1s |

**Chiến lược STT cho < 1s:**
1. **Silero VAD** chạy trên CPU → phát hiện chính xác lúc KH nói xong (50-100ms)
2. **Whisper small/medium** với sliding window 1s → transcribe chỉ đoạn có giọng nói (150-250ms)
3. Kết hợp streaming: gửi partial text cho LLM ngay khi có, không đợi toàn bộ câu

### 2.3. Large Language Model (LLM) - Bộ não AI

| Thành phần | Công nghệ | Mô tả |
|-----------|-----------|-------|
| Runtime | **Ollama** | Quản lý và chạy LLM local dễ dàng |
| Backend | **llama.cpp** | Inference engine C++ hiệu năng cao |
| Model chính | **Qwen3-4B** | Nhanh, tiếng Việt tốt, TTFT < 120ms |
| Model thay thế 1 | **Qwen2.5-7B-Instruct** | Chất lượng cao hơn, chậm hơn |
| Model thay thế 2 | **Vistral-7B-Chat** | LLM tiếng Việt của VinAI |
| Quantization | GGUF Q4_K_M (FP4 trên RTX 5070) | Tận dụng Tensor Cores Gen 5 |

**So sánh LLM - ưu tiên tốc độ TTFT < 1s (RTX 5070):**

| Model | Tiếng Việt | VRAM (Q4) | TTFT | Tok/s | Đánh giá |
|-------|-----------|-----------|------|-------|----------|
| **Qwen3-4B** | **★★★★☆** | **~3 GB** | **80-120ms** | **100-130** | **Khuyến nghị #1** |
| Phi-4-mini-3.8B | ★★★☆☆ | ~2.5 GB | 70-100ms | 110-140 | Nhanh nhất, TV yếu |
| Qwen2.5-7B | ★★★★☆ | ~5 GB | 120-180ms | 70-90 | Chất lượng cao |
| Vistral-7B | ★★★★★ | ~5 GB | 150-200ms | 60-80 | TV tốt nhất, chậm hơn |

> **TTFT** (Time To First Token): Thời gian sinh token đầu tiên - chỉ số quan trọng nhất cho mục tiêu < 1s.
> Với streaming pipeline, KH bắt đầu nghe AI nói ngay sau TTFT + TTS chunk đầu (~200ms tổng).

### 2.4. Text-to-Speech (TTS) - Tổng hợp giọng nói

| Thành phần | Công nghệ | Mô tả |
|-----------|-----------|-------|
| Engine chính | **F5-TTS-Vietnamese-ViVoice** | TTS tiếng Việt chất lượng cao, voice cloning |
| Base model | F5-TTS_Base (Flow Matching) | Nhanh hơn diffusion, RTF ~0.15 |
| Vocoder | **Vocos** | Chuyển mel-spectrogram → waveform |
| Dữ liệu training | 1000 giờ tiếng Việt | Vi-Voice, VLSP 2021/2022/2023 |
| License | CC-BY-NC-SA-4.0 | Chỉ dùng cho nghiên cứu/nội bộ |

**Tại sao chọn F5-TTS-Vietnamese-ViVoice:**

| Tiêu chí | F5-TTS ViVoice | Piper TTS | VITS |
|----------|---------------|-----------|------|
| Chất lượng giọng Việt | ★★★★★ | ★★★☆☆ | ★★★★☆ |
| Zero-shot voice clone | **Có** (chỉ cần 5-10s audio mẫu) | Không | Không |
| Tốc độ (RTF) | ~0.15 (GPU) | ~0.05 (CPU) | ~0.3 (GPU) |
| VRAM cần thiết | ~2-3 GB | 0 (CPU) | ~1-2 GB |
| Tự nhiên / Emotion | Rất tự nhiên | Trung bình | Khá tốt |
| Offline 100% | **Có** | Có | Có |

**Cách hoạt động F5-TTS:**

```
                    ┌─────────────┐
                    │ Audio mẫu   │ (5-10 giây giọng nhân viên NH)
                    │ ref.wav     │
                    └──────┬──────┘
                           │
┌──────────┐        ┌──────▼──────┐        ┌──────────┐
│ Text từ  │───────►│  F5-TTS     │───────►│ Audio    │
│ LLM      │        │  ViVoice    │        │ output   │
│          │        │  + Vocos    │        │ (giọng   │
└──────────┘        └─────────────┘        │ giống    │
                                           │ ref.wav) │
                                           └──────────┘
```

**Cài đặt & Sử dụng:**

```bash
# Clone repo
git clone https://github.com/nguyenthienhy/F5-TTS-Vietnamese
cd F5-TTS-Vietnamese
python -m pip install -e .

# Download model từ HuggingFace
# https://huggingface.co/hynt/F5-TTS-Vietnamese-ViVoice
mv F5-TTS-Vietnamese-ViVoice/config.json F5-TTS-Vietnamese-ViVoice/vocab.txt

# Inference
f5-tts_infer-cli \
    --model "F5TTS_Base" \
    --ref_audio ref.wav \
    --ref_text "cả hai bên hãy cố gắng hiểu cho nhau" \
    --gen_text "dạ anh ơi, hiện bên em đang có chương trình vay ưu đãi" \
    --speed 1.0 \
    --vocoder_name vocos \
    --vocab_file F5-TTS-Vietnamese-ViVoice/vocab.txt \
    --ckpt_file F5-TTS-Vietnamese-ViVoice/model_last.pt
```

**Voice Cloning cho nhân viên ngân hàng:**
- Chỉ cần thu âm **5-10 giây** giọng mẫu (ref.wav) + text tương ứng (ref_text)
- F5-TTS sẽ sinh audio mới giống giọng mẫu đó
- Có thể chuẩn bị nhiều giọng khác nhau (nam/nữ, Bắc/Nam)
- Output resample về 8000 Hz (G.711) cho telephony

**Streaming TTS cho < 1s:**
- Chia text từ LLM thành từng cụm 8-10 từ (tại dấu phẩy, dấu chấm)
- F5-TTS sinh audio từng cụm → phát ngay cho KH
- RTF ~0.15 nghĩa là 1s audio chỉ mất ~150ms để sinh → nhanh hơn real-time 6.5x

### 2.5. Call Manager - Quản lý cuộc gọi

| Thành phần | Công nghệ | Mô tả |
|-----------|-----------|-------|
| Backend API | **FastAPI** (Python) | REST API quản lý cuộc gọi |
| Database | **SQLite** | Lưu trữ KH, lịch sử, kịch bản |
| Web UI | **Vue.js / React** | Dashboard quản trị |
| Task Queue | **Celery + Redis** | Hàng đợi lên lịch gọi |

**Chức năng chính:**
- Import danh sách khách hàng (CSV/Excel)
- Lên lịch gọi tự động theo chiến dịch
- Theo dõi trạng thái cuộc gọi real-time
- Ghi âm & lưu transcript cuộc gọi
- Báo cáo & thống kê (tỷ lệ nghe máy, thời gian gọi, kết quả)
- Quản lý kịch bản tư vấn (script templates)

---

## 3. Kịch Bản Tư Vấn Ngân Hàng

### 3.1. Cấu trúc kịch bản (Dialog Flow)

```
┌─────────────┐
│  Chào hỏi   │ "Xin chào anh/chị [Tên]. Em là [Tên AI] từ ngân hàng [X]"
└──────┬──────┘
       │
       ▼
┌─────────────┐     ┌────────────┐
│ Xác nhận    │────►│ KH không   │──► Cảm ơn + Kết thúc
│ nhu cầu     │     │ quan tâm   │
└──────┬──────┘     └────────────┘
       │ KH quan tâm
       ▼
┌─────────────┐
│ Tư vấn      │ Giới thiệu sản phẩm phù hợp
│ sản phẩm    │ (vay, thẻ tín dụng, tiết kiệm)
└──────┬──────┘
       │
       ▼
┌─────────────┐     ┌────────────┐
│ Xử lý      │────►│ Giải đáp   │
│ câu hỏi    │     │ thắc mắc   │
└──────┬──────┘     └────────────┘
       │
       ▼
┌─────────────┐
│ Chốt lịch  │ Đặt lịch gặp tư vấn viên / gửi hồ sơ
│ hẹn         │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Kết thúc    │ Cảm ơn + tổng kết
└─────────────┘
```

### 3.2. System Prompt mẫu cho LLM

```
Bạn là nhân viên tư vấn của Ngân hàng [Tên NH], tên là [Tên NV].
Nhiệm vụ: Gọi điện tư vấn khách hàng về dịch vụ vay vốn và thẻ tín dụng.

QUY TẮC:
1. Luôn xưng "em" và gọi khách là "anh/chị"
2. Nói ngắn gọn, mỗi lượt trả lời tối đa 2-3 câu
3. Không bịa thông tin về lãi suất, phí nếu chưa được cung cấp
4. Nếu KH hỏi ngoài phạm vi, nói: "Dạ em sẽ ghi nhận và có chuyên viên liên hệ lại ạ"
5. Nếu KH từ chối, cảm ơn lịch sự và kết thúc
6. Không gọi lại nếu KH đã từ chối rõ ràng

SẢN PHẨM ĐANG TƯ VẤN:
- Vay tín chấp: Lãi suất từ X%/năm, hạn mức đến Y tỷ
- Vay mua nhà: Lãi suất ưu đãi X% trong Z năm đầu
- Thẻ tín dụng: Miễn phí thường niên năm đầu, cashback X%

THÔNG TIN KHÁCH HÀNG:
- Họ tên: {customer_name}
- Sản phẩm quan tâm: {interested_product}
- Ghi chú: {notes}
```

### 3.3. Ví dụ hội thoại

```
AI:  "Xin chào anh Minh. Em là Lan từ ngân hàng ABC. Em gọi để giới thiệu
      chương trình vay ưu đãi dành riêng cho anh. Anh có tiện nghe không ạ?"

KH:  "Ừ, nói nhanh đi"

AI:  "Dạ vâng. Hiện bên em đang có chương trình vay tín chấp với lãi suất
      chỉ từ 7.9% một năm, hạn mức lên đến 500 triệu, giải ngân trong 24 giờ.
      Anh có đang có nhu cầu vay vốn không ạ?"

KH:  "Lãi suất như vậy thì trả hàng tháng bao nhiêu?"

AI:  "Dạ, ví dụ anh vay 200 triệu trong 3 năm thì mỗi tháng anh trả khoảng
      6.8 triệu bao gồm cả gốc và lãi ạ. Anh muốn em tính cho khoản vay
      cụ thể nào không ạ?"
```

---

## 4. Training Pipeline - Huấn Luyện Dữ Liệu

### 4.1. Tổng quan quy trình training

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Thu thập     │────►│ Tiền xử lý   │────►│ Fine-tune    │
│ dữ liệu     │     │ & Format     │     │ LoRA         │
└──────────────┘     └──────────────┘     └──────┬───────┘
                                                  │
┌──────────────┐     ┌──────────────┐             │
│ Triển khai   │◄────│ Đánh giá     │◄────────────┘
│ Production   │     │ & Test       │
└──────────────┘     └──────────────┘
```

### 4.2. Nguồn dữ liệu training

| Nguồn | Loại dữ liệu | Mục đích |
|-------|-------------|----------|
| Bản ghi cuộc gọi thực | Audio → Transcript | Học phong cách tư vấn thực tế |
| FAQ ngân hàng | Hỏi-Đáp | Kiến thức sản phẩm |
| Quy trình tư vấn | Document | Luồng hội thoại chuẩn |
| Tình huống xử lý | Scenario | Xử lý phản đối, từ chối |
| Thông tin sản phẩm | Catalog | Chi tiết lãi suất, phí, điều kiện |

### 4.3. Format dữ liệu training (ChatML)

```json
{
  "conversations": [
    {
      "role": "system",
      "content": "Bạn là nhân viên tư vấn ngân hàng ABC..."
    },
    {
      "role": "user",
      "content": "Lãi suất vay mua nhà bao nhiêu?"
    },
    {
      "role": "assistant",
      "content": "Dạ anh/chị ơi, hiện bên em đang có chương trình vay mua nhà với lãi suất ưu đãi từ 6.5%/năm trong 2 năm đầu. Sau đó lãi suất thả nổi theo thị trường, thường dao động từ 8-10%/năm ạ. Anh/chị đang tìm mua nhà ở khu vực nào ạ?"
    }
  ]
}
```

### 4.4. Fine-tune với LoRA

```bash
# Công cụ: Unsloth (tối ưu cho máy local)
# Hỗ trợ: NVIDIA GPU 8GB+ VRAM

pip install unsloth

# Hoặc dùng LLaMA-Factory (giao diện web)
git clone https://github.com/hiyouga/LLaMA-Factory.git
cd LLaMA-Factory
pip install -e .
llamafactory-cli webui  # Mở giao diện training
```

**Thông số training khuyến nghị:**

| Thông số | Giá trị | Ghi chú |
|---------|---------|---------|
| Base model | Vistral-7B-Chat | Hoặc Qwen2.5-7B |
| LoRA rank | 16-32 | Rank cao hơn = học nhiều hơn |
| LoRA alpha | 32-64 | Thường = 2x rank |
| Learning rate | 2e-4 | |
| Epochs | 3-5 | Theo dõi loss để tránh overfit |
| Batch size | 4 | Tùy VRAM |
| Max length | 2048 | Đủ cho hội thoại tư vấn |
| Dataset size tối thiểu | 500-1000 mẫu | Càng nhiều càng tốt |

**Sau khi train xong:**

```bash
# Merge LoRA adapter vào model gốc
python merge_lora.py --base_model vistral-7b --lora_path ./output/lora

# Convert sang GGUF để chạy trên Ollama
python convert.py ./merged_model --outtype f16
./quantize ./merged_model/model-f16.gguf ./model-q4_k_m.gguf q4_k_m

# Import vào Ollama
ollama create banking-advisor -f Modelfile
```

### 4.5. RAG (Retrieval-Augmented Generation) - Bổ sung kiến thức

Thay vì fine-tune toàn bộ, dùng RAG để cập nhật thông tin sản phẩm linh hoạt:

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│ Tài liệu    │────►│ Embedding    │────►│ Vector DB    │
│ sản phẩm    │     │ (bge-m3)     │     │ (ChromaDB)   │
└─────────────┘     └──────────────┘     └──────┬───────┘
                                                 │
                    ┌──────────────┐              │ Truy xuất
                    │ LLM trả lời │◄─────────────┘
                    │ + context    │
                    └──────────────┘
```

| Thành phần | Công nghệ | Offline |
|-----------|-----------|--------|
| Embedding model | `bge-m3` hoặc `multilingual-e5-large` | Có |
| Vector database | **ChromaDB** hoặc **FAISS** | Có |
| Chunking | LangChain text splitter | Có |

**Ưu điểm RAG:**
- Cập nhật lãi suất, chương trình KM mới mà không cần re-train model
- Trả lời chính xác dựa trên tài liệu chính thức
- Giảm hiện tượng hallucination

---

## 5. Yêu Cầu Phần Cứng

### 5.1. Cấu hình khuyến nghị - RTX 5070 (1-5 cuộc gọi đồng thời)

| Thành phần | Yêu cầu |
|-----------|---------|
| CPU | Intel i7 Gen 13+ / AMD Ryzen 7 7700X+ |
| RAM | 32 GB DDR5 |
| GPU | **NVIDIA RTX 5070 12GB GDDR7** |
| SSD | 500 GB NVMe |
| Network | Card mạng Gigabit (cho SIP/VoIP nội bộ) |
| OS | Ubuntu 22.04/24.04 LTS |

**Tại sao RTX 5070:**

| Đặc điểm | Giá trị | Lợi ích |
|----------|---------|---------|
| VRAM | 12 GB GDDR7 | Đủ chạy STT + LLM + TTS đồng thời |
| Bandwidth | 672 GB/s | Nạp model nhanh, giảm latency |
| Tensor Cores Gen 5 | FP4/FP8 | Tăng tốc inference 20-30% so với RTX 40xx |
| AI TOPS | 988 | Xử lý đa tác vụ AI mượt |
| Giá | ~$550 (~14 triệu VNĐ) | Hiệu năng/giá tốt nhất cho AI offline |

### 5.2. Cấu hình nâng cấp (nếu cần chất lượng cao hơn)

| Thành phần | Yêu cầu | Lý do nâng cấp |
|-----------|---------|----------------|
| GPU | RTX 5070 Ti **16GB** (~$750) | Chạy model 7B-14B + VRAM dư cho batch |
| RAM | 64 GB DDR5 | Nhiều cuộc gọi đồng thời |

### 5.3. Ước tính tài nguyên theo module (tối ưu < 1s)

| Module | CPU | RAM | GPU VRAM | Disk |
|--------|-----|-----|----------|------|
| Asterisk PBX | 2 cores | 512 MB | - | 1 GB |
| Silero VAD | 1 core | 100 MB | - | 50 MB |
| Whisper.cpp (small/medium) | 2 cores | 1 GB | 1-2 GB | 1 GB |
| Ollama + Qwen3-4B (Q4) | 4 cores | 4 GB | 3 GB | 3 GB |
| F5-TTS ViVoice + Vocos | 2 cores | 2 GB | 2-3 GB | 2 GB |
| ChromaDB (RAG) | 1 core | 1 GB | - | 2 GB |
| Call Manager + Redis | 2 cores | 1 GB | - | 1 GB |
| **Tổng** | **~14 cores** | **~10 GB** | **~6-8 GB** | **~10 GB** |

> RTX 5070 (12GB) còn dư **4-6 GB VRAM** → có thể nâng model lên Qwen2.5-7B
> hoặc chạy 2-3 cuộc gọi đồng thời với batched inference.

### 5.4. Tùy chọn không có GPU (chỉ CPU) - KHÔNG khuyến nghị cho < 1s

Nếu không có GPU NVIDIA (latency sẽ > 3s):

- Dùng **Vosk** thay Whisper (streaming native trên CPU)
- Dùng model **Qwen2.5-1.5B** Q4 hoặc **Phi-3-mini**
- F5-TTS không chạy tốt trên CPU → dùng **Piper TTS** thay thế
- macOS: Whisper.cpp hỗ trợ **Metal** (GPU Apple Silicon M1+)

---

## 6. Kiến Trúc Phần Mềm Chi Tiết

### 6.1. Stack công nghệ

```
├── Telephony
│   ├── Asterisk 20 LTS          # IP PBX
│   ├── PJSIP                    # SIP stack
│   └── AudioSocket/EAGI         # Audio streaming interface
│
├── AI Engine
│   ├── whisper.cpp               # STT offline
│   ├── Silero VAD                # Voice Activity Detection
│   ├── Ollama + llama.cpp        # LLM runtime (Qwen3-4B)
│   ├── F5-TTS ViVoice + Vocos   # TTS tiếng Việt + voice clone
│   └── ChromaDB                  # Vector DB cho RAG
│
├── Application
│   ├── Python 3.11+              # Ngôn ngữ chính
│   ├── FastAPI                   # REST API
│   ├── WebSocket                 # Real-time communication
│   ├── SQLite                    # Database
│   ├── Redis                     # Cache + Message queue
│   └── Celery                   # Task scheduler
│
├── Frontend
│   ├── Vue.js 3 / React          # Web dashboard
│   └── TailwindCSS               # UI framework
│
└── DevOps
    ├── Docker Compose             # Container orchestration
    ├── Nginx                      # Reverse proxy
    └── Supervisor                 # Process manager
```

### 6.2. Cấu trúc thư mục dự án

```
chat-ai/
├── docker-compose.yml
├── .env.example
│
├── asterisk/                     # Cấu hình tổng đài
│   ├── Dockerfile
│   ├── extensions.conf           # Dial plan
│   ├── pjsip.conf                # SIP configuration
│   └── modules.conf
│
├── ai_engine/                    # Core AI
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── stt/
│   │   ├── whisper_service.py    # Whisper STT wrapper
│   │   └── vad.py                # Voice Activity Detection
│   ├── llm/
│   │   ├── ollama_client.py      # Ollama API client
│   │   ├── prompt_manager.py     # System prompt templates
│   │   └── conversation.py       # Quản lý ngữ cảnh hội thoại
│   ├── tts/
│   │   ├── f5tts_service.py      # F5-TTS ViVoice wrapper
│   │   ├── voice_manager.py      # Quản lý giọng mẫu (ref audio)
│   │   └── audio_utils.py        # Audio format conversion
│   └── rag/
│       ├── embedder.py           # Document embedding
│       ├── retriever.py          # Context retrieval
│       └── knowledge_base.py     # Quản lý knowledge base
│
├── call_manager/                 # Quản lý cuộc gọi
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                   # FastAPI entry point
│   ├── models/
│   │   ├── customer.py
│   │   ├── campaign.py
│   │   ├── call_log.py
│   │   └── script.py
│   ├── services/
│   │   ├── dialer.py             # Auto-dialer logic
│   │   ├── scheduler.py          # Lên lịch gọi
│   │   ├── recorder.py           # Ghi âm cuộc gọi
│   │   └── analytics.py          # Thống kê, báo cáo
│   └── api/
│       ├── customers.py
│       ├── campaigns.py
│       ├── calls.py
│       └── reports.py
│
├── frontend/                     # Dashboard
│   ├── Dockerfile
│   ├── package.json
│   └── src/
│       ├── views/
│       │   ├── Dashboard.vue
│       │   ├── Customers.vue
│       │   ├── Campaigns.vue
│       │   ├── CallMonitor.vue
│       │   └── Reports.vue
│       └── components/
│
├── training/                     # Training pipeline
│   ├── requirements.txt
│   ├── prepare_data.py           # Chuẩn bị dữ liệu
│   ├── train_lora.py             # Fine-tune LoRA
│   ├── merge_export.py           # Merge & export model
│   ├── train_tts.py              # Train custom voice
│   └── data/
│       ├── raw/                  # Dữ liệu thô
│       ├── processed/            # Dữ liệu đã xử lý
│       └── templates/            # Mẫu kịch bản
│
├── models/                       # Model files (gitignored)
│   ├── whisper/
│   ├── llm/
│   ├── tts/
│   └── embedding/
│
├── knowledge/                    # RAG knowledge base
│   ├── products/                 # Thông tin sản phẩm
│   ├── faq/                      # Câu hỏi thường gặp
│   ├── policies/                 # Chính sách, quy định
│   └── scripts/                  # Kịch bản tư vấn
│
└── docs/
    ├── ARCHITECTURE.md           # Tài liệu này
    ├── SETUP.md                  # Hướng dẫn cài đặt
    ├── TRAINING.md               # Hướng dẫn training
    └── API.md                    # API reference
```

---

## 7. Luồng Xử Lý Cuộc Gọi Chi Tiết

### 7.1. Outbound Call (Gọi đi)

```
1. Scheduler trigger cuộc gọi
   │
2. Call Manager gửi lệnh ORIGINATE tới Asterisk AMI
   │
3. Asterisk quay số qua VoIP Gateway → GSM → Điện thoại KH
   │
4. KH nhấc máy → Asterisk kết nối AudioSocket tới AI Engine
   │
5. [LOOP] Audio Processing:
   │
   ├─► 5a. Audio stream (KH nói) → VAD phát hiện giọng nói
   │       → Whisper.cpp chuyển thành text
   │
   ├─► 5b. Text → LLM (kèm conversation history + RAG context)
   │       → LLM sinh câu trả lời
   │
   ├─► 5c. Câu trả lời → F5-TTS ViVoice → Audio
   │       → Asterisk phát cho KH nghe
   │
   └─► 5d. Lưu transcript + cập nhật call log
   │
6. Kết thúc cuộc gọi (KH gác máy / AI kết thúc / timeout)
   │
7. Lưu recording + cập nhật trạng thái campaign
```

### 7.2. Streaming Pipeline - Mục tiêu < 1 giây

**Vấn đề pipeline tuần tự (CHẬM):**

```
Tuần tự: STT xong → LLM xong → TTS xong → phát audio = 1.5-3s
```

**Giải pháp: Streaming pipeline (chồng lấp các bước):**

```
KH nói:     ████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░
VAD:        ░░██░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  ← detect nói xong
STT stream: ░░░░████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░  ← partial text
LLM stream: ░░░░░░░░████████████░░░░░░░░░░░░░░░░░░░░  ← token by token
TTS stream: ░░░░░░░░░░░░░███████████░░░░░░░░░░░░░░░░  ← audio chunk
KH nghe:    ░░░░░░░░░░░░░░░░████████████████████░░░░  ← nghe liên tục
                               ▲
                               │
                     ~400-700ms từ lúc KH nói xong
```

**Latency breakdown (RTX 5070 + Streaming):**

| Bước | Thời gian | Ghi chú |
|------|-----------|---------|
| Silero VAD (detect nói xong) | 50-100ms | Chạy CPU, rất nhanh |
| Whisper small streaming | 150-250ms | FP16 trên RTX 5070 |
| LLM TTFT (token đầu tiên) | 80-120ms | Qwen3-4B Q4, FP4 Tensor Cores |
| F5-TTS (chunk đầu tiên) | 100-150ms | RTF ~0.15, sinh 8-10 từ |
| **Tổng đến khi KH nghe** | **~400-700ms** | **Đạt yêu cầu < 1s** |

```python
# Streaming pipeline - pseudo-code

async def process_turn_streaming(audio_stream, call_session):
    # 1. Phát filler ngay lập tức (0ms delay)
    asyncio.create_task(play_filler(call_session, "Dạ vâng ạ"))

    # 2. VAD + STT streaming
    customer_text = await vad_and_transcribe(audio_stream)

    # 3. RAG (chạy song song với STT nếu có partial text)
    relevant_docs = await rag.retrieve(customer_text, top_k=3)

    # 4. LLM streaming → TTS streaming → phát audio
    text_buffer = ""
    async for token in ollama.stream(
        model="banking-advisor",
        messages=call_session.history + [{"role": "user", "content": customer_text}],
        system=build_system_prompt(call_session.customer, relevant_docs)
    ):
        text_buffer += token
        # Khi gặp dấu phẩy/chấm hoặc đủ 8-10 từ → sinh audio + phát ngay
        if should_flush(text_buffer):
            audio_chunk = await f5tts.synthesize(
                text=text_buffer,
                ref_audio=call_session.voice_ref,
                ref_text=call_session.voice_ref_text
            )
            await asterisk.play(audio_chunk)
            text_buffer = ""

    # 5. Cập nhật history
    call_session.add_turn(customer_text, full_response)
```

**Kỹ thuật tối ưu < 1s:**

| # | Kỹ thuật | Tiết kiệm | Độ khó |
|---|---------|-----------|--------|
| 1 | **Streaming pipeline** (chồng lấp STT→LLM→TTS) | -50% tổng latency | Trung bình |
| 2 | **Silero VAD** thay vì chờ silence timeout | -200ms | Dễ |
| 3 | **Whisper small** thay large-v3 | -250ms | Dễ |
| 4 | **Qwen3-4B** thay 7B (TTFT thấp hơn) | -80ms | Dễ |
| 5 | **Filler audio** câu giờ tự nhiên | Perceived latency ~0 | Dễ |
| 6 | **F5-TTS streaming** từng cụm từ | -200ms | Trung bình |
| 7 | **FP4 quantization** trên RTX 5070 Blackwell | -20~30% | Tự động |
| 8 | **KV-cache** giữ context giữa các turn | -50ms TTFT | Dễ |

**Filler audio (câu giờ tự nhiên):**

```
KH nói xong → Phát ngay "Dạ vâng ạ..." (pre-recorded, 0ms delay)
            → Đồng thời STT + LLM đang xử lý
            → ~500ms sau: bắt đầu phát câu trả lời thật
```

Danh sách filler pre-record bằng F5-TTS:

- "Dạ vâng ạ..."
- "Dạ, em hiểu rồi ạ..."
- "Vâng, để em xem..."
- "Dạ được ạ..."

---

## 8. Bảo Mật & Tuân Thủ

### 8.1. Bảo mật dữ liệu

| Yêu cầu | Giải pháp |
|---------|----------|
| Mã hóa dữ liệu | SQLite encryption (SQLCipher) |
| Mã hóa recordings | AES-256 cho file ghi âm |
| Access control | JWT authentication cho Web UI |
| Audit log | Ghi log mọi thao tác truy cập |
| Backup | Backup tự động hàng ngày |

### 8.2. Tuân thủ pháp luật

- **Luật ATTT (86/2015/QH13)**: Bảo vệ thông tin cá nhân KH
- **Thông báo ghi âm**: AI phải thông báo cuộc gọi được ghi âm
- **Quyền từ chối**: KH có quyền yêu cầu không gọi lại
- **Do-Not-Call list**: Quản lý danh sách số không gọi
- **Giờ gọi**: Chỉ gọi trong khung giờ cho phép (8h-20h)
- **Nghị định 91/2020/NĐ-CP**: Chống tin nhắn rác, cuộc gọi rác

---

## 9. Giám Sát & Đánh Giá

### 9.1. Metrics theo dõi

| Metric | Mô tả | Mục tiêu |
|--------|-------|----------|
| Answer Rate | Tỷ lệ KH nghe máy | > 40% |
| Avg Call Duration | Thời gian trung bình/cuộc | 2-5 phút |
| Conversion Rate | Tỷ lệ KH quan tâm / đặt lịch hẹn | > 10% |
| STT Accuracy | Độ chính xác nhận dạng giọng nói | > 90% |
| Response Latency | Thời gian AI phản hồi | < 1s |
| Customer Satisfaction | Điểm hài lòng KH (khảo sát) | > 3.5/5 |
| Drop Rate | Tỷ lệ KH gác máy sớm | < 30% |

### 9.2. Dashboard giám sát

```
┌─────────────────────────────────────────────────────┐
│  DASHBOARD - AI Call Center                         │
├──────────┬──────────┬──────────┬───────────────────┤
│ Đang gọi │ Thành    │ Thất bại │ Hôm nay           │
│    3     │ công: 45 │   12     │ Tổng: 60 cuộc     │
├──────────┴──────────┴──────────┴───────────────────┤
│                                                     │
│  Cuộc gọi đang diễn ra:                            │
│  ┌─────────────────────────────────────────────┐   │
│  │ #1 Nguyễn Văn A - 0912xxx - 2:35 - Tư vấn  │   │
│  │ #2 Trần Thị B  - 0987xxx - 1:12 - Chào hỏi │   │
│  │ #3 Lê Văn C    - 0909xxx - 0:45 - Kết nối   │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  Transcript real-time (#1):                         │
│  KH: "Lãi suất vay mua nhà bao nhiêu?"            │
│  AI: "Dạ hiện bên em có lãi suất từ 6.5%..."      │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## 10. Kế Hoạch Triển Khai

### Phase 1: MVP (4-6 tuần)

- [ ] Cài đặt Asterisk + VoIP Gateway
- [ ] Tích hợp Silero VAD + Whisper.cpp STT (small/medium)
- [ ] Setup Ollama + Qwen3-4B
- [ ] Tích hợp F5-TTS-Vietnamese-ViVoice + chuẩn bị giọng mẫu
- [ ] Xây dựng streaming pipeline (STT→LLM→TTS chồng lấp)
- [ ] Test gọi thủ công 1 cuộc, đo latency < 1s

### Phase 2: Training & Tối ưu (2-4 tuần)

- [ ] Thu thập & chuẩn bị dữ liệu training (500+ mẫu)
- [ ] Fine-tune LoRA model cho domain ngân hàng
- [ ] Setup RAG với knowledge base sản phẩm
- [ ] Tối ưu latency: filler audio, FP4 quantization
- [ ] Thu âm giọng mẫu nhân viên NH cho F5-TTS voice clone

### Phase 3: Call Manager & UI (3-4 tuần)
- [ ] Xây dựng API quản lý cuộc gọi
- [ ] Import danh sách KH, lên lịch gọi
- [ ] Dashboard giám sát real-time
- [ ] Hệ thống ghi âm & lưu transcript
- [ ] Báo cáo & thống kê

### Phase 4: Production & Scale (2-3 tuần)
- [ ] Docker containerization
- [ ] Stress test 5 cuộc đồng thời
- [ ] Xử lý edge cases (mất kết nối, timeout, noise)
- [ ] Bảo mật & audit logging
- [ ] Tài liệu vận hành

### Tổng thời gian ước tính: 11-17 tuần

---

## 11. Chi Phí Ước Tính

### 11.1. Phần cứng (một lần)

| Hạng mục | Chi phí (VNĐ) |
|---------|--------------|
| Máy tính (i7 Gen 13 / RTX 5070 / 32GB DDR5) | 30-40 triệu |
| VoIP Gateway GoIP-4 | 3-5 triệu |
| UPS (lưu điện) | 2-3 triệu |
| **Tổng phần cứng** | **35-48 triệu** |

### 11.2. Phần mềm (miễn phí - open source)

| Phần mềm | License | Chi phí |
|----------|---------|--------|
| Asterisk | GPL | Miễn phí |
| Whisper.cpp | MIT | Miễn phí |
| Ollama + Qwen3-4B | Apache 2.0 | Miễn phí |
| F5-TTS ViVoice | CC-BY-NC-SA-4.0 | Miễn phí (phi thương mại) |
| ChromaDB | Apache 2.0 | Miễn phí |

### 11.3. Vận hành (hàng tháng)

| Hạng mục | Chi phí/tháng (VNĐ) |
|---------|-------------------|
| SIM điện thoại (4 số) | 400K-800K |
| Cước gọi | Tùy số cuộc gọi |
| Điện | ~200K-400K |
| **Tổng vận hành** | **~600K-1.2 triệu/tháng** |

---

## 12. Rủi Ro & Giải Pháp

| Rủi ro | Mức độ | Giải pháp |
|--------|--------|----------|
| Nhận dạng giọng nói sai (tiếng Việt vùng miền) | Cao | Thu thập thêm data vùng miền, fine-tune Whisper |
| Latency cao trên CPU | Trung bình | Đầu tư GPU hoặc dùng model nhỏ hơn |
| LLM trả lời sai thông tin | Cao | RAG + guardrails + human review |
| KH phát hiện đang nói với AI | Trung bình | F5-TTS voice clone giọng thật + filler words tự nhiên |
| Quá tải khi gọi đồng thời | Thấp | Giới hạn concurrent calls theo phần cứng |
| Mất điện / Sự cố phần cứng | Thấp | UPS + backup tự động |

---

## Phụ Lục

### A. Lệnh cài đặt nhanh

```bash
# 1. Cài Ollama + Model LLM
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3:4b-q4_K_M

# 2. Cài Whisper.cpp (STT)
git clone https://github.com/ggerganov/whisper.cpp
cd whisper.cpp && make
./models/download-ggml-model.sh small    # hoặc medium

# 3. Cài Silero VAD
pip install silero-vad

# 4. Cài F5-TTS-Vietnamese-ViVoice (TTS)
git clone https://github.com/nguyenthienhy/F5-TTS-Vietnamese
cd F5-TTS-Vietnamese
python -m pip install -e .
# Download model từ HuggingFace:
# https://huggingface.co/hynt/F5-TTS-Vietnamese-ViVoice
mv F5-TTS-Vietnamese-ViVoice/config.json F5-TTS-Vietnamese-ViVoice/vocab.txt

# 5. Cài Asterisk (Ubuntu)
sudo apt install asterisk

# 6. Cài ChromaDB (RAG)
pip install chromadb

# 7. Cài project dependencies
pip install fastapi uvicorn celery redis sqlalchemy websockets
```

### B. Tham khảo

| Resource | URL |
|----------|-----|
| F5-TTS ViVoice | huggingface.co/hynt/F5-TTS-Vietnamese-ViVoice |
| F5-TTS Vietnamese (code) | github.com/nguyenthienhy/F5-TTS-Vietnamese |
| F5-TTS (gốc) | github.com/SWivid/F5-TTS |
| Whisper.cpp | github.com/ggerganov/whisper.cpp |
| Silero VAD | github.com/snakers4/silero-vad |
| Ollama | ollama.com |
| Qwen3 | huggingface.co/Qwen/Qwen3-4B |
| Asterisk PBX | asterisk.org |
| LLaMA-Factory | github.com/hiyouga/LLaMA-Factory |
| ChromaDB | trychroma.com |
| Unsloth | github.com/unslothai/unsloth |
