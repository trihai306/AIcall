"""Luật chọn câu đệm. Thuần logic, KHÔNG import torch - xem filler_store."""
import random

# Câu dài hơn mức cần bao nhiêu thì vẫn coi là "vừa khít". Quá số này thì nó
# đẩy câu trả lời thật lùi lại một cách vô ích.
NOI_RONG_MS = 800.0


def can_che_ms(lich_su: list[dict], la_thoai: bool, mac_dinh: float) -> float:
    """Câu đệm phải dài ít nhất bằng độ trễ gần đây của CHÍNH đường này.

    Ngắn hơn thì khách nghe hụt đúng phần thiếu; dài quá thì câu trả lời thật bị
    đẩy ra sau một cách vô ích.

    BỎ những lượt trả lời bằng bảng câu sẵn (`luot_thuong_gap`). Chúng không gọi
    LLM nên nhanh có cấu trúc, và dùng chúng để đoán cho lượt phải gọi LLM là
    đoán trượt. Đo thật 08-08: hai lượt câu sẵn 450/458ms làm hệ thống tưởng
    đường đang nhanh nên BỎ câu đệm, rồi lượt 3 phải gọi LLM mất 3399ms - khách
    nghe im lặng 3,4 giây, đúng thứ câu đệm sinh ra để chặn.

    Tách thoại/chat vì hai đường chênh nhau đúng phần STT. Ưu tiên khoá
    `la_thoai` ghi thẳng; bản ghi cũ không có khoá đó thì suy từ `stt_ms` như
    trước - lưu ý cách suy này SAI ở những lượt dùng lại bản phiên âm đoán trước
    (stt_ms = 0), đó là lý do có khoá tường minh.
    """
    def dung_duong(m: dict) -> bool:
        if "la_thoai" in m:
            return bool(m["la_thoai"]) == la_thoai
        return bool(m.get("stt_ms")) == la_thoai

    qua = [m["ttfa_ms"] for m in lich_su[-6:]
           if m.get("ttfa_ms") and not m.get("luot_thuong_gap") and dung_duong(m)]
    return float(max(qua[-3:])) if qua else mac_dinh


def chon(ung_vien: list[tuple[str, float]], min_ms: float,
         dem: dict[str, int], rng: random.Random | None = None) -> str | None:
    """Chọn một câu đệm trong `ung_vien` = [(id, độ dài ms)].

    Ba tầng, rơi dần:
      1. Vừa khít: độ dài trong [min_ms, min_ms + NOI_RONG_MS]
      2. Đủ dài: độ dài >= min_ms
      3. Không câu nào đủ -> câu DÀI NHẤT (làm quãng lặng ngắn nhất có thể)

    Trong mỗi tầng, chỉ xét nhóm có SỐ ĐẾM NHỎ NHẤT rồi bốc ngẫu nhiên trong
    đó. Nhờ vậy nhóm 10 câu bảo đảm dùng hết 10 câu mới lặp lại câu đầu - chắc
    chắn, không phải xác suất như cách "tránh 3 câu vừa dùng" trước đây.
    """
    if not ung_vien:
        return None
    r = rng or random.Random()

    def it_dung_nhat(nhom: list[tuple[str, float]]) -> list[tuple[str, float]]:
        thap_nhat = min(dem.get(cid, 0) for cid, _ in nhom)
        return [(cid, ms) for cid, ms in nhom if dem.get(cid, 0) == thap_nhat]

    vua_khit = [x for x in ung_vien if min_ms <= x[1] <= min_ms + NOI_RONG_MS]
    if vua_khit:
        return r.choice(it_dung_nhat(vua_khit))[0]

    du_dai = [x for x in ung_vien if x[1] >= min_ms]
    if du_dai:
        return r.choice(it_dung_nhat(du_dai))[0]

    return max(it_dung_nhat(ung_vien), key=lambda x: x[1])[0]
