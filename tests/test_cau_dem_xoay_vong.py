"""Hỏi cùng chủ đề nhiều lần thì phải nghe các câu mở đầu KHÁC nhau.

VÌ SAO CÓ FILE NÀY. Cuộc gọi thật 06b8aae1 (11-09-2026 18:31): ba lượt hỏi hạn
mức, cả ba đều "Dạ hạn mức bên em thì,"; cuộc a819e352 ngay trước: hai lượt liền
"Dạ em nói rõ cho anh chị phần này luôn nhé,". Người dùng: "cứ lặp đi lặp lại
câu đệm".

Gốc: `pick_filler` xếp hạng ứng viên theo khoá "số_mẩu|id_đuôi" để xoay vòng,
nhưng `_send_filler` cộng lượt dùng vào `dem[id_duoi]` - từ khi bỏ kho câu đuôi
(06-09) id_đuôi luôn là "", nên số đếm của từng clip KHÔNG BAO GIỜ tăng. Mẩu mở
đầu nào cũng ngắn hơn quãng chờ cần che (~2 giây), `chon` rơi xuống tầng "không
câu nào đủ dài -> lấy câu DÀI NHẤT" với mọi clip cùng số đếm 0: luôn cùng một câu.
"""
import inspect
import struct
import types

from backend.services.tts_service import F5TTSService

MO_DAU = ("Dạ về hạn mức vay thì,", "Dạ hạn mức bên em thì,", "Dạ về mức vay được,")


def _wav(ms: int) -> bytes:
    sr, n = 24000, 24 * ms
    return (b"RIFF" + struct.pack("<I", 36 + 2 * n) + b"WAVEfmt " +
            struct.pack("<IHHIIHH", 16, 1, 1, sr, 2 * sr, 2, 16) +
            b"data" + struct.pack("<I", 2 * n) + b"\0" * (2 * n))


def _dich_vu():
    svc = F5TTSService.__new__(F5TTSService)
    svc._giong_thuc = lambda v=None: "g"
    svc._filler_cache, svc._filler_ms = {}, {}
    for i, ms in enumerate((1100, 1250, 1000)):
        k = ("g", "hoi_han_muc", i, "")
        svc._filler_cache[k], svc._filler_ms[k] = _wav(ms), float(ms)
    kho = types.SimpleNamespace(duoi=(), tinh_huong=(
        types.SimpleNamespace(id="hoi_han_muc", mo_dau=MO_DAU),))
    return svc, kho


def _dich_vu_co_nhom_chung(ms_chu_de=(1100, 1250, 1000),
                            ms_chung=(1990, 2030, 2217)):
    svc, kho_cu = _dich_vu()
    svc._filler_cache, svc._filler_ms = {}, {}
    chung = ("Dạ vâng,", "Vâng ạ,", "Dạ vâng ạ,")
    for th, cac_ms in (("hoi_han_muc", ms_chu_de), ("chung", ms_chung)):
        for i, ms in enumerate(cac_ms):
            k = ("g", th, i, "")
            svc._filler_cache[k], svc._filler_ms[k] = _wav(ms), float(ms)
    kho = types.SimpleNamespace(duoi=(), tinh_huong=(
        types.SimpleNamespace(id="hoi_han_muc", mo_dau=MO_DAU),
        types.SimpleNamespace(id="chung", mo_dau=chung),
    ))
    return svc, kho


def test_ba_luot_cung_chu_de_ra_ba_cau_mo_dau_khac_nhau():
    """Cả ba clip đều ngắn hơn quãng cần che 2000ms - đúng tình trạng máy thật."""
    svc, kho = _dich_vu()
    dem: dict = {}
    nghe = []
    for _ in range(3):
        wav, _, th = svc.pick_filler(kho, "g", min_ms=2000, dem=dem,
                                     id_tinh_huong="hoi_han_muc")
        assert wav and th == "hoi_han_muc"
        nghe.append(svc._filler_text_cuoi)
    assert sorted(nghe) == sorted(MO_DAU), nghe


def test_het_mot_vong_moi_quay_lai():
    svc, kho = _dich_vu()
    dem: dict = {}
    nghe = []
    for _ in range(6):
        svc.pick_filler(kho, "g", min_ms=2000, dem=dem, id_tinh_huong="hoi_han_muc")
        nghe.append(svc._filler_text_cuoi)
    assert sorted(nghe[:3]) == sorted(MO_DAU) and sorted(nghe[3:]) == sorted(MO_DAU), nghe


def test_dem_luot_dung_chi_o_mot_cho():
    """Hai nơi cùng giữ sổ đếm với hai kiểu khoá chính là cách lỗi này sinh ra."""
    from backend.pipeline.streaming_pipeline import StreamingPipeline
    src = inspect.getsource(StreamingPipeline._send_filler)
    assert "dem[id_duoi]" not in src, "_send_filler còn tự đếm theo id_duoi"


def test_chu_de_ngan_thi_roi_sang_nhom_chung_du_dai():
    """Số đo máy thật: hạn mức <=1,25s, nhóm chung gần 2-2,22s."""
    svc, kho = _dich_vu_co_nhom_chung()
    _, _, th = svc.pick_filler(kho, "g", min_ms=1800, dem={},
                               id_tinh_huong="hoi_han_muc")
    assert th == "chung"


def test_chu_de_du_dai_van_duoc_uu_tien():
    svc, kho = _dich_vu_co_nhom_chung(ms_chu_de=(1900, 2050, 2200))
    _, _, th = svc.pick_filler(kho, "g", min_ms=1800, dem={},
                               id_tinh_huong="hoi_han_muc")
    assert th == "hoi_han_muc"


def test_khong_nhom_nao_du_thi_chi_xoay_cac_cau_gan_dai_nhat():
    svc, kho = _dich_vu_co_nhom_chung()
    dem, nghe = {}, []
    for _ in range(6):
        svc.pick_filler(kho, "g", min_ms=2700, dem=dem,
                        id_tinh_huong="hoi_han_muc")
        nghe.append(svc._filler_text_cuoi)
    assert len(set(nghe[:3])) == 3
    assert set(nghe) == {
        "Dạ vâng,",
        "Vâng ạ,",
        "Dạ vâng ạ,",
    }


def test_chu_de_gan_dai_bang_nhom_chung_thi_giu_chu_de():
    """13-09-2026: nhóm chung có câu dài 1-1,3s ngang câu chủ đề. Chủ đề ngắn hơn
    không quá 300ms thì phải giữ chủ đề - khách hỏi hạn mức mà nghe "Dạ em trả
    lời anh chị luôn ạ," là mất độ đúng ý chỉ để đổi vài trăm ms."""
    svc, kho = _dich_vu_co_nhom_chung(ms_chu_de=(1100, 1250, 1000),
                                       ms_chung=(530, 1150, 1300))
    dem = {}
    for _ in range(6):
        _, _, th = svc.pick_filler(kho, "g", min_ms=1800, dem=dem,
                                   id_tinh_huong="hoi_han_muc")
        assert th == "hoi_han_muc"


def test_khong_ro_chu_de_thi_dung_cau_chung_dai():
    """Không nhận ra chủ đề: lấy câu chung dài, không rơi xuống "Dạ," 0,27s."""
    svc, kho = _dich_vu_co_nhom_chung(ms_chung=(270, 570, 1150, 1300))
    kho.tinh_huong[1].mo_dau = ("Dạ,", "Dạ vâng,", "Dạ em trả lời anh chị ạ,",
                                "Dạ em trả lời anh chị luôn ạ,")
    nghe = set()
    for _ in range(6):
        svc.pick_filler(kho, "g", min_ms=1800, dem={}, id_tinh_huong=None)
        nghe.add(svc._filler_text_cuoi)
    assert nghe <= {"Dạ em trả lời anh chị ạ,", "Dạ em trả lời anh chị luôn ạ,"}, nghe
