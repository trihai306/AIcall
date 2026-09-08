"""Tìm độ trễ vòng của đường tiếng bằng đối sánh chirp trên hai kênh bản ghi.

Vì sao cần. Bản ghi cuộc gọi đóng dấu khung AI lúc nó RỜI backend
(`phone_call_service.py:1100`) và khung khách lúc backend NHẬN được. Đo khoảng
cách giữa hai mốc đó cho ra độ trễ NỘI BỘ, thiếu trọn chặng
USB -> máy -> GSM -> tai khách và chặng ngược lại. Phần thiếu đó chưa ai đo:
thử suy từ tiếng AI vọng ngược trên 47 bản ghi thật thì chỉ 4 cuộc có tương
quan đủ mạnh (0,25-0,37) và chúng cho 100/320/340/580ms - không kết luận được.

Cách đo: phát một chirp qua đúng đường phát thật, để nó đi hết vòng rồi vọng
lại vào mic ở đầu khách. Cả hai lần xuất hiện đều nằm trên MỘT trục thời gian
của bản ghi, nên hiệu vị trí là độ trễ vòng - không cần đồng bộ đồng hồ hai máy.

Chirp chứ không phải tone thuần: tone 1kHz cho đỉnh tương quan lặp lại mỗi 1ms
nên không biết đỉnh nào là thật.
"""
import numpy as np
import pytest

from scripts.do_tre_vong import TIN_TOI_THIEU, tao_chirp, tim_tre


SR = 8000


def _dung_hai_kenh(tre_ms: float, sr: int = SR, giay: float = 4.0,
                   suy_giam_db: float = -20.0, nhieu: float = 0.002,
                   t_phat: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Kênh AI có chirp tại `t_phat`; kênh khách có bản vọng trễ `tre_ms`."""
    rng = np.random.default_rng(7)
    n = int(sr * giay)
    ai = rng.normal(0, nhieu, n)
    kh = rng.normal(0, nhieu, n)
    c = tao_chirp(sr)
    i = int(sr * t_phat)
    ai[i:i + len(c)] += c
    j = i + int(sr * tre_ms / 1000)
    kh[j:j + len(c)] += c * (10 ** (suy_giam_db / 20))
    return ai, kh


def test_tim_dung_do_tre_da_biet():
    ai, kh = _dung_hai_kenh(tre_ms=340)
    tre, tin = tim_tre(ai, kh, SR)
    assert tre == pytest.approx(340, abs=10)
    assert tin >= TIN_TOI_THIEU


def test_vong_rat_yeu_van_tim_ra():
    """Vọng -35dB: mức đã đo trên bản ghi thật (khách/AI -33 tới -37dB)."""
    ai, kh = _dung_hai_kenh(tre_ms=180, suy_giam_db=-35)
    tre, tin = tim_tre(ai, kh, SR)
    assert tre == pytest.approx(180, abs=10)


def test_khong_co_vong_thi_bao_khong_tin_duoc():
    """Kênh khách chỉ có nhiễu: phải nói KHÔNG TIN ĐƯỢC, không bịa ra một số."""
    ai, kh = _dung_hai_kenh(tre_ms=340)
    rng = np.random.default_rng(11)
    kh = rng.normal(0, 0.002, len(kh))          # xoá sạch vọng
    _, tin = tim_tre(ai, kh, SR)
    assert tin < TIN_TOI_THIEU


def test_tieng_noi_cua_khach_khong_keo_lech_ket_qua():
    """Khách nói chen vào lúc chirp đang đi: vẫn phải bắt đúng chirp."""
    ai, kh = _dung_hai_kenh(tre_ms=260)
    rng = np.random.default_rng(3)
    t = np.arange(len(kh)) / SR
    noi = np.zeros(len(kh))
    a, b = int(SR * 1.05), int(SR * 1.9)
    noi[a:b] = 0.05 * np.sin(2 * np.pi * 220 * t[a:b]) * rng.normal(1, .3, b - a)
    tre, tin = tim_tre(ai, kh + noi, SR)
    assert tre == pytest.approx(260, abs=10)


def test_chirp_nam_trong_bang_thoai():
    """Ngoài 300-3400Hz thì GSM cắt mất - chirp phải nằm gọn trong băng."""
    c = tao_chirp(SR)
    ph = np.abs(np.fft.rfft(c)) ** 2
    f = np.fft.rfftfreq(len(c), 1 / SR)
    trong_bang = ph[(f >= 300) & (f <= 3400)].sum() / ph.sum()
    assert trong_bang > 0.95


# --- gom nhiều lần phát trong một bản ghi ---------------------------------
# Một lần bíp không cho biết số đo có tin được không. Phát nhiều lần rồi nhìn
# độ tản mới biết.

def test_gom_dung_so_lan_phat_va_do_tre_tung_lan():
    from scripts.do_tre_vong import do_nhieu_lan
    rng = np.random.default_rng(5)
    n = SR * 12
    ai = rng.normal(0, 0.002, n)
    kh = rng.normal(0, 0.002, n)
    c = tao_chirp(SR)
    tre_that = [340, 355, 330]
    for k, tre in enumerate(tre_that):
        i = int(SR * (1.5 + 3.0 * k))
        ai[i:i + len(c)] += c
        j = i + int(SR * tre / 1000)
        kh[j:j + len(c)] += c * (10 ** (-25 / 20))
    ket = do_nhieu_lan(ai, kh, SR)
    assert len(ket) == 3
    for (tre, _), mong in zip(ket, tre_that):
        assert tre == pytest.approx(mong, abs=10)


def test_lan_phat_khong_co_vong_bi_loai_khoi_ket_qua():
    """Chỉ lần nào tìm thấy vọng mới được tính - không lấp chỗ trống bằng số bịa."""
    from scripts.do_tre_vong import do_nhieu_lan
    rng = np.random.default_rng(9)
    n = SR * 9
    ai = rng.normal(0, 0.002, n)
    kh = rng.normal(0, 0.002, n)
    c = tao_chirp(SR)
    for k in range(2):
        i = int(SR * (1.5 + 3.0 * k))
        ai[i:i + len(c)] += c
    j = int(SR * 1.5) + int(SR * 0.3)          # chỉ lần ĐẦU có vọng
    kh[j:j + len(c)] += c * (10 ** (-25 / 20))
    ket = do_nhieu_lan(ai, kh, SR)
    assert len(ket) == 1
    assert ket[0][0] == pytest.approx(300, abs=10)


# --- gói tiếng đem phát ----------------------------------------------------
# AudioTrack trên máy dựng đệm `dem_xuong` = 500ms (BridgeService.java). Đẩy vào
# một mảnh 250ms rồi im 2,5s thì mảnh nằm lại trong đệm chưa đủ ngưỡng phát: đo
# 07-09 chỉ 2/8 lần chirp ra được tới loa. Gói phải DÀY HƠN đệm đó.

def test_goi_phat_day_hon_dem_cua_may():
    from scripts.do_tre_vong import DEM_XUONG_MS, wav_chirp
    import io, wave
    with wave.open(io.BytesIO(wav_chirp()), "rb") as w:
        giay = w.getnframes() / w.getframerate()
    assert giay * 1000 > DEM_XUONG_MS * 1.5


def test_chirp_van_tim_duoc_trong_goi_co_im_lang():
    """Bọc im lặng không được làm lệch mốc: chirp vẫn phải tìm ra đúng chỗ."""
    from scripts.do_tre_vong import doc_wav, wav_chirp
    x, sr = doc_wav(wav_chirp())
    rng = np.random.default_rng(2)
    kh = rng.normal(0, 0.002, len(x) + sr)
    tre = int(sr * 0.25)
    kh[tre:tre + len(x)] += x * 0.05
    ai = np.concatenate([x, np.zeros(sr)])
    tre_do, tin = tim_tre(ai, kh, sr)
    assert tre_do == pytest.approx(250, abs=15)
    assert tin >= TIN_TOI_THIEU
