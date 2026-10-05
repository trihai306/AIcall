"""One conversational target shared by inference and fine-tuning preparation."""

import re

STYLE_GUIDE = """VĂN PHONG CUỘC GỌI:
- Nghe và đáp đúng ý vừa hỏi; dùng dữ kiện khách đã nói, không mở đầu lại kịch bản.
- Nói như một nhân viên đang trò chuyện: từ ngữ đời thường, nhịp ngắn, không đọc lại tài liệu hay lặp 'theo thông tin' ở mọi lượt.
- Nếu đã đủ căn cứ thì trả lời rõ. Nếu thiếu đúng một dữ kiện quyết định, hỏi đúng dữ kiện đó; không hỏi cho có.
- Khi khách lo lắng hoặc phản đối, ghi nhận ngắn rồi giải thích phần có căn cứ; không nịnh, không hứa duyệt hồ sơ.
- Không lặp 'Dạ' hay lời chào nếu câu đệm của cùng lượt đã nói rồi.
- Giữ xưng hô nhất quán và chỉ kết thúc khi khách muốn dừng."""
STYLE_GUIDE += (
    "\n- Ưu tiên tiếng Việt thuần trong lời nói: 'gửi trên ứng dụng', 'hoàn tiền', "
    "'cập nhật'; không đọc nguyên tiếng Anh trong tài liệu như online, cashback."
    "\n- Nếu khách yêu cầu cách nói miền Bắc, miền Nam hoặc trung tính, "
    "điều chỉnh từ ngữ và nhịp nói cho phù hợp từ lượt sau; không bắt chước "
    "quá đà và không đổi dữ kiện. Chưa có yêu cầu thì dùng tiếng Việt trung tính."
)


def requested_region_note(messages: list[dict]) -> str:
    """Keep the customer's latest explicit wording preference across turns."""
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        value = str(message.get("content") or "").lower()
        if "miền bắc" in value:
            return ('KHÁCH CHỌN CÁCH NÓI MIỀN BẮC: dùng lời lịch sự tự nhiên, '
                    'có thể mở bằng "Vâng,". Không ghép "anh/chị" trực tiếp trước tên sản phẩm.')
        if "miền nam" in value:
            return ('KHÁCH CHỌN CÁCH NÓI MIỀN NAM: dùng "Dạ," và từ ngữ gần gũi '
                    'vừa phải, xưng "em". Không dùng "chúng tôi", "quý khách" hay '
                    'ghép "anh/chị" trực tiếp trước tên sản phẩm.')
        if "trung tính" in value:
            return ('KHÁCH CHỌN CÁCH NÓI TRUNG TÍNH: dùng tiếng Việt phổ thông, '
                    'lịch sự, có thể mở bằng "Dạ,". Không ghép "anh/chị" trước tên sản phẩm.')
    return ""


def requested_address_note(messages: list[dict]) -> str:
    """Honor the last explicit way the customer asks to be addressed."""
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        value = str(message.get("content") or "").lower()
        match = re.search(
            r"(?:gọi|xưng hô).{0,28}?(?:tôi|mình|em|con|cháu).{0,12}?(?:là|bằng|như)\s+"
            r"(cô|chú|bác|anh|chị|em)\b", value,
        )
        self_reference = re.search(
            r"\b(cô|chú|bác)\s+(?:muốn|hỏi|cần|định|nói|gửi|vay)\b|"
            r"\b(?:giúp|cho)\s+(cô|chú|bác)\b", value,
        )
        if match or self_reference:
            title = match.group(1) if match else (self_reference.group(1) or self_reference.group(2))
            return (f'KHÁCH YÊU CẦU XƯNG HÔ: gọi khách là "{title}" từ lượt này. '
                    'Ưu tiên yêu cầu này hơn suy đoán giới tính từ giọng; '
                    'không dùng "anh/chị" hay đại từ khác để gọi khách.')
    return ""
