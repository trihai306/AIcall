# Training LLM theo phong cách tư vấn riêng

Fine-tune một base Qwen nhỏ bằng QLoRA để học **phong cách và cách dẫn dắt**.
Thông tin sản phẩm thay đổi như lãi suất, hạn mức, phí và điều kiện phải ở RAG,
không train cứng vào LoRA.

## Trước khi train — đọc kỹ

**Fine-tune KHÔNG phải lựa chọn đầu tiên.** Thứ tự đúng:

| Nhu cầu | Giải pháp | Công sức |
|---|---|---|
| Model biết thông tin sản phẩm, lãi suất, chính sách | **Bỏ file .md vào `knowledge/`** (RAG) — sửa là ăn ngay, không cần train | Phút |
| Đổi xưng hô, độ dài, giọng điệu chung | **Sửa system prompt** trong `backend/services/llm_service.py` + few-shot | Phút |
| Model bắt chước *cách dẫn dắt hội thoại* đặc trưng, xử lý tình huống theo kịch bản riêng, phong cách nhất quán qua hàng nghìn cuộc gọi | **Fine-tune** (tài liệu này) | Ngày |

Fine-tune cần **tối thiểu ~200 mẫu hội thoại chất lượng** (tốt: 500–1000). Dưới mức đó model học không đủ pattern, dễ overfit vào câu chữ cụ thể.

Trainer hiện dùng dạng **prompt + completion** và chỉ tính loss trên phần trả lời
cuối của assistant. System prompt, lời khách và lịch sử trước đó vẫn được đưa
vào làm ngữ cảnh nhưng không bị học như target. Đồng thời giữ lại 10% làm
holdout để theo dõi `eval_loss` thay vì chỉ nhìn `train_loss`.

**Cực kỳ quan trọng về base model:** production hiện có thể đang chạy model lớn
hơn (ví dụ `qwen3.5:9b`) trong khi cấu hình train mặc định là
`Qwen/Qwen2.5-3B-Instruct` để vừa GPU 12GB. Fine-tune 3B xong rồi chuyển thẳng
sang 3B là một lần **đổi model**, không phải chỉ "thêm kiến thức" cho 9B. Vì vậy
phải A/B trước khi đổi production.

Không đổi riêng `--base-model` thành `Qwen/Qwen3.5-9B` trong pipeline hiện tại.
Qwen3.5-9B dùng kiến trúc `Qwen3_5ForConditionalGeneration` (multimodal), còn
script này đang dùng `FastLanguageModel` và bước deploy đang dùng template
Qwen2.5/ChatML. Muốn fine-tune đúng 9B phải làm profile train + export + template
riêng và đo VRAM trên GPU đích.

### Tài liệu dùng để chốt cú pháp

- TRL SFTTrainer: https://huggingface.co/docs/trl/sft_trainer — định dạng
  conversational prompt/completion, `completion_only_loss`, eval và packing.
- Unsloth LoRA parameters: https://docs.unsloth.ai/basics/lora-parameters-encyclopedia
  — train trên completion, rank/alpha, dropout, weight decay và dấu hiệu overfit.
- Qwen3.5-9B model card: https://huggingface.co/Qwen/Qwen3.5-9B — kiến trúc và
  chat template chính thức của 9B.

**Lưu ý dữ liệu**: nếu dùng ghi âm cuộc gọi thật làm data, phải tuân thủ Nghị định 13/2023 — khách phải được thông báo ghi âm, và cần ẩn danh hoá (xoá tên, SĐT, số tài khoản thật) trước khi train.

## Bước 1 — Chuẩn bị dữ liệu

Bỏ file vào `data/training/` (hoặc upload qua web UI → tab Training). Hai định dạng:

**Định dạng A — JSONL** (mỗi dòng 1 mẫu):
```json
{"messages": [{"role":"system","content":"Bạn là... Chỉ dùng dữ kiện có trong nguồn."},{"role":"user","content":"Tôi muốn vay 200 triệu"},{"role":"assistant","content":"Dạ em ghi nhận anh muốn vay 200 triệu ạ. Anh đang quan tâm thời hạn khoảng bao lâu để em tư vấn đúng thông tin sản phẩm ạ?"}]}
```

**Định dạng B — transcript .txt** (dễ viết tay/chuyển từ ghi âm):
```
# cuoc_goi_01.txt
KH: Alo ai đấy?
TV: Dạ em chào anh ạ, em là Lan gọi từ ngân hàng ABC ạ.
KH: Có việc gì không?
TV: Dạ em xin phép anh một phút, bên em đang có gói vay ưu đãi cho khách hàng thân thiết ạ.
```
`TV:` là lượt model sẽ học. Mỗi lượt TV = 1 mẫu train (kèm ngữ cảnh phía trước).

**Nguồn data gợi ý:**
1. Transcript ghi âm cuộc gọi thật của tư vấn viên giỏi nhất (dùng PhoWhisper server transcribe, sửa tay, gắn nhãn KH/TV)
2. Kịch bản tư vấn nội bộ chuyển thành hội thoại
3. Hội thoại thật từ chính hệ thống này sau khi chạy thử — lấy các cuộc thành công, sửa những chỗ AI trả lời chưa đạt thành câu đúng ý bạn (đây là data quý nhất)

Gom + kiểm tra:
```bash
python training/llm/make_dataset.py
```

## Bước 2 — Train (máy RTX 5070)

```bash
# Tắt service để nhường VRAM
pkill ollama; pkill -f uvicorn

bash training/llm/train.sh              # mặc định: 3 epochs, rank 16
bash training/llm/train.sh --epochs 4 --lora-rank 32   # dataset lớn (>1000 mẫu)
```

- Lần đầu sẽ tạo venv riêng `.venv-train` (Unsloth xung đột dependency với F5-TTS nên không dùng chung venv).
- 500 mẫu × 3 epochs trên RTX 5070 ≈ 30–60 phút.
- VRAM: ~8–10GB (QLoRA 4-bit).
- `make_dataset.py` sẽ chặn mẫu không kết thúc bằng lượt `assistant` vì trainer
  cần tách rõ prompt và completion.
- Với dataset sinh từ `knowledge/`, mảnh RAG được gắn vào
  `THÔNG TIN THAM KHẢO` của **input**. Như vậy model học cách bám nguồn động;
  không nên sinh một đống đáp án chứa facts nhưng input lại không có nguồn.

## Bước 3 — Đánh giá trước khi đưa vào hệ thống

So model production với model vừa train bằng **đúng prompt và cấu hình inference
đang dùng thật**:

```bash
# Chỉ nạp model mới vào Ollama để test, CHƯA đổi .env
python training/llm/deploy_ollama.py

python training/llm/danh_gia.py qwen3.5:9b --rag
python training/llm/danh_gia.py tuvan-qwen --rag
python training/llm/danh_gia_hoi_thoai.py qwen3.5:9b --rag
python training/llm/danh_gia_hoi_thoai.py tuvan-qwen --rag
```

Chỉ đổi model khi bản fine-tune tốt hơn về cả độ đúng, bám mạch và độ trễ.

## Bước 4 — Đưa vào hệ thống

Script in hướng dẫn cụ thể cuối quá trình train. Tóm tắt:

```bash
# Chỉ chạy lệnh này SAU KHI A/B đạt
python training/llm/deploy_ollama.py --set-env
```

Script tạo `tuvan-qwen`; thêm `--set-env` mới đổi `OLLAMA_MODEL`. Giao diện web
mặc định cũng chỉ nạp model để A/B, không tự đổi production.

## Bước 5 — Theo dõi sau khi đổi

So sánh trước/sau bằng cùng một bộ ~20 câu hỏi test (tab chat hoặc `POST /api/benchmark/llm`):
- Giọng điệu có đúng phong cách bạn muốn?
- Còn trả lời đúng kiến thức chung không? (train quá tay sẽ "quên" — giảm epochs hoặc thêm data đa dạng)
- Vẫn ngắn ≤2 câu? (nếu data của bạn toàn câu dài, model sẽ nói dài theo — data quyết định)

Lặp: thu thêm hội thoại thật → bổ sung data → train lại. Chu kỳ 2–4 tuần/lần là hợp lý.
