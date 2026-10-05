# BankVN

BankVN là pipeline LLM ngân hàng tiếng Việt train từ trọng số ngẫu nhiên và tokenizer riêng.
Qwen3.5 chỉ làm teacher tạo/chấm dữ liệu SFT, không cung cấp trọng số hay tokenizer.

Production không tự đổi model. Checkpoint mới luôn là candidate cho tới khi qua benchmark gate.
