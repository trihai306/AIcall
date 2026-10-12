"""Lời dặn thêm cho mô hình ở ĐÚNG MỘT kiểu lượt: lời khách rất ngắn mà không luật, không kho nào nhận.

Bộ thử 156 lượt (12-10-2026), hai lượt máy nghe sai thành lời vô nghĩa ("cũng
như nào", "sâu giờ bấy nhiêu"): chạy nhiều lần thì khoảng một nửa số lần mô hình
hỏi lại ý khách (đúng), nửa còn lại nó hỏi sang thu nhập hoặc tự gán "khoản vay
400 triệu trong 16 tháng". Không có cách nhận ra lời vô nghĩa bằng chữ mà không
bắt nhầm câu ngắn hợp lệ ("thế à", "vậy cũng được"), nên không chặn bằng luật;
chỉ dặn mô hình cách xử trí khi chính nó không chắc.
"""

import re

SO_TU_TOI_DA = 4

LOI_DAN = (
    "\n\nLƯU Ý CHO LƯỢT NÀY: lời khách rất ngắn và có thể bị máy nghe sai. Nếu hiểu rõ "
    "khách muốn gì thì trả lời bình thường. Nếu KHÔNG chắc khách đang hỏi gì thì chỉ nói "
    "một câu xin khách nói lại, ví dụ: \"Dạ em nghe chưa rõ ạ, anh chị nói lại giúp em "
    "được không ạ?\". Không hỏi thu nhập, không hỏi hồ sơ, không tự đoán số tiền hay "
    "thời hạn khi chưa hiểu câu hỏi.")


def loi_dan_luot_ngan(loi_khach: str) -> str:
    """`LOI_DAN` khi lời khách không quá `SO_TU_TOI_DA` từ, ngược lại chuỗi rỗng."""
    tu = re.findall(r"\w+", loi_khach or "")
    return LOI_DAN if 0 < len(tu) <= SO_TU_TOI_DA else ""
