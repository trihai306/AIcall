"""Bóp quãng lặng F5 tự bịa vào giữa câu, KHÔNG đụng nhịp nghỉ thật của dấu câu.

Ngưỡng 360ms lấy từ đo thật ở đúng cấu hình đang chạy, 10 lượt mỗi bản:

    nghỉ THẬT   không dấu giữa 0ms | 1 phẩy 160ms | 1 chấm 320ms | 2 chấm 260ms
    quãng BỊA   380 - 1600ms   (đo trên bản ghi hội thoại thật)

Từng thử ngưỡng 260ms và SAI: nghỉ thật ở dấu chấm chạm 320ms nên nó cắt nhầm
ranh giới câu, hai câu dính vào nhau.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest

from backend.services.tts_service import (
    GIU_LANG_MS, NGUONG_LANG_BIA_MS, cat_lang_bia,
)

SR = 24000


def tieng(ms: float) -> np.ndarray:
    """Đoạn 'có tiếng' - biên độ đủ cao để không bị coi là lặng."""
    return np.full(int(SR * ms / 1000), 0.5, dtype=np.float32)


def im(ms: float) -> np.ndarray:
    return np.zeros(int(SR * ms / 1000), dtype=np.float32)


def im_co_hoi_tho(ms: float, ti_le: float = 0.12) -> np.ndarray:
    """Quãng nghỉ THẬT của F5: tai nghe là im, nhưng KHÔNG bằng 0.

    Đo trên bản ghi cuộc gọi thật, 23 quãng: năng lượng bằng 7,6% - 14,9% năng
    lượng đỉnh của mảnh, đỉnh biên độ 0.023 - 0.078. Bản đầu của `cat_lang_bia`
    xét biên độ đỉnh < 0.015 nên bỏ qua sạch 14/14 - hàm nằm im suốt từ ngày
    viết mà không ai biết, vì mọi test đều dùng lặng số học.

    Bao biên độ hình chữ V: hơi thở tắt dần về giữa quãng rồi nhen lên ở cuối.
    Chi tiết này không phải trang trí - nó là thứ để phân biệt quãng nghỉ với
    tiếng nhỏ đều đều, và là căn cứ của điều kiện "chạm đáy".
    """
    rng = np.random.default_rng(7)
    n = int(SR * ms / 1000)
    bao = np.abs(np.linspace(-1.0, 1.0, n))
    return (rng.standard_normal(n) * 0.5 * ti_le * bao).astype(np.float32)


def tieng_nho(ms: float, bien: float = 0.08) -> np.ndarray:
    """Tiếng NHỎ nhưng đều - phải giữ, không được coi là quãng nghỉ."""
    return np.full(int(SR * ms / 1000), bien, dtype=np.float32)


def do_lang_giua(x: np.ndarray, nguong_bien=0.015) -> list[float]:
    n = int(SR * 0.02)
    k = len(x) // n
    to = np.abs(x[: k * n].reshape(k, n)).max(axis=1)
    lang = to < nguong_bien
    ra, i = [], 0
    while i < k:
        if lang[i]:
            j = i
            while j < k and lang[j]:
                j += 1
            if i > 0 and j < k:
                ra.append((j - i) * 20.0)
            i = j
        else:
            i += 1
    return ra


# --- bóp đúng thứ cần bóp -----------------------------------------------

@pytest.mark.parametrize("dai_ms", [400, 600, 1000, 1600])
def test_bop_quang_bia(dai_ms):
    x = np.concatenate([tieng(500), im(dai_ms), tieng(500)])
    z = cat_lang_bia(x, SR)
    con = do_lang_giua(z)
    assert con and con[0] == pytest.approx(GIU_LANG_MS, abs=25)


@pytest.mark.parametrize("ti_le", [0.076, 0.12, 0.149])
def test_bop_quang_co_hoi_tho(ti_le):
    """Ca đã làm hàm chết: quãng nghỉ không im tuyệt đối vẫn phải bóp.

    7,6% / 12% / 14,9% là dải đo được trên bản ghi cuộc gọi thật.
    """
    x = np.concatenate([tieng(500), im_co_hoi_tho(700, ti_le), tieng(500)])
    z = cat_lang_bia(x, SR)
    # 700ms bóp còn 200ms -> ngắn đi 500ms, trừ sai số một khung ở mỗi mép.
    assert (len(x) - len(z)) / SR * 1000 == pytest.approx(500, abs=45)


def test_nguong_bam_theo_do_to_cua_manh():
    """Ngưỡng tính theo TỈ LỆ nên mảnh to nhỏ đều xử lý như nhau."""
    for he in (0.2, 1.0, 4.0):
        x = np.concatenate([tieng(500), im_co_hoi_tho(700), tieng(500)]) * he
        assert len(cat_lang_bia(x, SR)) < len(x), f"hệ số {he}"


def test_khong_bop_tieng_nho_deu():
    """Tiếng nhỏ nhưng ĐỀU thì giữ - đây là việc của điều kiện 'chạm đáy'.

    Biên độ 0.08 nằm dưới ngưỡng rộng (20% của 0.5 = 0.10) nên bị đánh dấu là
    lặng, nhưng nó không bao giờ tụt xuống đáy 7% nên không được công nhận.
    Thiếu điều kiện này thì mọi đoạn nói nhỏ dài quá 360ms đều bị xén.
    """
    x = np.concatenate([tieng(500), tieng_nho(700), tieng(500)])
    assert cat_lang_bia(x, SR) is x


def test_giu_nguyen_nhip_nghi_that_cua_dau_cham():
    """320ms là nghỉ THẬT ở dấu chấm - không được đụng vào."""
    x = np.concatenate([tieng(500), im(320), tieng(500)])
    z = cat_lang_bia(x, SR)
    assert len(z) == len(x)
    assert do_lang_giua(z)[0] == pytest.approx(320, abs=25)


def test_giu_nguyen_nhip_nghi_dau_phay():
    x = np.concatenate([tieng(500), im(160), tieng(500)])
    assert len(cat_lang_bia(x, SR)) == len(x)


def test_dung_ngay_moc_thi_khong_bop():
    """Đúng bằng ngưỡng thì giữ - chỉ bóp khi VƯỢT."""
    x = np.concatenate([tieng(400), im(NGUONG_LANG_BIA_MS), tieng(400)])
    assert len(cat_lang_bia(x, SR)) == len(x)


# --- không đụng hai đầu -------------------------------------------------

def test_khong_dung_lang_o_hai_dau():
    """Hai đầu là việc của trim_silence, và nhịp nối mảnh do chỗ khác chèn."""
    x = np.concatenate([im(800), tieng(500), im(800)])
    assert len(cat_lang_bia(x, SR)) == len(x)


# --- không làm hỏng thứ khác --------------------------------------------

def test_nhieu_quang_bop_het():
    x = np.concatenate([tieng(300), im(700), tieng(300), im(900), tieng(300)])
    con = do_lang_giua(cat_lang_bia(x, SR))
    assert len(con) == 2
    assert all(c == pytest.approx(GIU_LANG_MS, abs=25) for c in con)


def test_khong_co_gi_de_bop_thi_tra_nguyen_vat():
    x = np.concatenate([tieng(500), im(160), tieng(500)])
    assert cat_lang_bia(x, SR) is x


def test_tieng_lien_mach_khong_doi():
    x = tieng(2000)
    assert cat_lang_bia(x, SR) is x


def test_rong_va_qua_ngan():
    assert len(cat_lang_bia(np.array([], dtype=np.float32), SR)) == 0
    ngan = tieng(10)
    assert cat_lang_bia(ngan, SR) is ngan


def test_khong_lam_mat_tieng():
    """Tổng lượng tiếng (mẫu vượt ngưỡng) phải giữ nguyên."""
    x = np.concatenate([tieng(500), im(900), tieng(700)])
    z = cat_lang_bia(x, SR)
    assert int((np.abs(z) >= 0.015).sum()) == int((np.abs(x) >= 0.015).sum())
