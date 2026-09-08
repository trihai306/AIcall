"""Khử tiếng AI vọng ngược vào kênh khách, dùng chính tiếng AI đã ghi xuống máy
làm tham chiếu.

Đo trên bản ghi thật 06-09-2026 (`scripts/do_vong_ai.py`): số 0833816298 vọng ở
mức chỉ thấp hơn tiếng AI 6dB, trễ ~340ms, tương quan −0,37; STT của cuộc đó ra
toàn chữ rác ("mọi người rút lui"). Người dùng nghe lại xác nhận có tiếng Lan.

Khác mọi phép lọc nhiễu đã bị bác bỏ trong dự án: ở đây có TÍN HIỆU THAM CHIẾU
- ta biết chính xác thứ đã vọng - nên chỉ trừ phần tương quan với nó, không đụng
phần còn lại.
"""
import numpy as np

from backend.services.khu_vong import KhuVong

SR = 8000
KHUNG = 160
RNG = np.random.default_rng(0)


def _giong(giay: float, rng=RNG) -> np.ndarray:
    """Tín hiệu giống tiếng nói: nhiễu trắng qua vài bộ cộng hưởng, có nhịp."""
    n = int(SR * giay)
    x = rng.standard_normal(n).astype(np.float32)
    for f in (400.0, 900.0, 1800.0):
        w = 2 * np.pi * f / SR
        r = 0.97
        y = np.zeros_like(x)
        for i in range(2, n):                       # cộng hưởng bậc 2
            y[i] = x[i] + 2 * r * np.cos(w) * y[i - 1] - r * r * y[i - 2]
        x = y / (np.abs(y).max() + 1e-9)
    nhip = 0.5 + 0.5 * np.sin(2 * np.pi * 3.0 * np.arange(n) / SR)  # 3 âm tiết/giây
    return (x * nhip * 0.3).astype(np.float32)


def _duong_vong(tham_chieu: np.ndarray, tre_mau: int, he_so: float) -> np.ndarray:
    """Vọng = tham chiếu trễ, giảm mức, qua bộ lọc thông thấp ngắn (kênh thoại)."""
    ra = np.zeros_like(tham_chieu)
    ra[tre_mau:] = tham_chieu[:-tre_mau] * he_so
    h = np.array([0.25, 0.5, 0.25], dtype=np.float32)
    return np.convolve(ra, h, "same").astype(np.float32)


def _db(x: np.ndarray) -> float:
    return 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9)


def _chay(kv: KhuVong, tham_chieu: np.ndarray, mic: np.ndarray) -> np.ndarray:
    """Đưa từng khung 20ms qua đúng thứ tự thật: tham chiếu ghi xuống máy trước,
    rồi khung mic tới."""
    ra = np.zeros_like(mic)
    for i in range(0, len(mic) - KHUNG + 1, KHUNG):
        kv.them_tham_chieu(tham_chieu[i:i + KHUNG])
        ra[i:i + KHUNG] = kv.xu_ly(mic[i:i + KHUNG])
    return ra


def test_khu_duoc_vong_tre_340ms_it_nhat_10db():
    # Mỗi test một hạt giống riêng: dùng chung RNG cấp module thì tín hiệu của
    # test sau phụ thuộc thứ tự chạy, và một lần rút "khó" đã làm test nói đè
    # đỏ trong khi chạy riêng thì xanh.
    ai = _giong(6.0, np.random.default_rng(1))
    tre = int(0.340 * SR)
    mic = _duong_vong(ai, tre, 0.5)           # −6dB, đúng mức đo được
    kv = KhuVong(sr=SR)
    ra = _chay(kv, ai, mic)
    # Chấm ở 3 giây CUỐI: 3 giây đầu là lúc bộ lọc còn đang học.
    cuoi = slice(3 * SR, 6 * SR)
    giam = _db(mic[cuoi]) - _db(ra[cuoi])
    assert giam >= 10.0, f"chỉ giảm được {giam:.1f}dB vọng"


def test_khong_lam_hong_loi_khach_khi_noi_de():
    # Khách nghe 4 giây rồi mới chen vào - lúc đó bộ lọc đã học xong. Chen liên
    # tục từ giây 0 thì Geigel đóng băng suốt và bộ lọc không bao giờ học được;
    # đó là giá cố ý trả để không "học" lời khách thành vọng.
    ai = _giong(6.0, np.random.default_rng(2))
    khach = _giong(6.0, np.random.default_rng(7)) * 0.8
    khach[: 4 * SR] = 0.0
    mic = _duong_vong(ai, int(0.340 * SR), 0.5) + khach
    kv = KhuVong(sr=SR)
    ra = _chay(kv, ai, mic)
    cuoi = slice(4 * SR, 6 * SR)
    # Phần còn lại phải là lời khách: sai khác so với khách gốc nhỏ hơn hẳn
    # phần vọng đã trừ đi.
    con_lai = ra[cuoi] - khach[cuoi]
    assert _db(con_lai) < _db(mic[cuoi] - khach[cuoi]) - 6.0, (
        f"sau khử, sai khác với lời khách {_db(con_lai):.1f}dB, "
        f"vọng ban đầu {_db(mic[cuoi] - khach[cuoi]):.1f}dB")
    assert abs(_db(ra[cuoi]) - _db(khach[cuoi])) < 1.5, "mức lời khách bị đổi quá 1,5dB"


def test_ai_im_thi_khung_di_qua_nguyen_ven():
    kv = KhuVong(sr=SR)
    khach = _giong(1.0, np.random.default_rng(3))
    ra = _chay(kv, np.zeros_like(khach), khach)
    assert np.array_equal(ra, khach), "AI không nói mà vẫn đụng vào tiếng khách"


# --- Đánh dấu khung là VỌNG, để VAD bỏ qua và STT không phiên âm nó ------------
#
# Vì sao cần: đo trên bản ghi thật (`scripts/gioi_han_tuyen_tinh.py`, 06-09-2026)
# khớp bình phương tối thiểu toàn tri 512 tap chỉ trừ được 0,4-0,6dB - vọng qua
# GSM + AGC máy khách không còn liên hệ tuyến tính cố định với tham chiếu. Nhưng
# tương quan TỪNG KHUNG tại mốc trễ có p90 0,93-0,98. Nên ngoài việc trừ phần
# khớp được, bộ khử phải NÓI cho VAD biết khung nào là vọng: chính những khung
# đó kéo dài lượt của khách sau khi họ dứt lời và đưa lời AI vào STT thành chữ
# rác ("rồi không đình mà sợ đấy").

def test_khung_chi_co_vong_duoc_danh_dau_la_vong():
    ai = _giong(6.0, np.random.default_rng(4))
    mic = _duong_vong(ai, int(0.340 * SR), 0.5)
    kv = KhuVong(sr=SR)
    co = []
    for i in range(0, len(mic) - KHUNG + 1, KHUNG):
        kv.them_tham_chieu(ai[i:i + KHUNG])
        kv.xu_ly(mic[i:i + KHUNG])
        if i >= 3 * SR and np.sqrt(np.mean(mic[i:i + KHUNG] ** 2)) > 0.01:
            co.append(kv.la_vong)
    assert np.mean(co) >= 0.9, f"chỉ {100*np.mean(co):.0f}% khung vọng được đánh dấu"


def test_khung_khach_noi_khong_bi_danh_dau_la_vong():
    ai = _giong(6.0, np.random.default_rng(5))
    khach = _giong(6.0, np.random.default_rng(8)) * 0.8
    khach[: 4 * SR] = 0.0
    mic = _duong_vong(ai, int(0.340 * SR), 0.5) + khach
    kv = KhuVong(sr=SR)
    co = []
    for i in range(0, len(mic) - KHUNG + 1, KHUNG):
        kv.them_tham_chieu(ai[i:i + KHUNG])
        kv.xu_ly(mic[i:i + KHUNG])
        if i >= 4 * SR and np.sqrt(np.mean(khach[i:i + KHUNG] ** 2)) > 0.02:
            co.append(kv.la_vong)
    assert np.mean(co) <= 0.1, f"{100*np.mean(co):.0f}% khung khách nói bị coi là vọng"
