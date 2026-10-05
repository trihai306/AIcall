# Thiết kế BankVN từ số 0

## 1. Việc cần làm
Tạo một LLM ngân hàng ưu tiên tiếng Việt, khởi tạo trọng số và tokenizer từ số 0, có vòng học liên tục từ corpus Việt + dữ liệu teacher, giữ được function calling của hệ thống và chỉ được đưa lên production khi vượt benchmark hiện tại.

## 2. Đọc được từ dự án
- `README.md`: máy production nhắm RTX 5070 12GB; LLM, STT và TTS cùng chia VRAM.
- `training/llm/train_lora.py`: trainer hiện tại là QLoRA cho Qwen2.5, không phải pretraining từ số 0.
- `backend/services/llm_service.py`: backend đã nhận `tools` từ Ollama và đọc `message.tool_calls`.
- `backend/pipeline/cong_cu_llm.py`: hệ thống hiện có ít nhất `tra_ho_so_khach` và `tra_thong_tin_san_pham`.
- `scripts/bo_thu_10k_tai_lieu.py` + Excel 10k hiện có: đã có benchmark nghiệp vụ để làm promotion gate.
- `models/llm/Modelfile.tuvan-qwen`: template fine-tune cũ đã bỏ tool-calling, nên không được tái sử dụng nguyên trạng cho BankVN.

## 3. Giả định tôi chốt thay bạn
- BankVN “thuần Việt” nghĩa là corpus huấn luyện được lọc tiếng Việt rất mạnh nhưng vẫn giữ thuật ngữ nghiệp vụ như API, ATM, OTP, KYC, CIC, Visa, JSON · nếu muốn cấm tuyệt đối mọi token ngoại ngữ thì phải đổi bộ lọc và chấp nhận hỏng nhiều thuật ngữ thực tế.
- Qwen3.5-9B chỉ làm teacher sinh/chấm dữ liệu; BankVN không nạp trọng số hoặc tokenizer của Qwen · nếu không muốn teacher Qwen tham gia thì phải thay bằng dữ liệu người chấm, tốc độ tạo data sẽ giảm mạnh.
- Bản đầu dùng kiến trúc decoder-only chuẩn Transformers với trọng số random và tokenizer tự train từ corpus Việt · nếu bắt buộc tự viết cả kiến trúc transformer mới thì phải tách thành dự án nghiên cứu khác.
- RTX 5070 12GB là GPU train chính · vì vậy mốc đầu là 350M; 1.3B là mốc scale tiếp theo; 3B+ chỉ chạy khi đo VRAM cho thấy ổn hoặc có CPU/offload/multi-GPU.
- Không train trực tiếp trên mọi câu production chưa kiểm duyệt · dữ liệu mới phải qua lọc, dedupe, teacher/chấm và benchmark gate để tránh model tự học lỗi.
- Không tự chuyển production sau một checkpoint tốt hơn trên loss · promotion cần đạt gate nghiệp vụ, tool calling, tiếng Việt và không hồi quy so với baseline.

## 4. Cách làm và cái giá

### Hướng chọn: from-scratch + teacher distillation
1. `prepare_corpus.py`: nhận `.txt/.jsonl/.md`, chuẩn hóa Unicode, lọc tỷ lệ tiếng Việt, loại CJK/Hangul, dedupe theo hash, ghi corpus sạch.
2. `train_tokenizer.py`: train tokenizer BPE riêng cho tiếng Việt và thêm special tokens cho chat/tool call.
3. `pretrain.py`: khởi tạo model random từ config BankVN, causal-LM pretraining theo token budget, checkpoint định kỳ và resume được.
4. `teacher_generate.py`: dùng Qwen3.5-9B qua Ollama để tạo/sửa mẫu hội thoại ngân hàng tiếng Việt và mẫu function calling; teacher output phải qua validator trước khi nhập dataset.
5. `sft.py`: SFT BankVN trên hội thoại + tool-calling sau giai đoạn pretrain.
6. `continuous.py`: chạy một chu kỳ data → teacher → train → eval → promote/rollback; có lock để không chạy hai trainer cùng lúc.
7. `gate.py`: so checkpoint mới với baseline theo các số đo bắt buộc, không chỉ nhìn loss.

### So sánh phương án
| Phương án | Ưu điểm | Cái giá |
|---|---|---|
| Train 3B/4B từ số 0 ngay | Đúng mục tiêu cuối nhanh về mặt kiến trúc | Không phù hợp RTX 5070 12GB cho full pretraining; rất chậm hoặc phải offload nặng |
| Fine-tune Qwen3.5-4B | Nhanh đạt chất lượng cao | Vẫn kế thừa tokenizer/trọng số đa ngôn ngữ, không đúng yêu cầu “từ số 0” |
| **BankVN-350M → 1.3B → 3B** | Kiểm chứng được corpus/tokenizer/training loop trên đúng phần cứng, không mang trọng số Qwen | Cần nhiều token và nhiều vòng distillation; 350M không thể có năng lực tổng quát ngang 9B |

### Mốc nghiệm thu
- M0: corpus filter giữ tiếng Việt, loại CJK/Hangul, dedupe ổn định trên fixture test.
- M1: tokenizer BankVN encode/decode đúng tiếng Việt và special tokens tool-call.
- M2: BankVN-350M random-init train được, save/resume checkpoint và loss giảm trên smoke corpus.
- M3: SFT tạo được đúng protocol tool-call trên bộ test nhỏ.
- M4: candidate chạy qua benchmark nghiệp vụ; chỉ promote khi không hồi quy các gate bắt buộc.
- M5: scale lên 1.3B sau khi M0–M4 ổn; 3B chỉ sau khi đo VRAM/throughput thực tế.

## 5. Chỗ tôi hiểu khác lời bạn nói
“Thông minh như 9B” được hiểu là tiến tới ngang hoặc hơn Qwen3.5-9B **trong miền nghiệp vụ ngân hàng tiếng Việt của hệ thống**, không phải ngang 9B ở mọi kiến thức tổng quát. Một model nhỏ train 24/24 không tự vượt giới hạn capacity chỉ nhờ thời gian.

“Học 24/24” được triển khai thành các chu kỳ có checkpoint, đánh giá và rollback; không cho model tự học trực tiếp từ câu trả lời của chính nó sau từng cuộc gọi.

## 6. Phải chốt trước khi làm tiếp
Không có. Các quyết định trên đủ để dựng mốc M0–M3 mà không đụng production hiện tại; việc scale 1.3B/3B sẽ dựa trên số đo VRAM và benchmark sau mốc đầu.
