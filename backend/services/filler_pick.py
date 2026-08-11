"""Luật chọn câu đệm. Thuần logic, KHÔNG import torch - xem filler_store."""
import random

# Câu dài hơn mức cần bao nhiêu thì vẫn coi là "vừa khít". Quá số này thì nó
# đẩy câu trả lời thật lùi lại một cách vô ích.
NOI_RONG_MS = 800.0


# Nhân vào độ trễ quá khứ trước khi chọn câu đệm. KHÔNG có biên thì hụt ngay khi
# lượt này chậm hơn mấy lượt trước - mà TTFA dao động rất rộng, đo được 678-1978ms
# trên cùng một kịch bản.
BIEN_AN_TOAN = 1.25


def can_che_ms(lich_su: list[dict], la_thoai: bool, mac_dinh: float) -> float:
    """Câu đệm phải dài ít nhất bằng độ trễ gần đây của CHÍNH đường này.

    Ngắn hơn thì khách nghe hụt đúng phần thiếu; dài quá thì câu trả lời thật bị
    đẩy ra sau một cách vô ích.

    BỎ những lượt trả lời bằng bảng câu sẵn (`luot_thuong_gap`). Chúng không gọi
    LLM nên nhanh có cấu trúc, và dùng chúng để đoán cho lượt phải gọi LLM là
    đoán trượt. Đo thật 08-08: hai lượt câu sẵn 450/458ms làm hệ thống tưởng
    đường đang nhanh nên BỎ câu đệm, rồi lượt 3 phải gọi LLM mất 3399ms - khách
    nghe im lặng 3,4 giây, đúng thứ câu đệm sinh ra để chặn.

    `mac_dinh` là SÀN, không phải chỉ là giá trị lùi khi thiếu lịch sử. Vài lượt
    nhanh liên tiếp kéo ước lượng xuống thấp, rồi một lượt chậm đột ngột là hụt -
    đo được đúng thế: lịch sử toàn 678ms, lượt sau 1056ms, hụt 378ms.

    Chọn số bằng cách mô phỏng trên 25 lượt thật của ba lần chạy:
        sàn 1200ms, biên 1.25 -> hụt 2/25
        sàn 1800ms, biên 1.25 -> hụt 1/25
        sàn 2000ms, biên 1.25 -> hụt 0/25,  câu đệm dài hơn cần TB 996ms
    Nghiêng hẳn về phía dài: dài quá thì khách nghe CÂU ĐỆM, ngắn quá thì khách
    nghe IM LẶNG. Hai thứ đó không cùng hạng.

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
    if not qua:
        return mac_dinh
    return max(float(max(qua[-6:])) * BIEN_AN_TOAN, mac_dinh)


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


def ghep(mo_dau: str, duoi: str) -> str:
    """Ghép mẩu mở đầu với câu đuôi thành MỘT chuỗi cho F5.

    Một chuỗi chứ không nối hai đoạn TIẾNG: nối tiếng là tái tạo đúng lỗi chỗ
    nối mảnh - F5 sinh mỗi phát ngôn với ngữ điệu kết câu riêng, hai lần "kết
    câu" dính nhau nghe thành hai đoạn rời.

    Mở đầu rỗng trả về đuôi nguyên vẹn: đó là trường hợp suy biến, tức đúng
    hành vi trước khi có tình huống.
    """
    a, b = (mo_dau or "").strip(), (duoi or "").strip()
    return f"{a} {b}".strip() if a else b


# Dải độ dài câu đệm phải phủ. Dưới 700ms thì `_FILLER_BO_QUA_MS` đã bỏ đệm;
# trên 2500ms là dài hơn mọi quãng trễ đo được (678-2084ms) cộng biên 1.25.
DAI_THAP_MS, DAI_CAO_MS, BUOC_MS = 700.0, 2500.0, 300.0


def du_phu(do_dai: list[float], thap: float = DAI_THAP_MS,
           cao: float = DAI_CAO_MS, buoc: float = BUOC_MS
           ) -> list[tuple[float, float]]:
    """Các khoảng trong [thap, cao] KHÔNG có câu nào dài xấp xỉ. Trả list khoảng hở.

    Vì sao cần: trục chọn câu đệm là ĐỘ DÀI. Hở một khoảng nghĩa là mọi lượt có
    quãng trễ rơi vào khoảng đó sẽ làm `chon()` tụt xuống tầng chót "lấy câu dài
    nhất", và khách nghe hụt đúng phần thiếu. Trang quản lý dùng hàm này để
    CHỈ RA lỗ hổng thay vì chỉ liệt kê câu.
    """
    ho: list[tuple[float, float]] = []
    moc = thap
    while moc < cao:
        het = min(moc + buoc, cao)
        if not any(moc <= d < het for d in do_dai):
            if ho and ho[-1][1] == moc:
                ho[-1] = (ho[-1][0], het)      # gộp khoảng hở liền nhau
            else:
                ho.append((moc, het))
        moc = het
    return ho
