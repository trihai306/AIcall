# Training LLM theo phong cách tư vấn riêng

Fine-tune một base Qwen nhỏ bằng LoRA để học **phong cách và cách dẫn dắt**.
Thông tin sản phẩm thay đổi như lãi suất, hạn mức, phí và điều kiện phải ở RAG,
không train cứng vào LoRA.

### Bộ hội thoại tiếng Việt tự nhiên

`qwen35_2b_natural_v4.jsonl` được tạo từ bộ nghiệp vụ đã rà soát cộng 54 mẫu
hội thoại viết tay và 108 mẫu sửa lỗi về xưng hô, điều kiện tuổi, ý định dừng
cuộc gọi. Tái tạo bằng:

```bash
python training/llm/make_natural_dialogue_curriculum.py \
  --base data/training/qwen35_2b_style_curriculum_v2.jsonl \
  --output data/training/qwen35_2b_natural_v3.jsonl
python training/llm/make_dialogue_repair_v4.py \
  --base data/training/qwen35_2b_natural_v3.jsonl \
  --output data/training/qwen35_2b_natural_v4.jsonl
```

Sau khi train, chạy `evaluate_natural_dialogue.py --model <candidate>` và
`evaluate_banking_style.py --model <candidate>` trên Windows. Đọc cả nội dung
câu trả lời: các biểu thức chấm tự động không đủ để phát hiện mọi lời hứa sai.
Chỉ cân nhắc chuyển model phục vụ sau khi không còn lỗi nghiệp vụ hoặc xưng hô
trong bộ kiểm tra độc lập; loss giảm không phải bằng chứng đó.

### Vòng Qwen3.5 9B dạy Qwen3.5 2B

`teacher_threshold_questions.py` dùng model 9B đặt câu hỏi theo các tình huống
ngưỡng tuổi trong tài liệu MD. Chỉ nhận câu hỏi qua bộ lọc; đáp án được dựng
từ ngưỡng trong nguồn, không lấy nguyên lời 9B làm sự thật. File audit ghi rõ
câu bị loại. `make_multiturn_repair_v5.py`, `make_dialogue_repair_v6.py` và
`make_composition_repair_v7.py` bổ sung ca nhiều lượt, phân biệt điều kiện,
xưng hô và lời nói tiếng Việt. Dataset hiện tại là
`qwen35_2b_natural_v7.jsonl` (453 mẫu), gồm 7 câu hỏi được nhận từ 36 đề xuất
của 9B và 95 mẫu sửa lỗi ở hai vòng gần nhất.

Vòng v8 thêm 2/26 câu hỏi 9B qua rà thủ công và 42 mẫu sửa cách nói về gửi
tiết kiệm, thành `qwen35_2b_natural_v8.jsonl` (497 mẫu). Ứng viên v8 đạt
9/10 ca hội thoại nhưng chỉ 6/7 ca nghiệp vụ: trả lời sai mốc nợ xấu 8 tháng
so với điều kiện trên 1 năm, và chưa nói ra mức lãi cuối cùng ở một câu nhiều
lượt. Vì vậy v8 chỉ để thử; model phục vụ vẫn là `qwen3.5:9b`. Xem báo cáo
`data/training/banking_v8_eval.json` và `data/training/natural_v8_eval.json`.

Train nhiều lần trên cùng một bộ mẫu không làm model tự hiểu hơn và dễ học thuộc.
Vòng theo dõi chỉ train tiếp khi có mẫu mới đã đối chiếu MD, đủ dung lượng xuất
GGUF và GPU sẵn sàng. Mỗi vòng tạo model thử riêng, đo trên câu chưa dùng làm
đáp án train; `.env` vẫn giữ 9B cho tới khi model mới qua kiểm thử thực tế.

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

**Cực kỳ quan trọng về base model:** production hiện dùng `qwen3.5:9b` trên
Windows. Giao diện train hỗ trợ `Qwen/Qwen3.5-2B` (LoRA 16-bit) và
`Qwen/Qwen2.5-3B-Instruct` (QLoRA 4-bit) trên RTX 5070 12GB. Fine-tune 2B/3B
không biến 9B thành bản mới. Mỗi lần train tạo candidate riêng trong Ollama;
production chỉ đổi sau khi A/B về độ đúng nghiệp vụ và hội thoại.

Không đổi riêng `--base-model` thành `Qwen/Qwen3.5-9B` trên GPU 12GB: chưa có
profile train/export đã kiểm chứng cho 9B ở máy này. 9B hiện dùng làm model
production và có thể kiểm tra câu trả lời của candidate, nhưng kết luận của 9B
cũng phải đối chiếu với tài liệu.

### Luồng hiện dùng trên Windows

1. Đưa tài liệu nghiệp vụ `.md` vào `knowledge/` để RAG tìm nguồn. Chọn một
   dataset đã duyệt trên tab **Training LLM**; file challenge, stress, audit và
   log đánh giá không hiện trong danh sách chọn train.
2. Chọn `Qwen3.5-2B`. Hệ thống chỉ gộp **file được chọn**, gắn cùng quy tắc
   văn phong đang dùng khi trả lời, train và nạp một candidate riêng vào Ollama.
   Bản đang nhận cuộc gọi vẫn là 9B.
3. Kiểm tra bằng `evaluate_banking_style.py` với câu hỏi chưa dùng làm target,
   nhất là mốc tuổi, nợ xấu, tài sản và hội thoại nhiều lượt. Loss giảm không
   thay thế được bước này.

Bộ `qwen35_2b_style_curated_v1.jsonl` có 110 mẫu và chỉ là bản thử nghiệm.
Nó dạy cách nói trung tính, Bắc, Nam ở mức câu chữ khi khách yêu cầu; giọng
âm thanh do mẫu TTS quyết định. Model 2B vẫn có thể suy sai ngưỡng số khi tự
trả lời. `banking_fact_precheck.py` so trực tiếp các điều kiện rõ ràng trong
MD với dữ kiện khách nói và trả lời thẳng ở một số trường hợp đã xác định;
không kết luận phê duyệt khoản vay.

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

Gom + kiểm tra một nguồn cụ thể:
```bash
python training/llm/make_dataset.py --sources ten_dataset.jsonl \
  --output data/training/ten_run_train.jsonl --conversation-style
```

Nếu export GGUF hết dung lượng sau khi LoRA đã lưu, dọn file 16-bit trung gian
(`models/llm/*-gguf/`) nhưng giữ adapter và `*-gguf_gguf/`; chạy
`training/llm/export_adapter_gguf.py --adapter <thư mục adapter> --gguf-dir
<thư mục gguf>` để xuất tiếp mà không train lại.

## Bước 2 — Train (máy RTX 5070)

Trên Windows dùng tab **Training LLM** để chọn dataset và base model; job sẽ
nhả GPU, train, xuất GGUF và nạp candidate. Các lệnh `train.sh` bên dưới chỉ là
đường CLI cũ cho Qwen2.5 trên hệ có bash, không phải đường Windows đang dùng.

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
