"""Cửa sổ nhớ của mô hình: còn bao nhiêu chỗ cho hội thoại, và khi nào phải kêu.

KHÔNG import torch/ollama - luật nằm ở đây để test được trên máy không GPU,
giống `filler_pick`.

VÌ SAO CÓ TỆP NÀY. Ollama nhận `num_ctx`; hội thoại dài quá thì nó CẮT BỎ phần
đầu và KHÔNG báo gì - log vẫn sạch, không lỗi nào ném ra. Triệu chứng người
dùng thấy là "nói chuyện một lúc thì bot quên", rất dễ đổ oan cho lịch sử không
được lưu (lịch sử vẫn được gửi đủ; chính cửa sổ mới là chỗ hụt).

ĐO THẬT 2026-09-02, máy Windows, qwen2.5:7b, đọc `prompt_eval_count` của Ollama:

    lời dặn hệ thống, không tri thức     1053 token
    lời dặn + tri thức tra được (top_k=2) 1414 token   <- 69% của num_ctx=2048
    chừa cho câu trả lời (max_tokens)      150 token
    còn lại cho hội thoại                  484 token   -> ~6 lượt
"""

# Token trung bình của MỘT lượt hỏi-đáp, đo trên lượt thật của dự án.
TOKEN_MOI_LUOT = 75

# Số lượt một cuộc tư vấn thật cần nhớ. Không phải con số kỹ thuật - đây là
# nghiệp vụ: khách hỏi lãi ở lượt 3 rồi chê ở lượt 15 thì bot phải còn nhớ.
LUOT_CAN_TOI_THIEU = 20


def con_cho_hoi_thoai(prompt_tokens: int, num_ctx: int, max_tokens: int) -> int:
    """Token còn lại cho lịch sử, sau khi trừ CẢ lời dặn LẪN chỗ chừa cho câu
    trả lời sắp sinh ra.

    Quên trừ `max_tokens` là báo dư đúng bằng nó - mô hình vẫn tràn trong khi
    phép đo bảo còn chỗ.
    """
    return max(0, num_ctx - prompt_tokens - max_tokens)


def canh_bao_tran(prompt_tokens: int, num_ctx: int, max_tokens: int) -> str | None:
    """Lời cảnh báo nếu cửa sổ không đủ cho một cuộc tư vấn thật, None nếu đủ.

    Đo bằng SỐ LƯỢT chứa được, không bằng phần trăm cửa sổ đã dùng: cấu hình
    hỏng thật (1414 + 150 trên 2048) mới chiếm 76%, mọi ngưỡng phần trăm quanh
    85% đều cho nó lọt - trong khi nó chỉ nhớ nổi 6 lượt.
    """
    con = con_cho_hoi_thoai(prompt_tokens, num_ctx, max_tokens)
    so_luot = con // TOKEN_MOI_LUOT
    if so_luot >= LUOT_CAN_TOI_THIEU:
        return None
    return (f"Cửa sổ nhớ chỉ còn {con} token cho hội thoại (~{so_luot} lượt); "
            f"cuộc tư vấn cần {LUOT_CAN_TOI_THIEU} lượt. Ollama sẽ CẮT BỎ phần "
            f"đầu hội thoại mà không báo - bot quên dần. Nới LLM_NUM_CTX "
            f"(đang {num_ctx}) hoặc rút ngắn lời dặn (đang {prompt_tokens} token).")


def doc_so_token(chunk) -> int | None:
    """Số token THẬT của lời dặn + lịch sử, đọc từ chunk cuối của Ollama.

    Ollama gắn `prompt_eval_count` vào chunk `done`. Có sẵn, không tốn gì, và
    chính xác hơn mọi cách ước lượng theo ký tự - tỷ lệ ký tự/token của tiếng
    Việt lệch nhau tới 40% giữa lời dặn (2.6) và lời thoại (1.8).

    Trả None khi chưa tới chunk cuối hoặc bản Ollama không có trường này.
    Không ném lỗi: đây là phép đo phụ, hỏng nó không được làm hỏng lượt của khách.
    """
    if isinstance(chunk, dict):
        n = chunk.get("prompt_eval_count")
    else:
        n = getattr(chunk, "prompt_eval_count", None)
    return n if isinstance(n, int) and n > 0 else None
