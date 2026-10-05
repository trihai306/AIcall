# Kế hoạch triển khai BankVN học liên tục 24/7

Ngày cập nhật: 2026-09-20

## 1. Việc cần làm

Hoàn thiện BankVN, một LLM ngân hàng ưu tiên tiếng Việt được train từ trọng số ngẫu nhiên và tokenizer riêng, chạy ổn trên RTX 5070 12 GB, gọi được các hàm của VoiceBank và học liên tục theo chu kỳ có kiểm soát mà không tự thay model production.

## 2. Đọc được từ dự án

- `docs/THIET_KE_BANKVN_FROM_SCRATCH.md`: kiến trúc đã chốt theo lộ trình BankVN-350M → 1.3B → 3.2B; Qwen3.5-9B chỉ làm teacher sinh và chấm dữ liệu.
- `training/bankvn/train_tokenizer.py`: tokenizer hiện là SentencePiece BPE từ số 0, có byte fallback và 9 token giao thức BankVN.
- Smoke tokenizer `tokenizer-sp-smoke6` trên Windows ngày 2026-09-20: đủ `tokenizer.model`, `tokenizer.vocab`, `tokenizer.json`, `tokenizer_config.json`; `add_dummy_prefix=False`; ID token cố định là `pad=0`, `unk=1`, `bos=2`, `eos=3`, `system=4`, `user=5`, `assistant=6`, `tool_call=7`, `tool_result=8`.
- Gate tokenizer mới yêu cầu Hugging Face tokenizer và `SentencePieceProcessor` sinh đúng cùng chuỗi token ID cho các câu sanity; `tokenizer-sp-smoke6` đã đạt gate này. Tokenizer smoke5 cũ có cùng vocab/ID nhưng SentencePiece tự thêm dummy prefix nên chỉ dùng làm artifact chẩn đoán.
- Smoke pretrain mới từ `tokenizer-sp-smoke6` trên RTX 5070 ngày 2026-09-20: model random-init chạy thành công 1 bước; 283,689,984 tham số ở vocab smoke 512; loss 6.427; runtime 1.638 giây; CUDA peak allocated 2.90 GB và reserved 3.07 GB. Checkpoint: `models/bankvn/pretrain/sp-smoke6-final/final`.
- Smoke pretrain xác nhận tham số lưu ở FP32 nhưng phép tính train dùng mixed precision BF16; CUDA hỗ trợ BF16. Đây là hành vi đúng của Trainer, không phải lỗi train FP32 toàn phần.
- `training/bankvn/pretrain.py`: checkpoint được lưu và resume được; model dùng gradient checkpointing và optimizer 8-bit theo profile 350M.
- `training/bankvn/teacher_generate.py`: có chống sinh trùng theo `source_id`, lọc PII và kiểm tra tên function theo định nghĩa thật của backend.
- `backend/services/llm_service.py`: BankVN dùng giao thức text `<|bankvn_tool_call|>{...}<|bankvn_end|>`; các model Ollama cũ vẫn giữ native tool calling.
- `training/bankvn/gate.py`: candidate có gate về độ đúng nghiệp vụ, tool calling, tỷ lệ tiếng Việt, chữ ngoại ngữ, hallucination và độ trễ.
- `training/bankvn/continuous.py`: có lock một tiến trình, kiểm tra VRAM, dừng teacher trước khi train student, lưu trạng thái và không tự promote.
- `training/bankvn/run_forever.ps1`: chu kỳ 350M mặc định yêu cầu tối thiểu 7,000 MB VRAM trống, phù hợp với số đo máy Windows hiện tại.
- `common.py` hiện bắt buộc đủ bốn file tokenizer khi lưu checkpoint. `tokenizer_sanity.py` đã PASS trực tiếp trên `models/bankvn/pretrain/sp-smoke6-final/final`, nên checkpoint Mốc A mới đã mang đủ tokenizer nguồn để đi tiếp sang SFT/GGUF.
- File Excel benchmark nghiệp vụ đang có tại `/Users/hainc/Downloads/bo_thu_10k_ban_16b1cb7 (1).xlsx`; sheet mục tiêu là `Tất cả câu hỏi`.

## 3. Giả định tôi chốt thay bạn

- “Thuần tiếng Việt” nghĩa là dữ liệu chính bằng tiếng Việt, loại CJK/Hangul và giảm mạnh câu ngoại ngữ, nhưng vẫn giữ thuật ngữ nghiệp vụ như ATM, OTP, KYC, CIC, Visa, API và JSON · nếu cấm tuyệt đối mọi từ ngoại ngữ thì tokenizer, tài liệu kỹ thuật và function calling phải thiết kế lại.
- Bản đầu tiếp tục mang tên profile `BankVN-350M`, dù số tham số thực tế khoảng 316M khi dùng vocab 32k; tên profile là tên mốc sản phẩm, không phải cam kết đúng tuyệt đối 350 triệu tham số · nếu cần đúng 350M phải điều chỉnh hidden size hoặc số layer rồi đo lại VRAM.
- RTX 5070 12 GB là máy train chính và còn phải phục vụ ứng dụng · vòng train chỉ bắt đầu khi đủ VRAM, chỉ có một trainer, và teacher Ollama phải được dừng trước khi student lên GPU.
- Học 24/7 là các chu kỳ corpus → teacher → pretrain → SFT → benchmark → lưu candidate; không học trực tiếp từ mọi cuộc gọi và không tự dùng câu trả lời của chính model làm chân lý.
- Checkpoint tốt hơn về loss vẫn chưa đủ để đưa vào production · chỉ model vượt toàn bộ gate và bài test VoiceBank mới được cân nhắc promote.
- Mục tiêu “thông minh như 9B” được đo trong nghiệp vụ ngân hàng tiếng Việt và function calling của hệ thống · nếu yêu cầu ngang 9B ở kiến thức tổng quát thì cần thêm dữ liệu, compute và quy mô model ngoài khả năng một RTX 5070 12 GB.
- Giai đoạn đầu ưu tiên chứng minh toàn bộ dây chuyền bằng smoke nhỏ; chỉ chạy pretrain dài sau khi GGUF, Ollama và backend đã hoạt động trọn luồng · nếu bỏ smoke, lỗi định dạng có thể chỉ lộ ra sau nhiều ngày train.

## 4. Cách làm và cái giá

### Trạng thái hiện tại

| Mốc | Trạng thái | Bằng chứng nghiệm thu |
|---|---|---|
| Thiết kế from-scratch | Xong | Có thiết kế, profile 350M/1.3B/3.2B và nguyên tắc không auto-promote |
| Corpus cleaner | Đã có code | Lọc tiếng Việt, CJK/Hangul, dedupe và PII |
| Tokenizer SentencePiece | Đạt smoke6 | Round-trip tiếng Việt đúng; marker là một token; ID 0–8 đúng; HF encode = SentencePiece encode |
| Pretrain random-init | Đạt smoke + resume đến step 600 | 100 bước đầu + resume 500 bước đều không OOM/NaN; checkpoint-600 đủ state để resume |
| SFT bằng tokenizer mới | Đạt router refine1 | 360 steps/120 epochs; train loss 0.0572493; peak allocated 4.93 GB, reserved 5.25 GB |
| GGUF | Đạt v10/v11 | F16 ~567.5 MB; token ID 3–8 giữ đúng `USER_DEFINED=4`; exporter có metadata gate tự chặn regression |
| Ollama inference | Đạt v10 | Raw tool-call 2/2 đúng marker + JSON; decode khoảng 552–572 tok/s |
| Tool calling end-to-end | Đạt Mốc D | Live backend PASS toàn bộ gate BankVN + Qwen native tools; BankVN exact 2/2 |
| Train dài 24/7 | Chưa bật | Mốc D đã qua nhưng vẫn cần corpus/benchmark Mốc E/G trước khi bật worker dài |

### Kết quả đo thực tế ngày 2026-09-20

- Pretrain 100 bước đầu: 13.16 giây, 7.60 step/s, aggregate `train_loss=3.495`, CUDA peak allocated 2.88 GB / reserved 3.01 GB.
- Resume thêm 500 bước lên `global_step=600`: 63.76 giây, 9.41 step/s, aggregate `train_loss=0.04166`, CUDA peak allocated 2.89 GB / reserved 3.09 GB, không OOM/NaN.
- Checkpoint `checkpoint-600` có đủ `optimizer.pt`, `scheduler.pt`, `rng_state.pth`, `trainer_state.json`; `global_step=600`, nên resume là thật chứ không train lại từ đầu.
- Loss trung bình theo block 50-step: `1–50=5.2104`, `51–100=1.78054`, `101–150=0.15520`, `151–200=0.077852`, `201–250=0.065706`, `251–300=0.056462`, `301–350=0.043344`, `351–400=0.031614`, `401–450=0.021568`, `451–500=0.019954`, `501–550=0.016810`, `551–600=0.0113978`.
- SFT router checkpoint `models/bankvn/sft/bankvn-smoke6-router-refine1/final`: 360 steps/120 epochs, runtime 78.43 giây, 4.59 step/s, `train_loss=0.0572493`, CUDA peak allocated 4.93 GB / reserved 5.25 GB.
- HF framing probe đạt 2/2 target tool-call chính xác cho `tra_ho_so_khach` và `tra_thong_tin_san_pham`.
- Các candidate GGUF v2–v9 được dùng để chẩn đoán lỗi tokenizer/Ollama. Root cause cuối cùng: llama.cpp định nghĩa `_create_vocab_sentencepiece` ở `TextModel`; patch cũ vào `ModelBase` bị method của `TextModel` che mất, làm marker USER_DEFINED bị rơi về NORMAL/CONTROL.
- v10 sửa đúng `TextModel`: GGUF có `bankvn_end/system/user/assistant/tool_call/tool_result` tại ID 3–8 đều `token_type=4 (USER_DEFINED)`, trong khi BOS/EOS/UNK/PAD giữ `2/3/1/0`.
- Raw Ollama v10: câu dư nợ `prompt_eval_count=1196`, 42 output token, 552.41 tok/s; câu lãi suất `prompt_eval_count=1195`, 79 output token, 571.88 tok/s. Cả hai đều sinh đúng `<|bankvn_tool_call|>` và JSON target. Lần gọi đầu cold-start ~2015 ms; lượt kế tiếp ~163 ms.
- Live backend E2E v10: dư nợ 342.44 ms, lãi suất 411.08 ms; exact tool-call 2/2, schema nằm trong system prompt, BankVN không gửi native tools, marker không lộ ra output người dùng, prompt token accounting có dữ liệu.
- Tool thật: `tra_ho_so_khach` trả `Dư nợ hiện tại: 142.500.000 đồng.`; `tra_thong_tin_san_pham` đi qua RAG và trả fallback an toàn khi smoke data không có mục phù hợp.
- Qwen3.5-9B regression vẫn gửi native tools và gọi đúng `tra_ho_so_khach`; lượt đo E2E khoảng 4023.86 ms.
- Windows regression `tests/test_bankvn.py`: 12/12 PASS trong 4.07 giây.
- `export_ollama.py` hiện mặc định dùng `training/bankvn/convert_hf_to_gguf_bankvn.py`, `temperature=0.0`, và tự đọc GGUF để bắt buộc marker ID 3–8 là `USER_DEFINED`; export v11 qua đường chuẩn đã PASS metadata gate.
- Không dùng `--set-env` trong các smoke trên; production `.env` và model mặc định chưa bị đổi.

### Mốc A — khóa định dạng tokenizer và checkpoint

1. Sửa bước lưu checkpoint để copy `tokenizer.model` và `tokenizer.vocab` vào thư mục `final` cùng `tokenizer.json`.
2. Thêm kiểm tra tự động: thiếu một trong bốn file tokenizer thì dừng trước khi train/export.
3. Chạy lại tokenizer sanity trên checkpoint final, không chỉ trên thư mục tokenizer gốc.

Nghiệm thu:

- Bốn file tokenizer đều có trong checkpoint final.
- 9 special token giữ đúng ID 0–8.
- Ba câu smoke tiếng Việt decode không xuất hiện ký tự lỗi `�`.

Cái giá: checkpoint có thêm file nguồn SentencePiece, nhưng đổi lại GGUF có đủ metadata để converter nhận đúng tokenizer.

### Mốc B — SFT smoke và dữ liệu teacher

1. Đọc `data/bankvn/smoke/teacher.jsonl` bằng Python UTF-8 để phân biệt lỗi hiển thị PowerShell với lỗi dữ liệu thật.
2. Kiểm tra mỗi mẫu có `source_id`, hội thoại hợp lệ, PII đã che và tên function thuộc danh sách backend.
3. Chạy full SFT một mẫu từ checkpoint SentencePiece mới, 1 epoch, batch 1.
4. Kiểm tra loss hữu hạn, checkpoint mở lại được và tokenizer vẫn giữ đúng ID.
5. Tạo thêm bộ smoke gồm câu trả lời thường và ít nhất hai mẫu gọi hàm thật: `tra_ho_so_khach`, `tra_thong_tin_san_pham`.

Nghiệm thu:

- SFT kết thúc không lỗi CUDA/OOM/NaN.
- Loss chỉ tính trên phần assistant/tool-call; system, user và tool result bị mask `-100`.
- Tool-call target đúng JSON và đúng marker BankVN.

Cái giá: một mẫu chỉ chứng minh pipeline chạy; nó chưa chứng minh model đã biết trả lời hay gọi hàm chính xác.

### Mốc C — chuyển GGUF và chạy Ollama

1. Dùng `training/bankvn/convert_hf_to_gguf_bankvn.py` (được `export_ollama.py` gọi mặc định) để chuyển checkpoint SFT mới sang GGUF F16 và giữ nguyên semantics USER_DEFINED của tokenizer SentencePiece.
2. Kiểm tra file GGUF khác rỗng và converter không báo lỗi pre-tokenizer.
3. Tạo model `bankvn-smoke` trong Ollama từ file GGUF; không dùng cách import trực tiếp thư mục safetensors từng lỗi MLX.
4. Không sửa `OLLAMA_MODEL` trong `.env` ở mốc smoke.
5. Thử ba nhóm prompt: câu tiếng Việt thường, câu yêu cầu dữ kiện ngân hàng và câu cần gọi function.

Nghiệm thu:

- Ollama nạp model và sinh được token.
- Model dừng ở `<|bankvn_end|>`.
- Phản hồi không có ký tự hỏng do tokenizer.
- Function call có thể được parser backend đọc thành `{name, arguments}`.

Kết quả hiện tại: **Đạt** với v10; v11 export lại bằng đường chuẩn cũng qua metadata gate.

Cái giá: GGUF F16 lớn hơn bản quantized; ưu tiên F16 ở smoke để tách lỗi chuyển đổi khỏi sai số lượng tử. Sau khi đúng mới tạo Q8/Q6/Q4 để đo tốc độ và VRAM.

### Mốc D — kiểm thử tích hợp VoiceBank

1. Thêm test cho `_doc_bankvn_tool_calls`: JSON đơn, danh sách, JSON lỗi, thiếu marker và arguments không phải object.
2. Xác minh model BankVN được chèn schema tool vào system prompt và không truyền `tools=` native sang Ollama.
3. Xác minh model Qwen hiện tại vẫn đi native tool calling như trước.
4. Chạy backend với `bankvn-smoke` bằng cấu hình tạm thời cho phiên test; không đổi production mặc định.
5. Chạy một luồng hỏi sản phẩm và một luồng tra hồ sơ qua backend thật.

Nghiệm thu:

- BankVN gọi đúng function trên bộ smoke.
- Qwen regression test vẫn gọi function native thành công.
- Không lộ marker `<|bankvn_tool_call|>` ra giao diện người dùng.
- Token accounting và kiểm tra cửa sổ ngữ cảnh vẫn chạy ở chunk cuối.

Kết quả hiện tại: **Đạt toàn bộ** trên Windows với `bankvn-smoke6-router-v10-sp-types`; Qwen regression cũng đạt.

Cái giá: BankVN phải buffer toàn bộ lượt có tool trước khi trả; TTFT của lượt tool sẽ cao hơn streaming chữ thường. Đây là chấp nhận được ở giai đoạn đầu để parser chắc chắn.

### Mốc D2 — router production nhanh và ổn định

Hướng router generative sinh JSON/tool name trực tiếp đã dừng vì candidate nhỏ có thể regression nặng dù loss đẹp. Production hiện dùng ba tầng: regex deterministic cho intent chắc chắn, classifier Naive Bayes 3 lớp (`profile`, `product`, `assistant`) cho vùng còn lại, rồi mới fallback sang Qwen3.5-9B khi hai tầng đầu chưa đủ chắc chắn. Backend render tool-call deterministic nên classifier không phải tự sinh JSON hay tên hàm.

Classifier hiện dùng char n-gram 2–5, word unigram/bigram, ngưỡng confidence `0.62` và margin `1.5`. Runtime model là `models/bankvn/router/router_nb_current.json`; production không import code trong `training/`. Qwen3.5-9B vẫn là answer model/teacher và model production không bị đổi.

Kết quả gate hiện tại:

- clean40: domain accuracy 100%, tool-call accuracy 100%, no-tool accuracy 100%, hallucination 0%, p95 khoảng 0.025 ms.
- holdout cố định 90 mẫu cân bằng 30/30/30: 90/90 đúng, hallucination 0%; Windows p95 khoảng 0.251 ms, Mac khoảng 0.318 ms.
- `tests/test_bankvn.py` trên Windows: 29/29 pass sau khi tích hợp runtime classifier.
- Backend Windows sau restart trả HTTP 200; log xác nhận WebSocket nhận kết nối và LLM đã warm.

Holdout cố định nằm ở `training/bankvn/bench/router_holdout_v1.jsonl` và không được đưa vào train. `continuous.py` chấm cả candidate lẫn current trên cùng holdout; candidate phải đạt floor tuyệt đối và không được kém current về domain accuracy, tool-call accuracy, no-tool accuracy, hallucination và p95 latency. Candidate chỉ được ghi trạng thái để xem xét, không tự promote.

### Mốc E — chuẩn bị dữ liệu train thật

1. Nạp nguồn tiếng Việt hợp pháp và dữ liệu nội bộ đã loại PII vào `data/bankvn/raw`.
2. Gắn metadata nguồn, loại trùng theo hash và chia train/validation/test theo nguồn để tránh rò dữ liệu.
3. Giữ riêng bộ Excel 10k làm benchmark; không đưa câu benchmark nguyên văn vào train.
4. Teacher Qwen3.5-9B tạo SFT tiếng Việt theo từng `source_id`; validator loại JSON lỗi, function lạ, chữ CJK/Hangul và PII.
5. Lấy mẫu ngẫu nhiên để người kiểm tra trước mỗi đợt train dài.

Nghiệm thu:

- Tỷ lệ dòng CJK/Hangul sau lọc bằng 0 trên corpus được duyệt.
- Không có hash trùng giữa train và benchmark.
- 100% mẫu tool-call dùng function có thật trong backend.
- Báo cáo được số document, số token, tỷ lệ bị loại, lý do bị loại và nguồn dữ liệu.

Cái giá: lọc mạnh làm giảm lượng data, nhưng data sạch quan trọng hơn số lượng thô với model nhỏ chuyên ngành.

### Mốc F — pretrain dài BankVN-350M

1. Chạy thử 100 bước để kiểm tra loss, tốc độ, checkpoint và resume.
2. Resume thêm 500 bước; xác minh step tăng tiếp thay vì train lại từ đầu.
3. Khi hai lần trên ổn, chạy `run_forever.ps1` theo chu kỳ 500 bước.
4. Mỗi chu kỳ lưu tối đa hai checkpoint gần nhất, trạng thái vào `data/bankvn/state/continuous.json` và log riêng.
5. Nếu VRAM trống dưới 7,000 MB, cycle bỏ qua và thử lại sau; không tranh GPU với dịch vụ đang phục vụ người dùng.
6. Khi teacher sinh data, dừng teacher trước khi student train để giải phóng VRAM.

Nghiệm thu:

- 100 bước và 500 bước đều không OOM/NaN.
- Resume đúng global step.
- Loss trung bình theo cửa sổ 50 bước được ghi lại; không yêu cầu giảm ở từng bước đơn lẻ.
- Dừng và khởi động lại Windows không làm mất checkpoint hợp lệ.
- Lock ngăn được hai vòng continuous chạy đồng thời.

Kết quả hiện tại: **đã đạt phần smoke 100 + resume 500** đến step 600 và xác minh đủ state resume. Chưa bật `run_forever.ps1`; bước này chờ Mốc E/G có corpus thật và benchmark/gate đầy đủ.

Cái giá: một RTX 5070 12 GB sẽ cần thời gian dài để đạt số token đủ lớn. Chạy 24/7 không thay thế được chất lượng corpus hoặc giới hạn năng lực của model 350M.

### Mốc G — benchmark, promotion và rollback

1. Chấm candidate và baseline trên cùng bộ Excel 10k và bộ tool-call cố định.
2. Ghi riêng độ đúng nghiệp vụ, tool-call accuracy, tỷ lệ câu thuần Việt, tỷ lệ chữ ngoại ngữ, hallucination, latency và VRAM.
3. Candidate không đạt bất kỳ gate bắt buộc nào thì giữ trạng thái `pending_benchmark` hoặc `rejected`.
4. Chỉ sau khi đạt gate mới tạo model candidate ổn định; việc đổi `.env` là bước riêng, có bản baseline để rollback.
5. Với router classifier, luôn benchmark candidate và `router_nb_current.json` trên holdout cố định; candidate regression ở bất kỳ metric bắt buộc nào thì reject.
6. Không auto-promote router hoặc đổi `OLLAMA_MODEL`; promotion luôn là bước riêng sau gate.

Gate tối thiểu trước khi cân nhắc production:

- Tool-call accuracy đạt 100% trên bộ function smoke bắt buộc.
- Không có CJK/Hangul trong đầu ra benchmark.
- Không giảm độ đúng nghiệp vụ so với baseline hiện tại.
- Hallucination không cao hơn baseline.
- Không có lỗi backend/tool parser mới trong test regression.

Cái giá: gate nghiêm có thể giữ model ở trạng thái candidate lâu hơn, nhưng tránh một checkpoint loss đẹp làm hỏng nghiệp vụ thật.

### Mốc H — quyết định scale 1.3B và 3.2B

Chỉ mở mốc 1.3B sau khi 350M hoàn thành toàn bộ Mốc A–G. Trước khi scale phải đo tokens/giây, thời gian dự kiến cho một tỷ token, peak VRAM, RAM và dung lượng checkpoint. Profile 3.2B chỉ chạy khi có phương án offload/multi-GPU hoặc GPU lớn hơn được đo thực tế.

Cái giá: 1.3B và 3.2B tăng năng lực nhưng làm chậm train, tăng checkpoint và có thể không vừa 12 GB cho full training. Không tự bật `--allow-large` chỉ để vượt chặn cấu hình.

### Thứ tự thực hiện gần nhất

1. Giữ router production hiện tại làm baseline và mở rộng holdout bằng dữ liệu tiếng Việt mới đã lọc semantic; tuyệt đối không trộn holdout vào train.
2. Chạy một vài cycle continual hữu hạn, chấm candidate so với current sau mỗi cycle và lưu report/gate.
3. Chuẩn bị corpus thật theo Mốc E, thống kê nguồn/số token/tỷ lệ bị loại và khóa benchmark khỏi train.
4. Chạy benchmark Excel 10k + bộ tool-call cố định cho baseline và candidate.
5. Chỉ sau nhiều cycle hữu hạn không regression mới cân nhắc bật `run_forever.ps1`; vẫn giữ cơ chế nhường GPU và không auto-promote.
6. Không đổi production `.env` hoặc `OLLAMA_MODEL` cho tới khi candidate vượt toàn bộ gate promotion.

## 5. Chỗ tôi hiểu khác lời bạn nói

- “Cho nó học 24/24” được triển khai thành worker học theo chu kỳ có checkpoint và gate, không phải để model tự sửa trọng số sau mỗi câu khách hỏi.
- “Chỉ cần tiếng Việt” không loại các mã và thuật ngữ ngân hàng quốc tế cần thiết cho nghiệp vụ và function calling.
- “Thông minh như 9B” là mục tiêu chất lượng trong miền ngân hàng tiếng Việt; kế hoạch không cam kết model 350M có năng lực tổng quát bằng model 9B.
- Bản đầu chưa được bật làm model chính. Nó phải đi hết smoke, GGUF, Ollama, tích hợp và benchmark trước.

## 6. Phải chốt trước khi làm tiếp

Không có quyết định nào cần chốt để hoàn thành các mốc A–D và smoke 100/500 bước.

Trước khi bắt đầu pretrain dài hoặc scale lên 1.3B cần chốt riêng ngân sách điện/thời gian GPU, danh sách nguồn dữ liệu được phép sử dụng và việc máy Windows có được ưu tiên train khi VoiceBank đang phục vụ thật hay không. Cho tới lúc đó, worker mặc định nhường GPU khi VRAM trống dưới 7,000 MB và tuyệt đối không tự đổi model production.
