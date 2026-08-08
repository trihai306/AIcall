"""Luật chọn câu đệm. Thuần logic, KHÔNG import torch - xem filler_store."""
import random

# Câu dài hơn mức cần bao nhiêu thì vẫn coi là "vừa khít". Quá số này thì nó
# đẩy câu trả lời thật lùi lại một cách vô ích.
NOI_RONG_MS = 800.0


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
