"""Chọn đoạn mẫu cho một giọng mới, từ bản ghi dài.

VÌ SAO CÓ. Bên A báo chữ "ạ" nghe không tự nhiên (17-08-2026). Gốc: đoạn mẫu
đang dùng là giọng KỂ CHUYỆN, không có lấy một chữ "ạ" nào trong suốt 20 phút
bản ghi, nên F5 phải tự bịa ngữ điệu cho tiểu từ. Chữa bằng tay mất ~2 giờ và
mắc 3 lỗi; mỗi lỗi đó thành một test ở đây.

Số dùng làm ngưỡng đều là số ĐO ĐƯỢC trên cùng một người, cùng một bản ghi:

    độ dài đoạn mẫu   ->  tông lệch đầu ra   WER
    8,88s                 35,0%              4,0%
    6,42s                 27,0%
    4,94s                 11,8%              160%   <- cắt vào GIỮA TỪ
    3,18s                 14,0%              0,0%   <- đang chạy thật
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from backend.services.chon_doan_mau import (DAI_MAX, DAI_MIN, LECH_LOI_TRAN,
                                            cer, cham_diem, tach_don_vi,
                                            xep_hang)

SR = 24000


# --- dựng tín hiệu -----------------------------------------------------

def tieng(ms, dbfs=-16.0, he_so_dinh_db=14.0, hat=1):
    """Giả tiếng nói với HỆ SỐ ĐỈNH THẬT.

    Sóng sin có hệ số đỉnh 3dB, mảnh tiếng thật đo được 10-19dB. Dựng test bằng
    sin thì bỏ lọt đúng loại lỗi đã mắc ở `can_do_to`: hàm gần như không làm gì
    trên tiếng thật mà test vẫn xanh. Xem `tests/test_can_do_to.py`.
    """
    n = int(SR * ms / 1000)
    rng = np.random.default_rng(hat)
    x = rng.normal(0, 1, n)
    x = x / np.sqrt((x ** 2).mean())
    x[:: max(1, n // 40)] = 10 ** (he_so_dinh_db / 20)
    x = x / np.sqrt((x ** 2).mean())
    return (x * 10 ** (dbfs / 20)).astype(np.float32)


def tu(chu, a, b):
    return {"word": chu, "start": a, "end": b}


def doan(*words):
    return [{"text": " ".join(w["word"] for w in words), "words": list(words)}]


def deu(chu_list, buoc=0.35, tu_luc=0.0):
    """Chuỗi từ nối tiếp nhau, mỗi từ `buoc` giây."""
    ra, t = [], tu_luc
    for c in chu_list:
        ra.append(tu(c, round(t, 3), round(t + buoc, 3)))
        t += buoc
    return ra


# --- BẪY 1: cắt theo GIÂY đẻ ra chữ ma ---------------------------------
#
# Cắt giữa từ làm STT nghe ra một chữ "không" không hề có ở đầu clip. Dùng clip
# đó làm đoạn mẫu thì F5 đọc ra đúng chữ sai ấy, WER 160%.

def test_moc_cat_luon_roi_dung_RANH_GIOI_TU():
    ws = deu(["Dạ", "em", "chào", "anh", "chị", "mình", "nhé", "hôm", "nay",
              "bên", "em", "có", "chương", "trình", "mới", "ạ"])
    dau = {w["start"] for w in ws}
    cuoi = {w["end"] for w in ws}
    for dv in tach_don_vi(doan(*ws)):
        assert dv["a"] in dau, f"mốc đầu {dv['a']} không phải đầu một từ nào"
        assert dv["b"] in cuoi, f"mốc cuối {dv['b']} không phải cuối một từ nào"


def test_khong_don_vi_nao_DE_LEN_NHAU():
    ws = deu(["t%d" % i for i in range(40)])
    dv = tach_don_vi(doan(*ws))
    for x, y in zip(dv, dv[1:]):
        assert y["a"] >= x["b"], "hai đơn vị chồng lấn -> nghe lặp chữ"


# --- BẪY 2: độ dài ----------------------------------------------------

def test_qua_TRAN_thi_khong_duoc_sinh_ra():
    """Đơn vị dài hơn 5,5s không được đẻ ra ngay từ khâu tách."""
    ws = deu(["t%d" % i for i in range(60)])
    for dv in tach_don_vi(doan(*ws)):
        assert dv["dai"] <= DAI_MAX + 1e-6, f"đơn vị {dv['dai']:.2f}s vượt trần"


def test_qua_TRAN_thi_bi_LOAI_o_khau_xep_hang():
    """Có đường khác đưa ứng viên vào (người dùng tự chỉnh mốc) - vẫn phải chặn.

    8,88s là đoạn mẫu cũ thật, đo ra tông lệch 35,0%.
    """
    ra = xep_hang([_ung_vien(dai=8.88), _ung_vien(dai=3.18)])
    assert [round(u["dai"], 2) for u in ra] == [3.18], "clip 8,88s vẫn lọt"


def test_qua_NGAN_cung_bi_loai():
    ra = xep_hang([_ung_vien(dai=1.4), _ung_vien(dai=3.18)])
    assert [round(u["dai"], 2) for u in ra] == [3.18]


# --- BẪY 3: lời lệch tiếng --------------------------------------------
#
# Ứng viên `heu_a6_50` lệch lời 12,5% -> WER đầu ra 160%, tiếng vỡ hoàn toàn.
# F5 canh chữ theo ref_text rồi sinh tiếp trên nền ref_audio; chỗ lệch không
# biến mất mà rò sang phần sinh.

def test_LECH_LOI_qua_nguong_thi_bi_loai():
    ra = xep_hang([_ung_vien(lech_loi=0.125), _ung_vien(lech_loi=0.0)])
    assert len(ra) == 1, "clip lệch lời 12,5% vẫn được xếp hạng"
    assert ra[0]["lech_loi"] == 0.0


def test_nguong_lech_loi_dung_hang_so_da_chot():
    assert xep_hang([_ung_vien(lech_loi=LECH_LOI_TRAN)]), "đúng ngưỡng phải ĐẠT"
    assert not xep_hang([_ung_vien(lech_loi=LECH_LOI_TRAN + 0.001)])


def test_cer_do_dung_ti_le_ky_tu_sai():
    assert cer("dạ vâng ạ", "dạ vâng ạ") == 0.0
    assert cer("dạ vâng ạ", "") == 1.0
    assert 0.0 < cer("dạ vâng ạ", "dạ vâng à") < 0.3


def test_cer_BO_QUA_dau_cau_va_hoa_thuong():
    """STT trả về không dấu câu, lời người ghi thì có - đó không phải lệch."""
    assert cer("Dạ vâng, em nghe anh.", "dạ vâng em nghe anh") == 0.0


# --- BẪY 4: xếp hạng ---------------------------------------------------

def test_ket_bang_TIEU_TU_duoc_xep_TREN():
    """Đây đúng là gốc lỗi bên A báo. Trong 20 phút bản ghi chỉ có 3 chỗ như
    vậy, nên nó phải là trọng số cao nhất chứ không phải điểm cộng cho vui."""
    ra = xep_hang([
        _ung_vien(loi="bên em vừa ra chương trình mới cho khách hàng"),
        _ung_vien(loi="bên em vừa ra chương trình mới cho khách hàng ạ"),
    ])
    assert ra[0]["loi"].endswith("ạ"), "câu kết bằng tiểu từ không được xếp trên"


def test_it_THOI_hon_thi_xep_tren():
    """Tương quan +0,93 giữa độ thổi của đoạn mẫu và độ thổi đầu ra."""
    ra = xep_hang([_ung_vien(h1h2=8.0, loi="a"), _ung_vien(h1h2=2.0, loi="b")])
    assert ra[0]["loi"] == "b"


def test_NEN_NHIEU_thap_hon_thi_xep_tren():
    ra = xep_hang([_ung_vien(nen=-45.1, loi="a"), _ung_vien(nen=-68.0, loi="b")])
    assert ra[0]["loi"] == "b"


def test_moi_ung_vien_deu_co_DIEM_va_sap_GIAM_DAN():
    ra = xep_hang([_ung_vien(h1h2=h, loi=str(h)) for h in (2.0, 9.0, 5.0)])
    assert all("diem" in u for u in ra)
    assert [u["diem"] for u in ra] == sorted((u["diem"] for u in ra), reverse=True)


def test_KHONG_xep_hang_bang_do_troi_cao_do():
    """Tương quan với đầu ra chỉ +0,48, và `heu_a6` phá quy luật: clip tự trôi
    47,7% mà đầu ra chỉ trôi 6%. Đo thì cứ đo, nhưng đừng lấy làm điểm."""
    ra = xep_hang([_ung_vien(f0_dai=90.0, loi="a"), _ung_vien(f0_dai=10.0, loi="b")])
    assert ra[0]["diem"] == ra[1]["diem"], "đã lấy độ trôi cao độ ra chấm điểm"


# --- đo trên tiếng thật ------------------------------------------------

def test_cham_diem_tra_du_khoa():
    d = cham_diem(tieng(3200), SR, "Dạ vâng em nghe anh ạ", "dạ vâng em nghe anh ạ")
    for k in ("dai", "lech_loi", "h1h2", "nen", "f0_tv", "f0_dai",
              "co_tieu_tu", "le_phep"):
        assert k in d, f"thiếu khoá {k}"


def test_cham_diem_do_dung_DO_DAI():
    assert abs(cham_diem(tieng(3200), SR, "a", "a")["dai"] - 3.2) < 0.01


def test_nhan_ra_TIEU_TU_cuoi_cau():
    assert cham_diem(tieng(3200), SR, "em nghe anh ạ", "em nghe anh ạ")["co_tieu_tu"]
    assert cham_diem(tieng(3200), SR, "em nghe anh nhé", "em nghe anh nhé")["co_tieu_tu"]
    assert not cham_diem(tieng(3200), SR, "em nghe anh", "em nghe anh")["co_tieu_tu"]


def test_KHONG_nham_tieu_tu_o_GIUA_cau():
    """"ạ" giữa câu không cho ngữ điệu kết - chỉ chữ CUỐI mới tính."""
    d = cham_diem(tieng(3200), SR, "dạ anh cho em hỏi", "dạ anh cho em hỏi")
    assert not d["co_tieu_tu"]


def test_nhan_ra_giong_LE_PHEP():
    assert cham_diem(tieng(3200), SR, "dạ em chào anh", "dạ em chào anh")["le_phep"]
    assert not cham_diem(tieng(3200), SR, "hôm qua trời mưa to", "hôm qua trời mưa to")["le_phep"]


def test_NEN_NHIEU_cang_lang_cang_thap():
    to = cham_diem(tieng(3200, dbfs=-16.0), SR, "a", "a")["nen"]
    nho = cham_diem(tieng(3200, dbfs=-40.0), SR, "a", "a")["nen"]
    assert nho < to, "nền nhiễu không theo mức tín hiệu"


# --- rìa ---------------------------------------------------------------

def test_khong_co_tu_nao_thi_tra_rong():
    assert tach_don_vi([]) == []
    assert tach_don_vi([{"text": "", "words": []}]) == []


def test_ban_ghi_qua_NGAN_thi_khong_co_ung_vien():
    assert tach_don_vi(doan(*deu(["a", "b"]))) == []


def test_xep_hang_rong():
    assert xep_hang([]) == []


def test_gop_TU_NHIEU_DOAN_stt_lien_nhau():
    """Whisper trả về nhiều đoạn; câu hay nằm vắt qua ranh giới đoạn."""
    a = deu(["Dạ", "em", "chào", "anh"], tu_luc=0.0)
    b = deu(["bên", "em", "có", "chương", "trình", "mới", "ạ"], tu_luc=1.4)
    dv = tach_don_vi([{"text": "x", "words": a}, {"text": "y", "words": b}])
    assert dv, "không gom được qua ranh giới đoạn STT"
    assert any(d["loi"].endswith("ạ") for d in dv)


# --- tiện ích cho test -------------------------------------------------

def _ung_vien(dai=3.5, lech_loi=0.0, h1h2=4.0, nen=-60.0, f0_tv=200.0,
              f0_dai=30.0, loi="bên em hỗ trợ anh chị"):
    return {"a": 0.0, "b": dai, "dai": dai, "loi": loi, "lech_loi": lech_loi,
            "h1h2": h1h2, "nen": nen, "f0_tv": f0_tv, "f0_dai": f0_dai,
            "co_tieu_tu": loi.strip().split()[-1] in ("ạ", "nhé", "nha", "nhỉ"),
            "le_phep": any(t in loi.split() for t in ("dạ", "em", "anh", "chị"))}


def test_hang_so_dung_nhu_da_chot():
    assert (DAI_MIN, DAI_MAX) == (3.0, 5.5)
    assert LECH_LOI_TRAN == 0.05


# --- chia cửa sổ gửi STT -----------------------------------------------
#
# Bản ghi 20 phút ~200MB, phải chia mới gửi được cho Whisper. Chia theo GIÂY
# CHẴN thì ranh giới rơi vào giữa từ (đúng lỗi đã làm hỏng `heu_a6_50`) và câu
# vắt qua chỗ đó mất luôn.

def test_cua_so_PHU_KIN_khong_ho_khong_chong():
    from backend.services.chon_doan_mau import cua_so_ngat
    x = np.concatenate([tieng(2000, hat=i) if i % 2 else np.zeros(int(SR * 0.4), np.float32)
                        for i in range(60)])
    cs = cua_so_ngat(x, SR, dai_toi_da=8.0)
    assert cs[0][0] == 0
    assert cs[-1][1] == len(x)
    for p, q in zip(cs, cs[1:]):
        assert p[1] == q[0], "cửa sổ hở hoặc chồng lấn -> mất chữ ở ranh giới"


def test_cua_so_khong_vuot_TRAN():
    from backend.services.chon_doan_mau import cua_so_ngat
    x = np.concatenate([tieng(2000, hat=i) if i % 2 else np.zeros(int(SR * 0.4), np.float32)
                        for i in range(60)])
    for a, b in cua_so_ngat(x, SR, dai_toi_da=8.0):
        assert (b - a) / SR <= 8.0 + 1e-6


def test_cat_DUNG_CHO_IM_chu_khong_phai_giay_chan():
    """Chỗ cắt phải rơi vào khoảng lặng, không rơi giữa tiếng."""
    from backend.services.chon_doan_mau import cua_so_ngat
    khoi = [tieng(3000, hat=i) if i % 2 else np.zeros(int(SR * 1.0), np.float32)
            for i in range(20)]
    x = np.concatenate(khoi)
    for a, b in cua_so_ngat(x, SR, dai_toi_da=9.0)[:-1]:
        quanh = x[max(0, b - int(SR * 0.05)):b + int(SR * 0.05)]
        assert np.abs(quanh).max() < 0.05, f"cắt tại {b/SR:.2f}s rơi vào giữa tiếng"


def test_ban_ghi_ngan_hon_cua_so_thi_de_nguyen():
    from backend.services.chon_doan_mau import cua_so_ngat
    x = tieng(3000)
    assert cua_so_ngat(x, SR, dai_toi_da=40.0) == [(0, len(x))]


def test_cua_so_ban_ghi_rong():
    from backend.services.chon_doan_mau import cua_so_ngat
    assert cua_so_ngat(np.array([], dtype=np.float32), SR) == []


def test_quet_nang_luong_theo_LO_khong_lech_o_ranh_gioi():
    """Quét theo lô để khỏi ngốn bộ nhớ trên bản ghi 20 phút (~29 triệu mẫu).
    Tín hiệu dưới đây dài hơn một lô, nên nó đi qua đúng chỗ ghép lô."""
    from backend.services.chon_doan_mau import _LO_MAU, cua_so_ngat
    khoi = [tieng(1500, hat=i) if i % 2 else np.zeros(int(SR * 0.5), np.float32)
            for i in range(80)]
    x = np.concatenate(khoi)
    assert len(x) > _LO_MAU, "tín hiệu test ngắn hơn một lô - không kiểm được gì"
    cs = cua_so_ngat(x, SR, dai_toi_da=9.0)
    assert cs[0][0] == 0 and cs[-1][1] == len(x)
    for a, b in cs[:-1]:
        quanh = x[max(0, b - int(SR * 0.05)):b + int(SR * 0.05)]
        assert np.abs(quanh).max() < 0.05, f"cắt tại {b/SR:.2f}s rơi vào giữa tiếng"
