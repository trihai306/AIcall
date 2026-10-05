"""Chọn tình huống từ phiên âm dở bằng cosine. KHÔNG import torch - xem
filler_store để biết vì sao cả ba tệp câu đệm phải chạy được không cần GPU.
"""
import re
import unicodedata

import numpy as np

# Điểm cosine tối thiểu để nhận một tình huống.
#
# ĐO 2026-08-12 trên 11 lần phân loại thật của một hội thoại 9 lượt, ghi cả
# những lần dưới ngưỡng để tính được mọi mức từ một lần chạy:
#
#     0.516  hoi_han_muc            "khoảng vay của"                    SAI
#     0.600  hen_goi_lai            "thế vay tối"                       SAI
#     0.613  tu_choi_dang_ban       "a lô"                              SAI
#     0.614  hoi_dieu_kien          "vay tín chấp"                      SAI
#     0.642  hen_goi_lai            "được rồi"                          đúng
#     0.692  xin_noi_chuyen_vien    "ừ em nói đi"                       SAI
#     0.694  no_xau_lo_khong...     "anh còn nợ"                        SAI
#     0.808  hoi_thoi_gian_duyet    "bao lâu thì"                       đúng
#     0.824  hoi_lai_suat           "lãi suất vay tín chấp bên em..."   đúng
#     0.869  hen_goi_lai            "được rồi mai anh gọi lại cho em"   đúng
#     0.887  hoi_lai_suat           "lãi suất vay"                      đúng
#
# Mọi lần SAI đều dưới 0.70; mọi lần trên 0.80 đều đúng. Có khoảng trống thật
# giữa 0.694 và 0.808, nên 0.75 nằm đúng chỗ tách:
#     0.55 -> phân loại 10 lần, đúng 5   (50%)
#     0.75 -> phân loại  4 lần, đúng 4  (100%)
#
# Chọn 0.75 dù nó BỎ nhiều lượt hơn, vì chọn sai mẩu mở đầu tệ hơn không có mẩu
# nào: nói "Dạ về thời gian duyệt hồ sơ thì" với người đang hỏi ngày đến hạn
# chính là "nói trớt vấn đề khách vừa nói" - lỗi mà tính năng này sinh ra để chữa.
#
# VÌ SAO điểm thấp lại hay sai: câu đệm phải phát TRƯỚC khi STT của lượt xong,
# nên phân loại chỉ có phiên âm CỤT ("thế vay tối", "vay tín chấp"). Cùng những
# câu đó ở dạng trọn vẹn thì phân loại đúng 7/7. Điểm thấp chính là dấu hiệu
# câu còn cụt - đó là lý do ngưỡng cao lọc được.
# ĐO LẠI 05-09-2026 trên 102 lượt tiếng khách THẬT (trích từ 47 bản ghi cuộc
# gọi) bằng `scripts/do_nguong_tinh_huong.py` — kết quả KHÁC HẲN phép đo cũ ở
# trên, vốn dựa trên một tập nhỏ:
#
#     mốc 1000ms   0,75 -> chọn 29, đúng 15, SAI 14   (52%)
#                  0,85 -> chọn  8, đúng  5, SAI  3   (62%)
#                  0,90 -> chọn  4, đúng  4, SAI  0   (100%)
#     mốc 1200ms   0,75 -> chọn 33, đúng 20, SAI 13   (61%)
#                  0,90 -> chọn  5, đúng  5, SAI  0   (100%)
#
# Tức 0,75 để lọt gần MỘT NỬA số lần chọn là sai tình huống. Nguyên tắc ngay
# trên vẫn đúng nguyên vẹn — chỉ là số đo cũ quá lạc quan.
#
# Cái giá đã biết và chấp nhận: chỉ ~5% lượt có câu đệm theo ngữ cảnh, 95% còn
# lại dùng rổ chung. Đó vẫn hơn hiện trạng, vì rổ chung trung tính còn chọn sai
# thì nghe như AI hiểu nhầm ý khách.
#
# ĐÃ ĐO VÀ BÁC BỎ hướng nới lưới lọc cho riêng đường câu đệm (dùng bản phiên âm
# thô chưa qua `_dang_ngo`): bản thô NGANG hoặc KÉM bản lọc ở mọi mốc, và ở
# 800ms nó chọn thêm 8 lượt thì cả 8 đều sai. Xem
# `scripts/do_noi_luoi_cau_dem.py`.
NGUONG_DIEM = 0.75

# Ngưỡng RIÊNG cho đường CHỌN CÂU ĐỆM. Không nâng `NGUONG_DIEM` chung vì
# `_tra_bang_hoi_dap` cũng gọi `chon_tinh_huong` với ngưỡng mặc định — nâng
# chung là âm thầm siết luôn bảng hỏi-đáp, một tính năng khác hẳn. Bộ test bắt
# được đúng chuyện này (`test_nguong_doc_thang_cao_hon_nguong_trung`).
#
# Hai đường chịu rủi ro khác nhau nên đáng có hai ngưỡng: bảng hỏi-đáp trượt thì
# rơi về tri thức (vô hại), còn câu đệm chọn sai thì khách nghe AI nói trớt ý.
#
# 0,90 -> 0,75 (06-09-2026), NGƯỜI DÙNG CHỌN sau khi thấy cái giá của 0,90:
# 3/5 lượt không nhận ra tình huống (`latency_metrics` hai phiên 10:25 và 10:31),
# và vì "không rõ thì thôi không phát đệm" nên 60% số lượt khách nghe im lặng
# trọn quãng chờ.
#
# CÁI GIÁ CỦA CHIỀU NGƯỢC LẠI, đã đo và đã nói rõ trước khi đổi
# (`scripts/do_nguong_tinh_huong.py`, 102 lượt tiếng khách thật):
#     mốc 1000ms  0,75 -> chọn 29, đúng 15, SAI 14   (52%)
#                 0,90 -> chọn  4, đúng  4, SAI  0   (100%)
#     mốc 1200ms  0,75 -> chọn 33, đúng 20, SAI 13   (61%)
#                 0,90 -> chọn  5, đúng  5, SAI  0   (100%)
# Tức đổi "không chọn" lấy "chọn nhiều hơn nhưng khoảng một nửa là sai tình
# huống". Đây là đánh đổi người dùng chọn, không phải số đo mới bác bỏ số cũ.
#
# BẮT BUỘC ĐI KÈM: hạ xuống dưới 0,90 thì vùng ĐỘ PHỦ THẤP hết an toàn - đo lại
# cùng một bảng ở hai ngưỡng cho hai kết quả ngược nhau, phần độ phủ dưới 0,5 là
# "4 đúng / 0 sai" ở 0,90 nhưng "4 đúng / 7 SAI" ở 0,75. Vùng đó nay do
# `filler_pick.DIEM_DOI_KHI_PHU_THAP` gác, và
# `tests/test_do_phu_tinh_huong.py` có lưới canh đúng ràng buộc này.
NGUONG_CAU_DEM = 0.75


def chuan_hoa(v: np.ndarray) -> np.ndarray:
    """Chuẩn hoá L2 theo hàng cuối. Nhận cả vector 1 chiều và ma trận.

    Vector 0 trả về chính nó chứ không chia cho 0: đoạn phiên âm rỗng hoàn toàn
    có thể cho ra vector 0, mà NaN lan ra thì mọi điểm sau đó vô nghĩa và không
    có gì báo lỗi.
    """
    v = np.atleast_2d(np.asarray(v, dtype=np.float32))
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return np.divide(v, n, out=np.zeros_like(v), where=n > 1e-12)


# Chủ đề bot có thể đã tư vấn, và dấu hiệu nhận ra trong LỜI BOT.
#
# Đọc lời BOT chứ không đọc lời khách - đây là điểm mấu chốt. Lời bot là chữ do
# chính hệ thống sinh ra: không đi qua tai máy, không mất dấu vì kênh 8kHz,
# không cụt vì khách chưa nói xong. Nó là tín hiệu SẠCH duy nhất còn lại khi
# điểm cosine giữa "hỏi" và "chê" chỉ cách nhau 0.026.
#
# Từ khoá cố ý để RỘNG ("lãi" chứ không phải "lãi suất"): bot nói "mức lãi hiện
# tại là" cũng là đã tư vấn lãi. Nhận dư một chút thì cùng lắm là cho nhóm chê
# vào cuộc sớm hơn cần thiết - vẫn phải thắng điểm cosine mới được chọn. Nhận
# thiếu thì cổng không bao giờ mở, và lỗi "chê hoá thành hỏi" còn nguyên.
#
# PHẢI BẮT CẢ CÂU TRẢ LỜI CỤT (thêm 07-09-2026). Bảng cũ chỉ có từ chỉ CHỦ ĐỀ,
# nên nó mù với đúng kiểu câu mà dự án đang cố ý theo đuổi - trả lời thẳng, gọn,
# không nhắc lại đề bài:
#     "Từ 7.9%/năm ạ."            không có chữ "lãi"
#     "Tối đa là 500 triệu đồng ạ."  không có "hạn mức" lẫn "vay tối đa"
# Cuộc 08c0d3e0: bot báo lãi bằng đúng câu đầu, cổng `lai_suat` không mở, nên
# khách chê "lãi cao thế" ở giây 116 bị chấm thành HỎI lãi (`che_lai_cao` chấm
# 1.000 mà bị loại, `hoi_lai_suat` 0.923 thắng) - khách đang chê mà nghe "Dạ lãi
# suất bên em thì,". Người dùng báo: "câu đệm ko có trong kịch bản, bot tự bịa".
#
# Cái giá của "%" và "tối đa": câu về PHÍ có phần trăm cũng đánh dấu lai_suat,
# câu về THỜI HẠN có "tối đa" cũng đánh dấu han_muc. Đó là nhận dư, đúng hướng
# an toàn đã nói ở trên - KHÔNG đổi thành điều kiện chặt hơn ("%" VÀ "/năm") vì
# nhận thiếu mới là lỗi đắt.
TU_KHOA_CHU_DE: dict[str, tuple[str, ...]] = {
    "lai_suat": ("lãi", "%", "phần trăm"),
    "han_muc": ("hạn mức", "tối đa"),
    "phi": ("phí",),
    "thoi_han": ("thời hạn", "kỳ hạn", "vay trong"),
}


# Tình huống nào chỉ được vào cuộc SAU KHI bot đã tư vấn chủ đề tương ứng.
#
# Để trong code chứ không thêm cột vào bảng `tinh_huong`: bảng đó đang có dữ
# liệu thật trên máy chạy, thêm cột là phải nâng cấp cơ sở dữ liệu cho một ánh
# xạ 3 dòng gần như không đổi. Đánh đổi: thêm tình huống chê mới qua trang quản
# lý thì phải sửa thêm ở đây - `tests/test_ngu_canh_luot.py` bắt được nếu quên.
#
# `so_sanh_ben_khac` CỐ Ý không có điều kiện: khách so sánh ngay từ lượt đầu là
# chuyện thường, và đo được nó không lẫn với "hỏi lãi" (0.638, dưới ngưỡng).
# Chỉ ba nhóm dưới đây mới lẫn - chúng dùng lại đúng chữ của câu hỏi.
DIEU_KIEN_NGU_CANH: dict[str, str] = {
    "che_lai_cao": "lai_suat",
    "che_phi_cao": "phi",
    "che_han_muc_thap": "han_muc",
}


def chu_de_da_noi(loi_bot: str) -> set[str]:
    """Chủ đề bot vừa tư vấn trong lượt này, đọc từ chính lời bot.

    Gọi sau mỗi lượt bot nói, dồn vào `session.da_tu_van`. Đó là thứ mở cổng
    cho nhóm tình huống chê - xem `loc_theo_ngu_canh`.
    """
    low = loi_bot.lower()
    return {chu_de for chu_de, tu in TU_KHOA_CHU_DE.items()
            if any(t in low for t in tu)}


def loc_theo_ngu_canh(dieu_kien: dict[str, str], da_tu_van) -> frozenset[str]:
    """Tình huống phải LOẠI khỏi lượt chấm này.

    `dieu_kien` = {id tình huống: chủ đề bắt buộc phải tư vấn trước}. Chuỗi rỗng
    nghĩa là không cần điều kiện gì - tuyệt đại đa số tình huống thuộc loại này.

    Chỉ BẬT THÊM nhóm chê, không tắt nhóm hỏi: khách vẫn được quyền hỏi lại lãi
    lần thứ hai sau khi đã nghe. Cổng này thu hẹp chỗ sai chứ không đổi hành vi
    đang đúng.
    """
    da = set(da_tu_van or ())
    return frozenset(id_th for id_th, chu_de in dieu_kien.items()
                     if chu_de and chu_de not in da)


def chon_tinh_huong(q: np.ndarray, kho: dict[str, np.ndarray],
                    nguong: float = NGUONG_DIEM,
                    bo_qua: frozenset[str] = frozenset()) -> tuple[str | None, float]:
    """Tình huống khớp nhất với `q`, hoặc `(None, điểm_cao_nhất)` nếu dưới ngưỡng.

    `kho` = {id: ma trận (số_ví_dụ, d) ĐÃ chuẩn hoá}. `q` đã chuẩn hoá.

    `bo_qua` là các tình huống chưa đủ điều kiện ngữ cảnh ở lượt này - xem
    `loc_theo_ngu_canh`. Loại TRƯỚC khi chấm chứ không chấm rồi bỏ: điểm trả về
    phải là điểm của cái thật sự được chọn, nếu không thì ngưỡng và log đều nói
    dối về độ chắc chắn của quyết định.

    Lấy ví dụ KHỚP NHẤT trong mỗi tình huống, không lấy trung bình các ví dụ:
    một tình huống thường có nhiều cách nói rất khác nhau ("lãi suất bao nhiêu"
    với "một tháng trả bao nhiêu"), lấy trung bình là làm loãng cả hai.
    """
    tot_id, tot_diem = None, 0.0
    for id_th, M in kho.items():
        if M.size == 0 or id_th in bo_qua:
            continue
        diem = float(np.max(M @ q))
        if diem > tot_diem:
            tot_id, tot_diem = id_th, diem
    if tot_id is not None and tot_diem >= nguong:
        return tot_id, tot_diem
    return None, tot_diem


def chon_tinh_huong_tu_khoa_nhanh(
    text: str, tinh_huong, bo_qua: frozenset[str] = frozenset(),
) -> str | None:
    """Chọn tức thì một chủ đề có mẩu nói trung tính và từ khóa không nhập nhằng.

    Chỉ dùng khi đã có TOÀN BỘ câu hỏi. Các nhóm về lãi, phí, hồ sơ... cần
    phân biệt hỏi/chê/trạng thái nên vẫn qua vector; hiện chỉ mẩu mở đầu về
    thẻ điện tử được duyệt cho đường này.
    """
    normalized = unicodedata.normalize("NFD", (text or "").casefold())
    normalized = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized.replace("đ", "d")).strip()
    words = f" {normalized} "
    if any(f" {phrase} " in words for phrase in (
        "khong hoi the dien tu", "khong phai the dien tu",
        "khong quan tam the dien tu", "ngoai the dien tu",
    )):
        return None

    matches = []
    for item in tinh_huong:
        if not item.bat or item.id in bo_qua:
            continue
        for keyword in item.tu_khoa:
            phrase = unicodedata.normalize("NFD", keyword.casefold())
            phrase = "".join(c for c in phrase if unicodedata.category(c) != "Mn")
            phrase = re.sub(r"[^a-z0-9]+", " ", phrase.replace("đ", "d")).strip()
            if len(phrase.split()) >= 2 and f" {phrase} " in words:
                matches.append((len(phrase), item.id))
    if not matches:
        return None
    longest = max(length for length, _ in matches)
    winners = {id_th for length, id_th in matches if length == longest}
    return "the_dien_tu" if winners == {"the_dien_tu"} else None


def chon_tinh_huong_vi_du_nhanh(
    text: str, tinh_huong, bo_qua: frozenset[str] = frozenset(),
) -> tuple[str | None, bool]:
    """Câu đầy đủ trùng một ví dụ đã lưu chỉ cần tra chữ, không cần nhúng lại.

    Dữ liệu mới có hiệu lực ngay sau ``nap_lai``. Kết quả thứ hai cho biết câu
    có trùng ví dụ nào không; nếu trùng HAI nhãn thì bỏ cả đường từ khóa và để
    vector quyết định. Không áp dụng cho phiên âm dở của cuộc gọi.
    """
    def norm(value: str) -> str:
        value = unicodedata.normalize("NFD", (value or "").casefold())
        value = "".join(c for c in value if unicodedata.category(c) != "Mn")
        return re.sub(r"[^a-z0-9]+", " ", value.replace("đ", "d")).strip()

    cau = norm(text)
    if not cau:
        return None, False
    matches = {
        item.id for item in tinh_huong
        if item.bat and item.id != "chung" and item.id not in bo_qua
        and any(norm(example) == cau for example in getattr(item, "vi_du", ()))
    }
    return (next(iter(matches)), True) if len(matches) == 1 else (None, bool(matches))


def vua_bao_lai_suat(history: list[dict]) -> bool:
    """Lời AI vừa nói có thật sự báo lãi không, không dùng chủ đề tích lũy cũ."""
    last_answer = ""
    previous_user = ""
    for turn in reversed(history):
        if not last_answer:
            if turn.get("role") == "assistant":
                last_answer = turn.get("content") or ""
        elif turn.get("role") == "user":
            previous_user = turn.get("content") or ""
            break
    if not last_answer:
        return False
    answer = unicodedata.normalize("NFD", last_answer.casefold())
    answer = "".join(c for c in answer if unicodedata.category(c) != "Mn")
    answer = re.sub(r"[^a-z0-9%]+", " ", answer.replace("đ", "d"))
    previous = unicodedata.normalize("NFD", previous_user.casefold())
    previous = "".join(c for c in previous if unicodedata.category(c) != "Mn")
    previous = re.sub(r"[^a-z0-9]+", " ", previous.replace("đ", "d"))
    topics = chu_de_da_noi(last_answer)
    if "phi" in topics or "lai_suat" not in topics:
        return False
    if any(cue in answer for cue in (
        "chua co thong tin", "khong co thong tin", "chua xac nhan",
        "can xac minh", "khong ro muc lai",
    )):
        return False
    if not re.search(r"\d|%|\bphan tram\b", answer):
        return False
    return bool(re.search(r"\blai\b", answer)
                or re.search(r"\blai\b", previous))


def chon_phan_hoi_ngan_theo_phien(
    text: str, history: list[dict], bo_qua: frozenset[str] = frozenset(),
) -> str | None:
    """Hiểu câu chê lãi rất ngắn từ lời AI NGAY TRƯỚC trong cùng phiên.

    "Cao thế em" tự nó không chứa chủ đề; nhúng vector sẽ rơi về câu chung.
    Chủ đề cũ ở nhiều lượt trước không đủ: khách có thể vừa chuyển sang phí.
    """
    if "che_lai_cao" in bo_qua:
        return None
    value = unicodedata.normalize("NFD", (text or "").casefold())
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    value = re.sub(r"[^a-z0-9]+", " ", value.replace("đ", "d")).strip()
    if not re.fullmatch(
        r"(?:(?:da|oi|ui|troi|sao|ma|vay) )*(?:cao|dat)"
        r" (?:qua|the|vay|nhi|ha)(?: (?:em|e|anh|chi|a))*", value,
    ):
        return None
    return "che_lai_cao" if vua_bao_lai_suat(history) else None


def chon_tinh_huong_cau_day_du(
    text: str, q: np.ndarray, kho: dict[str, np.ndarray], tinh_huong,
    nguong: float = 0.90, bo_qua: frozenset[str] = frozenset(),
) -> tuple[str | None, float]:
    """Câu đã có đủ chữ: vector quyết định, từ khóa rõ ràng cứu điểm sát ngưỡng.

    Không áp dụng cho phiên âm dở: một từ khóa trong câu cụt dễ gán sai ý.
    Từ khóa chỉ xác nhận ứng viên vector đứng đầu, không tự chọn chủ đề khác.
    """
    selected, score = chon_tinh_huong(q, kho, nguong=nguong, bo_qua=bo_qua)
    if selected or score < 0.80:
        return selected, score
    candidate, _ = chon_tinh_huong(q, kho, nguong=0.80, bo_qua=bo_qua)
    if not candidate:
        return None, score

    def norm(value: str) -> str:
        value = unicodedata.normalize("NFD", value.casefold())
        value = "".join(c for c in value if unicodedata.category(c) != "Mn")
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.replace("đ", "d"))).strip()

    words = f" {norm(text)} "
    matches = []
    for item in tinh_huong:
        if not item.bat or item.id in bo_qua or item.id not in kho:
            continue
        for keyword in item.tu_khoa:
            phrase = norm(keyword)
            if len(phrase.split()) >= 2 and f" {phrase} " in words:
                matches.append((len(phrase), item.id))
    if not matches:
        return None, score
    longest = max(length for length, _ in matches)
    winners = {id_th for length, id_th in matches if length == longest}
    return (candidate, score) if winners == {candidate} else (None, score)
