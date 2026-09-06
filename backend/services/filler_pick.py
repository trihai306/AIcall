"""Luật chọn câu đệm. Thuần logic, KHÔNG import torch - xem filler_store."""
import asyncio
import random
import re

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



def tinh_huong_dung(tinh_huong: tuple[int, str, float] | None,
                    n_audio: int) -> tuple[str | None, float | None]:
    """Tình huống dùng cho lượt này, kèm ĐỘ PHỦ của bản đoán (chỉ để ghi số).

    `tinh_huong` = (số byte bản đoán đã nghe, id, điểm) - do `speculate` hoặc
    `_phan_loai_dong_bo` ghi. `n_audio` = tổng byte tiếng của lượt.

    KHÔNG còn lưới chặn theo độ phủ. Luật cũ vứt mọi phân loại có độ phủ dưới
    0,5 và tự ghi trong code là "TẠM 0.5, CHƯA ĐO". Đo 06-09-2026 trên 102 lượt
    tiếng khách thật, chấm ở đúng ngưỡng đường thật dùng (0,90), cắt theo tỉ lệ
    BYTE AUDIO đúng như `do_phu` thật:

        do_phu   vượt ngưỡng   ĐÚNG   SAI      luật cũ
          0.15         0          0     0      vứt đi
          0.25         0          0     0      vứt đi
          0.35         1          1     0      vứt đi
          0.45         3          3     0      vứt đi
          0.55         3          3     0      giữ lại
          0.70         4          4     0      giữ lại
          0.85         6          6     0      giữ lại

    SAI = 0 ở MỌI mức, và phần bị vứt là 4 đúng / 0 sai. Nó không chặn được lần
    sai nào, chỉ bỏ đi kết quả tốt - trên máy thật đã bỏ đúng một lượt hỏi lãi
    suất chấm 0,915.

    VÌ SAO bỏ được: ngưỡng ĐIỂM đã làm sẵn việc này. Chú thích của `NGUONG_DIEM`
    viết thẳng "điểm thấp chính là dấu hiệu câu còn cụt" - điểm đo trực tiếp cái
    mà độ phủ chỉ đo gián tiếp qua độ dài. Số đo trên xác nhận: không bản cắt nào
    lọt 0,90 khi độ phủ dưới 0,35.

    HỆ QUẢ phải nhớ: giờ CHỈ còn ngưỡng điểm gánh việc này. Hạ `NGUONG_CAU_DEM`
    xuống là phải đo lại bảng trên - `tests/test_do_phu_tinh_huong.py` có lưới
    canh đúng ràng buộc đó.

    Vẫn trả `do_phu` để `_send_filler` ghi vào metrics: bỏ luật thì bỏ, nhưng bỏ
    luôn số đo là lần sau lại phải đoán.

    `n_audio <= 0` là đường gõ chữ - không có tiếng nên không có gì để phủ.
    """
    if not tinh_huong or n_audio <= 0:
        return None, None
    n_th, id_th, diem = tinh_huong
    do_phu = n_th / n_audio
    if do_phu < DO_PHU_COI_LA_THAP and diem < DIEM_DOI_KHI_PHU_THAP:
        return None, do_phu
    return id_th, do_phu


# Dưới mức phủ này thì bản đoán mới nghe được một phần câu, và ĐÒI ĐIỂM CAO HƠN.
#
# Vì sao có hai con số thay vì một sàn phẳng: đo cùng một bảng ở hai ngưỡng cho
# hai kết quả ngược nhau (`scripts/do_do_phu_tinh_huong.py [nguong]`, 102 lượt
# tiếng khách thật). Phần độ phủ dưới 0,5:
#
#     chấm ở 0,90 -> 4 đúng / 0 SAI     (độ phủ là đồ thừa)
#     chấm ở 0,75 -> 4 đúng / 7 SAI     (độ phủ là lưới thật)
#
# Tức rủi ro không nằm ở ĐỘ DÀI mà ở ĐỘ CHẮC CHẮN; độ dài chỉ là proxy. Nên luật
# đúng là "nghe được ít thì phải chắc hơn", không phải sàn phẳng.
#
# Không quay lại sàn phẳng 0,5: nó vứt luôn ca đo được trên máy thật (điểm 0,915
# ở độ phủ 0,35) - đúng ca người dùng vừa thấy chạy đúng ngày 06-09.
DO_PHU_COI_LA_THAP = 0.5
DIEM_DOI_KHI_PHU_THAP = 0.90


# Không rõ tình huống thì có BỎ HẲN câu đệm không. Xem `nen_bo_cau_dem` cho số
# đo và lịch sử của quyết định này.
BO_DEM_KHI_KHONG_RO = False


def nen_bo_cau_dem(id_tinh_huong: str | None, co_audio: bool) -> bool:
    """Có BỎ HẲN câu đệm lượt này không (thay vì rơi về rổ chung)?

    Người dùng 06-09-2026: "sao vẫn vào none nhiều, nếu none thì thôi không câu
    đệm cho tôi". Rổ chung trung tính nhưng vô thưởng vô phạt, và khi nó rơi
    trúng câu cùng nghĩa với lưới chặn số thì thành nói hai lần một ý.

    CÁI GIÁ, đo cùng ngày trên `latency_metrics` (hai phiên 10:25 và 10:31):
    3/5 lượt có `tinh_huong_id` rỗng. Bỏ đệm ở đó nghĩa là 60% số lượt khách
    nghe im lặng trọn quãng chờ - đo được 1376-2325ms. Hạ được tỉ lệ None
    (hiện do ngưỡng 0,90 chặn) thì cái giá này nhỏ đi theo.

    `co_audio = False` là đường GÕ CHỮ: ở đó `n_audio = 0` nên máy chưa từng thử
    phân loại. "Không rõ tình huống" ở đấy không mang nghĩa gì, áp luật này vào
    là xoá sạch câu đệm của một đường vốn đang chạy đúng.

    ĐÃ TẮT chiều 06-09-2026 (`BO_DEM_KHI_KHONG_RO = False`). Đo trên cuộc gọi
    `e036b33b` cho thấy cái giá thật của việc bỏ đệm: khách dứt lời tới lúc AI
    cất tiếng là 560ms ở lượt CÓ tình huống, nhưng **1920ms và 1880ms** ở hai
    lượt None. Nâng mốc im lặng lên 1 giây thì quãng đó thành ~2,7 giây - nghe
    như rớt máy. Câu đệm rổ chung tuy trung tính nhưng vẫn hơn im lặng.
    """
    return BO_DEM_KHI_KHONG_RO and co_audio and id_tinh_huong is None


# Nhịp hỏi lại khi đang chờ tình huống. 20ms là một khung tiếng - nhỏ hơn thì
# chỉ tốn vòng lặp, lớn hơn thì cái lợi của việc về sớm bị chính nó ăn mất.
NHIP_HOI_MS = 20.0


async def cho_den_khi(dieu_kien, tran_ms: float,
                      nhip_ms: float = NHIP_HOI_MS) -> float:
    """Chờ tới khi `dieu_kien()` đúng, tối đa `tran_ms`. Trả số ms đã chờ THẬT.

    VÌ SAO KHÔNG dùng `asyncio.wait({task})`: tác vụ đoán trước làm năm việc nối
    nhau - STT, ghi `spec_stt`, CHẤM TÌNH HUỐNG, RAG, rồi LLM soạn sẵn. Câu đệm
    chỉ cần việc thứ ba, mà chờ theo tác vụ là chờ luôn hai việc cuối, vốn tốn
    hàng trăm ms tới cả giây và câu đệm không dùng tới.

    Đo trên cuộc gọi thật 0396130621 (phiên e2e7034c, 10:59): ngân sách 650ms mà
    "AI bắt đầu nói sau 754ms" và "745ms" - lần nào cũng đốt trọn ngân sách,
    trong khi phiên âm cuối câu chỉ mất 297-365ms. Tức phần lớn quãng chờ đó là
    chờ RAG và LLM một cách vô ích.

    Trả số ms đã chờ để `_send_filler` ghi vào metrics - không có nó thì lần sau
    lại phải đoán xem cú chờ tốn bao nhiêu.
    """
    t0 = asyncio.get_event_loop().time()
    tran = tran_ms / 1000.0
    while True:
        if dieu_kien():
            break
        if asyncio.get_event_loop().time() - t0 >= tran:
            break
        await asyncio.sleep(min(nhip_ms / 1000.0, tran))
    return (asyncio.get_event_loop().time() - t0) * 1000.0

# Tiểu từ lịch sự ở đầu câu đuôi cần bỏ khi đã có mẩu mở đầu.
# Thứ tự: dài trước để tránh khớp chặng đầu của từ dài hơn
# (vd "Vâng ạ" phải thắng "Vâng" khi đuôi là "Vâng ạ, ...").
# Đo 08-11: 41/42 câu đuôi (bat=1) mở bằng Dạ hoặc Vâng;
#           20/20 mẩu mở đầu cũng vậy → 820/840 tổ hợp (98%) bị lặp.
# Sau tiểu từ: `[,\s]*` ăn dấu phẩy và/hoặc khoảng trắng tuỳ ý,
# rồi phần còn lại gom vào group(2).
_TIEU_TU_RE = re.compile(
    r"^(Dạ vâng ạ|Dạ vâng|Vâng ạ|Dạ|Vâng)[,\s]*(.*)",
    re.DOTALL,
)


def ghep(mo_dau: str, duoi: str) -> str:
    """Ghép mẩu mở đầu với câu đuôi thành MỘT chuỗi cho F5.

    Một chuỗi chứ không nối hai đoạn TIẾNG: nối tiếng là tái tạo đúng lỗi chỗ
    nối mảnh - F5 sinh mỗi phát ngôn với ngữ điệu kết câu riêng, hai lần "kết
    câu" dính nhau nghe thành hai đoạn rời.

    Mở đầu rỗng trả về đuôi nguyên vẹn: đó là trường hợp suy biến, tức đúng
    hành vi trước khi có tình huống.

    Khi có mẩu mở đầu, bỏ tiểu từ lịch sự ở đầu câu đuôi để tránh lặp.
    Đo 08-11 trên 840 tổ hợp: 98% bị nói lắp trước khi có logic này.
    STT nghe lại clip thật xác nhận: "dạ về lãi suất thì dạ em kiểm tra ngay."
    Câu đuôi dùng trần (mở đầu rỗng) giữ nguyên tiểu từ — lúc đó đúng.
    """
    a, b = (mo_dau or "").strip(), (duoi or "").strip()
    if not a:
        return b  # suy biến: đúng hành vi khi không có tình huống

    m = _TIEU_TU_RE.match(b)
    if m:
        b_tran = m.group(2).strip()
        if not b_tran:
            # Câu đuôi hoàn toàn là tiểu từ ("Dạ", "Vâng ạ", "Dạ vâng ạ").
            # Chỉ phát mẩu mở đầu; không thêm âm trống sau dấu phẩy.
            return a
        # Chữ đầu phải viết thường: đứng giữa câu, không phải đầu câu mới.
        # Dữ liệu thật đã thường sẵn; đây là lưới chặn cho câu đuôi tương lai.
        b_tran = b_tran[0].lower() + b_tran[1:]
    else:
        b_tran = b  # không có tiểu từ → giữ nguyên

    return f"{a} {b_tran}"


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
