"""Kiểm kho câu thật trong data/fillers.json - bắt lỗi lúc soạn câu."""
from backend.services.filler_store import DUONG_DAN_MAC_DINH, lay_kho, nap


def test_kho_that_nap_duoc():
    kho = nap(DUONG_DAN_MAC_DINH)
    assert len(kho.cau) >= 28


def test_moc_1_chi_co_chu_de_chung():
    # Lọc theo chủ đề là mốc 2. Seed câu nêu chủ đề bây giờ thì nó phát cho
    # câu hỏi bất kỳ - tệ hơn hiện tại.
    assert {c.chu_de for c in nap(DUONG_DAN_MAC_DINH).cau} == {"chung"}


def test_du_cau_ngan_va_cau_dai():
    # Xấp xỉ theo số ký tự, KHÔNG phải bảo đảm về mili giây: độ dài thật đo
    # lúc dựng tiếng và khác nhau theo giọng. Kiểm ba khoảng ký tự để bắt lỗi
    # soạn thiếu nguyên một rổ. Số ms thật kiểm bằng scripts/do_cau_dem.py.
    cau = nap(DUONG_DAN_MAC_DINH).cau
    assert sum(1 for c in cau if len(c.text) <= 20) >= 8
    assert sum(1 for c in cau if 20 < len(c.text) < 55) >= 8
    assert sum(1 for c in cau if len(c.text) >= 55) >= 10


def test_lay_kho_nho_ket_qua():
    assert lay_kho() is lay_kho()
