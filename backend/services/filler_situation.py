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


def chon_tinh_huong(q: np.ndarray, kho: dict[str, np.ndarray],
                    nguong: float = NGUONG_DIEM) -> tuple[str | None, float]:
    """Tình huống khớp nhất với `q`, hoặc `(None, điểm_cao_nhất)` nếu dưới ngưỡng.

    `kho` = {id: ma trận (số_ví_dụ, d) ĐÃ chuẩn hoá}. `q` đã chuẩn hoá.

    Lấy ví dụ KHỚP NHẤT trong mỗi tình huống, không lấy trung bình các ví dụ:
    một tình huống thường có nhiều cách nói rất khác nhau ("lãi suất bao nhiêu"
    với "một tháng trả bao nhiêu"), lấy trung bình là làm loãng cả hai.
    """
    tot_id, tot_diem = None, 0.0
    for id_th, M in kho.items():
        if M.size == 0:
            continue
        diem = float(np.max(M @ q))
        if diem > tot_diem:
            tot_id, tot_diem = id_th, diem
    if tot_id is not None and tot_diem >= nguong:
        return tot_id, tot_diem
    return None, tot_diem
