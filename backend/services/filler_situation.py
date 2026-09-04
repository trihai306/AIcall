"""Chọn tình huống từ phiên âm dở bằng cosine. KHÔNG import torch - xem
filler_store để biết vì sao cả ba tệp câu đệm phải chạy được không cần GPU.
"""
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
NGUONG_DIEM = 0.75


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
TU_KHOA_CHU_DE: dict[str, tuple[str, ...]] = {
    "lai_suat": ("lãi",),
    "han_muc": ("hạn mức", "vay tối đa", "vay được tối đa"),
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
