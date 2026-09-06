"""Câu chào phải vào bản ghi ĐỦ, dù lúc đó chưa mở tai nghe khách.

VÌ SAO CÓ FILE NÀY. Ba cuộc gọi thật liên tiếp (`99ee5360`, `f2f61c42`,
`394faf67`) đều cho kênh AI đoạn đầu chỉ **1,4 giây**, trong khi log TTS ghi rõ
câu chào dài **2830ms** và sinh lại bằng tay thì 3/3 lần đều đủ chữ. Tôi đã lần
lượt đổ cho TTS, cho việc khách nói đè, rồi cho gió — cả ba đều sai.

Gốc thật nằm ở BỘ GHI, không nằm ở đường tiếng:

  - `chao_khi_bat_may` chỉ đặt `tam_dung_nghe = False` SAU khi đã chào.
  - Trong lúc đó `_read_loop` gặp `tam_dung_nghe` là `continue` ngay, nên
    `them_khach()` KHÔNG được gọi -> trục thời gian của bản ghi đứng yên ở 0.
  - `them_bot()` vẫn chạy (tiếng AI vẫn rời máy chủ bình thường), nên cả 141
    khung câu chào cùng đóng dấu vị trí ~0.
  - `_lay_khoi` vứt khung bot khi `vi_tri < i - _TRUOT_TOI_DA`, và mỗi vòng chỉ
    lấy được một khung -> quá nửa câu chào bị vứt.

Khách VẪN NGHE ĐỦ (log cùng cuộc gọi: "không đói khung lần nào — đường tiếng
xuống máy sạch"). Chỉ bản ghi hỏng. Đây là lý do phải có test này: bản ghi là
bằng chứng chính để soi cuộc gọi, mà nó lại nói dối đúng ở đoạn quan trọng nhất.
"""
import numpy as np
import pytest

from backend.services.recorder import GhiAmCuocGoi

SR = 8000
KHUNG = 160          # 20ms @ 8kHz


def _bo_ghi(tmp_path):
    bo = GhiAmCuocGoi("thu", tmp_path, sr=SR, mau_moi_khung=KHUNG)
    # `them_khach`/`them_bot` chỉ nhận khung khi đang chạy. Bật cờ thẳng thay vì
    # `start()` để khỏi phải dựng task nền chỉ để kiểm phép ghép hai kênh.
    bo.running = True
    return bo


def _tieng(n=KHUNG, muc=0.3):
    return np.full(n, muc, dtype=np.float32)


def test_khung_bot_khong_bi_vut_khi_kenh_khach_chay_cung(tmp_path):
    """Sau khi sửa: vòng thu ghi kênh khách NGAY CẢ khi `tam_dung_nghe` bật, nên
    hai chiều chạy cùng nhịp trong lúc chào và không khung nào bị vứt."""
    bo = _bo_ghi(tmp_path)
    n_chao = 141                                  # 2,83 giây
    # Vòng thu chạy song song với đường phát: mỗi khung bot có một khung khách
    # đi kèm, kể cả khi khách chưa nói gì (khung im).
    for _ in range(n_chao):
        bo.them_bot(_tieng())
        bo.them_khach(_tieng(muc=0.0))
    for _ in range(50):
        bo.them_khach(_tieng(muc=0.1))

    giu = 0
    while True:
        khoi = bo._lay_khoi(np.zeros(KHUNG, dtype=np.float32))
        if khoi is None:
            break
        giu += int((np.abs(khoi[:, 1]) > 0.01).sum() // KHUNG)
    assert giu >= n_chao * 0.9, (
        f"chỉ {giu}/{n_chao} khung câu chào vào được bản ghi — "
        "phần còn lại bị vứt — trục thời gian kênh khách phải chạy trong lúc chào")


def test_kenh_khach_dung_yen_thi_mat_cau_chao(tmp_path):
    """Ghi lại HÌNH DẠNG CŨ của lỗi, để không ai vô tình dựng lại nó.

    Nếu vòng thu không ghi kênh khách trong lúc `tam_dung_nghe` bật thì trục
    thời gian đứng yên và quá nửa câu chào bị vứt. Đo được 26/141.
    """
    bo = _bo_ghi(tmp_path)
    n_chao = 141
    for _ in range(n_chao):
        bo.them_bot(_tieng())                    # KHÔNG có them_khach đi kèm
    for _ in range(n_chao + 50):
        bo.them_khach(_tieng(muc=0.1))
    giu = 0
    while True:
        khoi = bo._lay_khoi(np.zeros(KHUNG, dtype=np.float32))
        if khoi is None:
            break
        giu += int((np.abs(khoi[:, 1]) > 0.01).sum() // KHUNG)
    assert giu < n_chao * 0.5, (
        "hình dạng lỗi cũ đã đổi — cập nhật lại chú thích ở đầu file")


def test_kenh_khach_chay_song_song_thi_khong_mat_gi(tmp_path):
    """Đối chứng: hai chiều chạy cùng nhịp thì không được mất khung nào."""
    bo = _bo_ghi(tmp_path)
    n = 100
    for _ in range(n):
        bo.them_bot(_tieng())
        bo.them_khach(_tieng(muc=0.1))
    giu = 0
    while True:
        khoi = bo._lay_khoi(np.zeros(KHUNG, dtype=np.float32))
        if khoi is None:
            break
        giu += int((np.abs(khoi[:, 1]) > 0.01).sum() // KHUNG)
    assert giu >= n * 0.95, f"mất khung dù hai chiều cùng nhịp: {giu}/{n}"
