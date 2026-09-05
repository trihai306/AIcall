"""Vòng đệm giữ tiếng TRƯỚC lúc VAD nhận ra khách bắt đầu nói.

Vì sao cần: cả hai đường thu đều mở lượt bằng "N khung liên tiếp vượt ngưỡng",
rồi VỨT mọi thứ trước đó. Phụ âm đầu (h, th, l, c) năng lượng thấp nên nằm dưới
ngưỡng và mất trắng. Đo 05-09-2026 (`scripts/do_cut_dau_cau.py`, 5 câu qua
PhoWhisper-medium): cắt 200ms đầu -> CER 0,334; cắt 400ms -> 0,466; và
"lãi suất bao nhiêu" thành đúng một chữ "nhiều".

Đệm KHÔNG được dài tuỳ ý: phần đệm chứa tiếng AI vọng lại, và Whisper chép luôn
lời AI thành lời khách. Đo (`scripts/do_dem_truoc.py`, vọng 30%): +300ms cho CER
0,033 nhưng +500ms cho 0,481 (`năm trăm triệu đồng lãi suất bao nhiêu`).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.services.dem_truoc import DEM_TRUOC_MS, DemTruoc


def test_so_khung_lam_tron_len():
    """Thiếu một khung là thiếu đúng phần phụ âm đầu - phải làm tròn LÊN."""
    assert DemTruoc(300, khung_ms=20).so_khung == 15
    assert DemTruoc(300, khung_ms=128).so_khung == 3   # 2,34 -> 3
    assert DemTruoc(256, khung_ms=128).so_khung == 2


def test_luon_giu_it_nhat_mot_khung():
    assert DemTruoc(0, khung_ms=20).so_khung == 1
    assert DemTruoc(5, khung_ms=128).so_khung == 1


def test_giu_dung_thu_tu_thoi_gian():
    d = DemTruoc(60, khung_ms=20)          # 3 khung
    for x in (b"aa", b"bb", b"cc"):
        d.them(x)
    assert d.lay() == b"aabbcc"


def test_khung_cu_bi_day_ra():
    d = DemTruoc(40, khung_ms=20)          # 2 khung
    for x in (b"aa", b"bb", b"cc"):
        d.them(x)
    assert d.lay() == b"bbcc"


def test_KHONG_xoa_khi_gap_khung_im():
    """Đây là khác biệt cốt lõi với mã cũ.

    `xuLyCatLoi` cũ xoá sạch đệm ở BẤT KỲ khung nào tụt dưới ngưỡng, nên chỉ giữ
    được chuỗi liên tục cuối cùng. Mà giọng nói luôn có chỗ trũng giữa các âm
    tiết, nên phần đầu câu bị vứt. Vòng đệm này không biết tới ngưỡng.
    """
    d = DemTruoc(60, khung_ms=20)
    d.them(b"to")          # có tiếng
    d.them(b"im")          # chỗ trũng - mã cũ xoá sạch ở đây
    d.them(b"to")
    assert d.lay() == b"toimto"


def test_xoa_thi_rong():
    d = DemTruoc(60, khung_ms=20)
    d.them(b"aa")
    d.xoa()
    assert d.lay() == b""


def test_lay_khong_lam_rong_dem():
    """Lấy ra rồi vẫn phải giữ: lượt sau còn cần phần đệm của chính nó."""
    d = DemTruoc(40, khung_ms=20)
    d.them(b"aa")
    assert d.lay() == b"aa"
    assert d.lay() == b"aa"


def test_moc_mac_dinh_nam_trong_vung_da_do_an_toan():
    """300ms: đo được vọng AI 30% cho CER 0,033. 500ms cho 0,481 - đừng nới."""
    assert 200 <= DEM_TRUOC_MS <= 400


def test_dem_dai_hon_lich_su_thi_chi_giu_phan_moi():
    d = DemTruoc(40, khung_ms=20)          # 2 khung
    for i in range(50):
        d.them(bytes([i]))
    assert d.lay() == bytes([48, 49])


# --- Nối vào đường điện thoại -------------------------------------------
#
# `_read_loop` cần thiết bị + pipeline + session thật nên không dựng thể được;
# soi mã nguồn theo đúng nếp của `test_dem_doi_khung.py`.

def _nguon_read_loop() -> str:
    import inspect
    from backend.services import phone_call_service as pcs
    return inspect.getsource(pcs.PhoneCallBridge._read_loop)


def test_phone_nap_vong_dem_TRUOC_nhanh_mo_luot():
    """Phải nạp ở MỌI khung, kể cả khung im.

    Nạp bên trong `if not speaking:` thì khung im không vào đệm, mà chỗ trũng
    giữa hai âm tiết đúng là thứ cần giữ.
    """
    n = _nguon_read_loop()
    i_nap = n.find("dem_truoc.them(")
    i_nhanh = n.find("if not speaking:")
    assert i_nap != -1, "không thấy chỗ nạp vòng đệm trong `_read_loop`"
    assert i_nhanh != -1
    assert i_nap < i_nhanh, "vòng đệm phải được nạp TRƯỚC nhánh mở lượt"


def test_phone_mo_luot_lay_ca_vong_dem_khong_phai_moi_khung_hien_tai():
    """Chỗ chữa "mất đầu câu": trước đây bắt đầu đúng từ khung hiện tại, tức
    bỏ luôn 80ms đã dùng để dò (`VAD_ON_FRAMES`) lẫn phụ âm đầu dưới ngưỡng."""
    n = _nguon_read_loop()
    i = n.find("tieng_8k.clear()")
    assert i != -1
    sau = n[i:i + 400]
    assert "dem_truoc.lay()" in sau, "mở lượt không lấy vòng đệm"
    assert "tieng_8k += frame" not in sau, (
        "vẫn còn cộng riêng `frame` - vòng đệm đã chứa nó rồi, cộng nữa là lặp")


def test_phone_dung_khung_20ms_nen_du_so_khung():
    """300ms ở khung 20ms là 15 khung, thừa sức phủ 80ms cửa sổ dò."""
    from backend.services import phone_call_service as pcs
    d = DemTruoc(DEM_TRUOC_MS, pcs.FRAME_MS)
    assert d.so_khung * pcs.FRAME_MS >= 300
    assert d.so_khung > pcs.VAD_ON_FRAMES, (
        "vòng đệm phải DÀI HƠN cửa sổ dò, không thì chỉ chứa đúng những khung "
        "đã vượt ngưỡng và không mang thêm được gì")
