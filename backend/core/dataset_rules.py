"""Luật kiểm tra dataset train, lấy thẳng từ system prompt lúc chạy thật.

Vì sao cần: model học theo data, không học theo system prompt. Nếu data dạy
kiểu trả lời dài dòng, liệt kê, dùng chữ số - thì fine-tune xong model sẽ nói
đúng như thế, và system prompt có ép cỡ nào cũng thua. Bộ dataset mẫu ban đầu
của dự án chính là ví dụ: 34-38 từ, chữ số, liệt kê ba dòng thẻ - trong khi
system prompt yêu cầu tối đa 25 từ và viết số thành chữ.

Cái nguy hiểm là lỗi đó KHÔNG có gì báo. Train vẫn chạy, model vẫn trả lời
tiếng Việt, chỉ là trả lời sai phong cách - và chỉ phát hiện được khi nghe
cuộc gọi thật.

Nguồn luật: SYSTEM_PROMPT_TEMPLATE trong backend/services/llm_service.py.
Sửa luật ở đó thì phải sửa ở đây.
"""

import re

GIOI_HAN_TU = 25      # quy tắc 2: "TỐI ĐA 25 từ"
GIOI_HAN_CAU = 2      # quy tắc 2: "TỐI ĐA 2 câu"

_CHU_SO = re.compile(r"\d")
_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
# Gạch đầu dòng / đánh số đầu dòng - quy tắc 6 cấm markdown, quy tắc 9 cấm liệt kê.
_GACH_DAU_DONG = re.compile(r"(^|\n)\s*([-*•+]|\d+[.)])\s")
_MARKDOWN = re.compile(r"\*\*|__|`|^#{1,6}\s", re.MULTILINE)
_TACH_CAU = re.compile(r"[.?!]+")


def dem_tu(text: str) -> int:
    return len(text.split())


def dem_cau(text: str) -> int:
    return len([c for c in _TACH_CAU.split(text) if c.strip()])


def kiem_tra_tra_loi(text: str) -> tuple[list[str], list[str]]:
    """Soi một câu trả lời của tư vấn viên.

    Trả về (loi, canh_bao):
      - loi     : vi phạm quy tắc ghi rõ trong system prompt, train vào là hỏng
      - canh_bao: lệch thói quen của giọng tư vấn, vẫn train được
    """
    loi: list[str] = []
    canh_bao: list[str] = []
    t = (text or "").strip()

    if not t:
        return ["câu trả lời rỗng"], []

    n_tu, n_cau = dem_tu(t), dem_cau(t)
    if n_tu > GIOI_HAN_TU:
        loi.append(f"{n_tu} từ (tối đa {GIOI_HAN_TU})")
    if n_cau > GIOI_HAN_CAU:
        loi.append(f"{n_cau} câu (tối đa {GIOI_HAN_CAU})")
    if _CHU_SO.search(t):
        loi.append("còn chữ số - phải viết thành chữ, ví dụ 6.5% -> sáu phẩy năm phần trăm")
    if _EMOJI.search(t):
        loi.append("có emoji")
    if _GACH_DAU_DONG.search(t):
        loi.append("có gạch đầu dòng - qua điện thoại không ai nghe được danh sách")
    if _MARKDOWN.search(t):
        loi.append("có ký hiệu markdown")

    thap = t.lower()
    if "ạ" not in thap:
        canh_bao.append("thiếu chữ 'ạ' cuối câu")
    if not thap.startswith("dạ"):
        canh_bao.append("không mở đầu bằng 'Dạ'")
    if not re.search(r"\bem\b", thap):
        canh_bao.append("không xưng 'em'")

    return loi, canh_bao


def kiem_tra_cap(cap: list[tuple[str, str]], dong_dau: int = 2) -> dict:
    """Soi cả danh sách (câu khách hỏi, câu tư vấn trả lời).

    dong_dau: số dòng của cặp đầu tiên trong file gốc, để báo lỗi đúng dòng
    người dùng nhìn thấy trong Excel (mặc định 2 vì dòng 1 là tiêu đề).
    """
    chi_tiet = []
    so_loi = so_canh_bao = 0

    for i, (hoi, tra_loi) in enumerate(cap):
        loi, canh_bao = kiem_tra_tra_loi(tra_loi)
        if not (hoi or "").strip():
            loi.insert(0, "thiếu câu khách hỏi")
        if loi or canh_bao:
            chi_tiet.append({
                "dong": dong_dau + i,
                "khach_hoi": (hoi or "")[:80],
                "tra_loi": (tra_loi or "")[:120],
                "loi": loi,
                "canh_bao": canh_bao,
            })
        so_loi += bool(loi)
        so_canh_bao += bool(canh_bao) and not loi

    return {
        "tong": len(cap),
        "dat": len(cap) - so_loi,
        "so_dong_loi": so_loi,
        "so_dong_canh_bao": so_canh_bao,
        "chi_tiet": chi_tiet[:50],   # đủ để sửa, không làm ngập giao diện
        "con_nua": max(0, len(chi_tiet) - 50),
    }
