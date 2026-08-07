# Training LLM theo phong cách tư vấn riêng

Fine-tune Vistral-7B bằng QLoRA để model tư vấn đúng giọng điệu, quy trình, sản phẩm của bạn.

## Trước khi train — đọc kỹ

**Fine-tune KHÔNG phải lựa chọn đầu tiên.** Thứ tự đúng:

| Nhu cầu | Giải pháp | Công sức |
|---|---|---|
| Model biết thông tin sản phẩm, lãi suất, chính sách | **Bỏ file .md vào `knowledge/`** (RAG) — sửa là ăn ngay, không cần train | Phút |
| Đổi xưng hô, độ dài, giọng điệu chung | **Sửa system prompt** trong `backend/services/llm_service.py` + few-shot | Phút |
| Model bắt chước *cách dẫn dắt hội thoại* đặc trưng, xử lý tình huống theo kịch bản riêng, phong cách nhất quán qua hàng nghìn cuộc gọi | **Fine-tune** (tài liệu này) | Ngày |

Fine-tune cần **tối thiểu ~200 mẫu hội thoại chất lượng** (tốt: 500–1000). Dưới mức đó model học không đủ pattern, dễ overfit vào câu chữ cụ thể.

**Lưu ý dữ liệu**: nếu dùng ghi âm cuộc gọi thật làm data, phải tuân thủ Nghị định 13/2023 — khách phải được thông báo ghi âm, và cần ẩn danh hoá (xoá tên, SĐT, số tài khoản thật) trước khi train.

## Bước 1 — Chuẩn bị dữ liệu

Bỏ file vào `data/training/` (hoặc upload qua web UI → tab Training). Hai định dạng:

**Định dạng A — JSONL** (mỗi dòng 1 mẫu):
```json
{"messages": [{"role":"system","content":"Bạn là..."},{"role":"user","content":"Lãi suất bao nhiêu?"},{"role":"assistant","content":"Dạ hiện bên em từ sáu phẩy năm phần trăm ạ. Anh định vay khoảng bao nhiêu ạ?"}]}
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

## Bước 3 — Đưa vào hệ thống

Script in hướng dẫn cụ thể cuối quá trình train. Tóm tắt:

```bash
# Copy file gguf xuất ra thành tên chuẩn
cp models/llm/tuvan-gguf/*q4_k_m*.gguf models/llm/vistral-tuvan-q4.gguf
cd models/llm && ollama create vistral-tuvan -f Modelfile.tuvan
```

Sửa `.env`: `OLLAMA_MODEL=vistral-tuvan` → restart services.

## Bước 4 — Đánh giá

So sánh trước/sau bằng cùng một bộ ~20 câu hỏi test (tab chat hoặc `POST /api/benchmark/llm`):
- Giọng điệu có đúng phong cách bạn muốn?
- Còn trả lời đúng kiến thức chung không? (train quá tay sẽ "quên" — giảm epochs hoặc thêm data đa dạng)
- Vẫn ngắn ≤2 câu? (nếu data của bạn toàn câu dài, model sẽ nói dài theo — data quyết định)

Lặp: thu thêm hội thoại thật → bổ sung data → train lại. Chu kỳ 2–4 tuần/lần là hợp lý.
