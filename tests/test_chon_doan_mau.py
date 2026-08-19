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

from backend.services.chon_doan_mau import (DAI_MAX, DAI_MIN, LECH_GIUA_TRAN,
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


def test_moi_don_vi_deu_bat_dau_o_MOT_TU():
    """Không đòi phải là đầu câu.

    Bản đầu bắt buộc đầu câu, và trên bản ghi thật nó rơi từ 355 xuống 84 đơn vị
    rồi mất luôn đoạn hay nhất - vì mốc chữ của Whisper không có khe nào, dấu
    chấm là tín hiệu duy nhất, mà giữa dòng nói liên tục thì rất ít dấu chấm.
    Chỗ bắt đầu xấu để khâu cho STT nghe lại clip loại, đừng loại từ khâu tách.
    """
    ws = deu(["m%d" % i for i in range(30)])
    dau = {w["start"] for w in ws}
    for d in tach_don_vi(doan(*ws)):
        assert d["a"] in dau, f"bắt đầu ở {d['a']}s - không trùng đầu từ nào"


def test_co_de_len_nhau_thi_KHONG_TRUNG_HET_khoa():
    """Ứng viên được phép chồng lấn (mỗi chỗ bắt đầu cho một clip khác nhau),
    nhưng không được có hai cái y hệt nhau."""
    ws = deu(["m%d" % i for i in range(30)])
    dv = tach_don_vi(doan(*ws))
    khoa = [(d["a"], d["b"]) for d in dv]
    assert len(khoa) == len(set(khoa)), "có ứng viên trùng khít nhau"


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

def test_ca_heu_a6_50_bi_day_XUONG_DUOI():
    """Ca hỏng thật: clip cắt cụt nên STT nghe thêm chữ "không" ở ĐẦU.

    Ngày xưa nó cho WER 160%, nhưng vì `.txt` khi đó ghi lời SAI. Giờ `.txt` lấy
    từ chính STT nghe clip nên khớp tiếng theo cấu tạo - lỗi ấy không tái diễn
    được. Còn lại chỉ là cắt cụt âm: đáng xếp dưới, chưa đủ bằng chứng để vứt.
    """
    xau = _ung_vien(loi="em thấy tự ti và bản thân mình tệ quá chị ạ")
    xau["nghe_lai"] = "không em thấy tự ti và bản thân mình tệ quá chị ạ"
    xau["lech_loi"] = 0.125
    tot = _ung_vien(loi="em thấy tự ti và bản thân mình tệ quá chị ạ")
    tot["nghe_lai"] = "em thấy tự ti và bản thân mình tệ quá chị ạ"
    ra = xep_hang([xau, tot])
    assert ra[0]["lech_loi"] == 0.0


def test_nguong_lech_GIUA_dung_hang_so_da_chot():
    u = _ung_vien(loi="a b c d e", lech_loi=LECH_GIUA_TRAN)
    u["nghe_lai"] = "a b x d e"                      # lệch ở GIỮA
    assert xep_hang([u]), "đúng ngưỡng phải ĐẠT"
    u2 = dict(u, lech_loi=LECH_GIUA_TRAN + 0.001)
    assert not xep_hang([u2])


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
    assert LECH_GIUA_TRAN == 0.25


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


# --- đo cao độ ---------------------------------------------------------

def _chuoi_xung(f0, ms, sr=SR):
    """Chuỗi xung tần số `f0` - dạng sóng thô nhưng cao độ thì biết chắc."""
    n = int(sr * ms / 1000)
    x = np.zeros(n, dtype=np.float32)
    x[:: max(1, int(sr / f0))] = 1.0
    return x * 0.5


def test_do_dung_CAO_DO_giong_nu():
    """Giọng nữ ~200Hz. Sai quãng tám ở đây là bảng số đo thành vô nghĩa."""
    d = cham_diem(_chuoi_xung(200, 3200), SR, "a", "a")
    assert abs(d["f0_tv"] - 200) < 12, f"đo ra {d['f0_tv']}Hz thay vì 200Hz"


def test_do_dung_CAO_DO_giong_nam_tram():
    """Giọng nam trầm ~95Hz - phải không bị bắt nhầm thành bội 2 (190Hz)."""
    d = cham_diem(_chuoi_xung(95, 3200), SR, "a", "a")
    assert abs(d["f0_tv"] - 95) < 8, f"đo ra {d['f0_tv']}Hz thay vì 95Hz"


def test_cao_do_KHONG_lech_khi_doi_tan_so_lay_mau():
    """Bản ghi nguồn hay ở 44,1 hoặc 48kHz chứ không phải 24kHz."""
    for sr in (16000, 44100, 48000):
        d = cham_diem(_chuoi_xung(180, 3200, sr), sr, "a", "a")
        assert abs(d["f0_tv"] - 180) < 12, f"{sr}Hz: đo ra {d['f0_tv']}Hz"


# --- tiểu từ THẬT, không phải chữ trùng âm --------------------------------
#
# Chạy thật trên bản ghi 20 phút (18-08) tách được 349 đoạn nhưng cả 4 đoạn lọt
# vào chung kết đều là NHẬN NHẦM:
#
#     "rất là nhiều lần mình những cái câu chuyện đó ấy"
#     "kể cho mình nghe ... và nếu có thể thì bạn ấy"      <- cắt giữa mệnh đề
#     "dạo này trong máy khác à đấy thì lúc đó ... rằng là à"
#
# "ấy" trong "bạn ấy" là đại từ chỉ định, "à" là tiếng ngập ngừng - không cái
# nào cho ngữ điệu kết cả. Chúng chiếm hết suất kiểm lời nên đoạn tốt thật
# ("...bản thân mình tệ quá chị ạ") bị đẩy ra ngoài.
#
# Bộ TIEU_TU_CUOI_VE bên `text_chunker` rộng hơn là ĐÚNG cho việc của nó (chèn
# nhịp nghỉ - nhận rộng thì cùng lắm nghỉ thừa). Ở đây nhận rộng là hỏng.

def test_AY_khong_phai_tieu_tu():
    d = cham_diem(tieng(3200), SR, "mình thấy bạn ấy", "mình thấy bạn ấy")
    assert not d["co_tieu_tu"], '"bạn ấy" bị nhận nhầm là tiểu từ lễ phép'


def test_A_ngap_ngung_khong_phai_tieu_tu():
    d = cham_diem(tieng(3200), SR, "lúc đó mình mới nhận ra rằng là à",
                  "lúc đó mình mới nhận ra rằng là à")
    assert not d["co_tieu_tu"], '"à" ngập ngừng bị nhận nhầm là tiểu từ'


def test_A_LE_PHEP_van_duoc_nhan():
    d = cham_diem(tieng(3200), SR, "bản thân mình tệ quá chị ạ",
                  "bản thân mình tệ quá chị ạ")
    assert d["co_tieu_tu"], 'mất luôn "ạ" thật - siết quá tay'


def test_KHONG_thuong_cho_cat_giua_menh_de():
    """Kết bằng tiểu từ chỉ đáng thưởng khi chỗ đó THẬT SỰ hết câu.

    Nếu không, bộ tách đi tìm chữ trùng âm ở giữa câu để cắt vào - đúng thứ đã
    xảy ra với "và nếu có thể thì bạn ấy".
    """
    from backend.services.chon_doan_mau import _diem_ket
    ws = deu(["a"] * 5) + [tu("ạ", 1.75, 2.05), tu("rồi", 2.05, 2.35)]
    assert _diem_ket(ws, 5) == 0.0, "thưởng cho tiểu từ nằm giữa câu"


def test_CO_thuong_khi_tieu_tu_o_cuoi_cau():
    from backend.services.chon_doan_mau import _diem_ket
    ws = deu(["a"] * 5) + [tu("ạ.", 1.75, 2.05), tu("Dạ", 2.6, 2.9)]
    assert _diem_ket(ws, 5) > 0.0


def test_tach_chon_HET_CAU_chu_khong_chon_chu_trung_am():
    """Trong cùng một cửa sổ có cả hai chỗ kết - phải lấy chỗ hết câu thật."""
    ws = (deu(["m%d" % i for i in range(10)])                    # 0,00-3,50
          + [tu("ấy", 3.50, 3.80)]                               # giữa mệnh đề
          + [tu("nữa", 3.80, 4.10), tu("ạ.", 4.10, 4.40)]        # hết câu thật
          + [tu("Dạ", 5.00, 5.30)])
    dv = tach_don_vi(doan(*ws))
    assert dv and dv[0]["b"] == 4.40, f"cắt ở {dv[0]['b'] if dv else '?'} thay vì 4.40"


# --- mốc chữ của Whisper KHÔNG có khe -------------------------------------
#
# Đổ mốc từng chữ của bản ghi thật (18-08) ra xem thì mọi chữ đều nối liền nhau,
# khe đúng 0ms:
#
#     533.49-534.03  nào.    khe sau 0ms
#     534.03-534.81  chỉ     khe sau 0ms
#     536.87-537.21  em      khe sau 0ms
#
# Tức phép dò "hết câu bằng quãng nghỉ" CHƯA BAO GIỜ chạy trong một đoạn STT -
# chỉ dấu chấm là tín hiệu thật. Siết chỗ bắt đầu chỉ theo dấu chấm thì rơi từ
# 355 xuống 84 đơn vị và mất luôn đoạn tốt nhất ("em thấy tự ti..."), vì trước
# chữ "em" không có dấu chấm nào.

def test_van_tach_duoc_khi_moc_chu_KHONG_CO_KHE():
    """Bản ghi thật nối liền chữ - đừng bắt phải có quãng nghỉ mới cho bắt đầu."""
    ws, t = [], 0.0
    for c in "chỉ là mỗi ngày khá là giống nhau em thấy tự ti và bản thân mình tệ quá chị ạ.".split():
        ws.append(tu(c, round(t, 2), round(t + 0.28, 2)))
        t += 0.28                                   # khe 0ms, y như thật
    dv = tach_don_vi(doan(*ws))
    assert dv, "không tách được đơn vị nào khi mốc chữ không có khe"
    assert any(d["loi"].rstrip().endswith("ạ.") for d in dv), \
        "bỏ mất câu kết bằng tiểu từ"


# --- nắn mốc cắt về chỗ lặng THẬT trong sóng âm ---------------------------
#
# Cắt đúng mốc chữ của Whisper là cắt vào giữa âm: clip mở đầu bằng một phụ âm
# cụt, STT nghe lại ra khác, và ứng viên trượt khâu kiểm lời. Đó chính là cách
# đoạn "em thấy tự ti..." bị loại dù nó là đoạn tốt nhất trong cả bản ghi.

def test_nan_moc_ve_cho_LANG_nhat():
    from backend.services.chon_doan_mau import nan_moc
    x = np.concatenate([tieng(500, hat=1), np.zeros(int(SR * 0.12), np.float32),
                        tieng(500, hat=2)])
    goc = int(SR * 0.70)                            # nằm giữa TIẾNG, khe ở 0,50-0,62
    ra = nan_moc(x, SR, goc, cua_ms=150)
    assert abs(ra / SR - 0.70) > 0.02, "không nắn gì cả"
    assert np.abs(x[ra - 240:ra + 240]).max() < 0.05, "nắn vào chỗ vẫn có tiếng"


def test_nan_moc_KHONG_di_qua_xa():
    from backend.services.chon_doan_mau import nan_moc
    x = tieng(2000)
    goc = int(SR * 1.0)
    ra = nan_moc(x, SR, goc, cua_ms=150)
    assert abs(ra - goc) <= int(SR * 0.150) + 1, "nắn vượt quá cửa sổ cho phép"


def test_nan_moc_giu_trong_bien():
    from backend.services.chon_doan_mau import nan_moc
    x = tieng(400)
    assert 0 <= nan_moc(x, SR, 0, cua_ms=150) <= len(x)
    assert 0 <= nan_moc(x, SR, len(x), cua_ms=150) <= len(x)


# --- dẹp ứng viên đè lên nhau ---------------------------------------------
#
# Cho phép bắt đầu ở nhiều chỗ thì cùng một câu đẻ ra chục biến thể lệch nhau
# vài từ. Chạy thật (18-08): 1520 ứng viên, nhưng hai đoạn đứng đầu là CÙNG MỘT
# CÂU ("...góp ý ở dưới phần comment cho mình biết với nhé") chỉ khác chỗ vào.
# Chúng chiếm hết 24 suất kiểm lời nên đoạn hay nhất của cả bản ghi không tới
# lượt - đúng lỗi cũ, chỉ đổi nguyên nhân.

def test_dep_trung_giu_cai_DIEM_CAO_hon():
    from backend.services.chon_doan_mau import dep_de_len
    a = {"a": 30.5, "b": 35.8, "diem": 9.9}
    b = {"a": 31.8, "b": 35.8, "diem": 10.2}        # gần trùng, điểm cao hơn
    ra = dep_de_len([a, b])
    assert len(ra) == 1 and ra[0]["diem"] == 10.2


def test_dep_trung_GIU_doan_o_cho_khac():
    from backend.services.chon_doan_mau import dep_de_len
    ra = dep_de_len([{"a": 30.0, "b": 34.0, "diem": 9.0},
                     {"a": 500.0, "b": 504.0, "diem": 8.0}])
    assert len(ra) == 2, "dẹp nhầm cả đoạn ở chỗ khác trong bản ghi"


def test_dep_trung_de_len_IT_thi_giu_ca_hai():
    from backend.services.chon_doan_mau import dep_de_len
    ra = dep_de_len([{"a": 0.0, "b": 4.0, "diem": 9.0},
                     {"a": 3.5, "b": 7.5, "diem": 8.0}])   # đè 0,5/4,0 = 12%
    assert len(ra) == 2


def test_dep_trung_sap_theo_DIEM_GIAM():
    from backend.services.chon_doan_mau import dep_de_len
    ra = dep_de_len([{"a": 0.0, "b": 4.0, "diem": 5.0},
                     {"a": 100.0, "b": 104.0, "diem": 9.0},
                     {"a": 200.0, "b": 204.0, "diem": 7.0}])
    assert [u["diem"] for u in ra] == [9.0, 7.0, 5.0]


def test_dep_trung_rong():
    from backend.services.chon_doan_mau import dep_de_len
    assert dep_de_len([]) == []


# --- lệch ở ĐÂU quan trọng hơn lệch BAO NHIÊU ------------------------------
#
# Đo 24 ứng viên trên bản ghi thật (18-08): phân bố lệch lời LIÊN TỤC từ 0% tới
# 48%, khe rộng nhất nằm ở 34%->48% - vô dụng làm mốc cắt. Nên mọi ngưỡng phần
# trăm đều tuỳ tiện như nhau.
#
# Nhưng nhìn LÝ DO lệch thì có quy luật rõ:
#
#   tách ra                              STT nghe lại                  bản chất
#   ...thông báo từ TÁP khác nhé         ...từ TAB khác nhé            chính tả
#   HÔM NAY cũng là hơn ba năm           ĐẾN hôm nay cũng là...        mất từ ĐẦU
#   ...mở điện thoại LÊN MỖI SÁNG THÌ    ...lên mỗi sáng               thừa từ CUỐI
#
# 9/24 cái lệch 6-24% đều là mất/thừa đúng một từ ở BIÊN, tức cắt hỏng - đó mới
# là đường dẫn tới WER 160%. Lệch ở GIỮA chỉ là STT nghe nhoè, vô hại.

def test_mat_tu_o_DAU_bi_bat():
    from backend.services.chon_doan_mau import lech_o_bien
    assert lech_o_bien("hôm nay cũng là hơn ba năm rồi mọi người ạ",
                       "đến hôm nay cũng là hơn ba năm rồi mọi người ạ")


def test_thua_tu_o_CUOI_bi_bat():
    from backend.services.chon_doan_mau import lech_o_bien
    assert lech_o_bien("nào đó khi ở mình mở điện thoại lên mỗi sáng thì",
                       "khi ở mình mở điện thoại lên mỗi sáng")


def test_nhoe_CHINH_TA_o_giua_thi_KHONG_bat():
    """"táp"/"tab" là STT nghe nhoè, không phải cắt hỏng - đừng loại oan."""
    from backend.services.chon_doan_mau import lech_o_bien
    assert not lech_o_bien("bạn có thể lờ đi những thông báo từ táp khác nhé",
                           "bạn có thể lờ đi những thông báo từ tab khác nhé")


def test_khop_hoan_toan_thi_khong_bat():
    from backend.services.chon_doan_mau import lech_o_bien
    assert not lech_o_bien("dạ vâng em nghe anh ạ", "dạ vâng em nghe anh ạ.")


def test_nghe_lai_RONG_thi_coi_nhu_hong():
    from backend.services.chon_doan_mau import lech_o_bien
    assert lech_o_bien("dạ vâng em nghe anh ạ", "")


def test_cut_bien_thi_TRU_DIEM_chu_khong_loai():
    """Loại thẳng thì trên bản ghi thật chỉ còn ĐÚNG MỘT ứng viên - không đủ để
    nghe so, mà cả tính năng sinh ra là để đưa danh sách cho tai người chọn."""
    cut = _ung_vien(loi="hôm nay cũng là hơn ba năm rồi mọi người ạ")
    cut["nghe_lai"] = "đến hôm nay cũng là hơn ba năm rồi mọi người ạ"
    cut["lech_loi"] = 0.03
    gon_ = _ung_vien(loi="hôm nay cũng là hơn ba năm rồi mọi người ạ")
    gon_["nghe_lai"] = "hôm nay cũng là hơn ba năm rồi mọi người ạ"
    ra = xep_hang([cut, gon_])
    assert len(ra) == 2, "clip cắt cụt biên bị vứt thay vì trừ điểm"
    assert ra[0]["nghe_lai"] == gon_["nghe_lai"], "clip cắt gọn không được xếp trên"


def test_xep_hang_GIU_clip_chi_nhoe_o_giua():
    """Nhoè giữa câu 8% thì giữ - ngưỡng cũ 5% loại oan đúng loại này."""
    u = _ung_vien(loi="bạn có thể lờ đi những thông báo từ táp khác nhé")
    u["nghe_lai"] = "bạn có thể lờ đi những thông báo từ tab khác nhé"
    u["lech_loi"] = 0.08
    assert len(xep_hang([u])) == 1


def test_van_loai_khi_lech_giua_QUA_TO():
    """Nhoè vài chữ thì tha, chứ nghe ra nửa câu khác thì không."""
    u = _ung_vien(loi="bạn có thể lờ đi những thông báo từ táp khác nhé")
    u["nghe_lai"] = "bạn hoàn toàn sai rồi mọi thứ đã thay đổi hết từ táp khác nhé"
    u["lech_loi"] = 0.42
    assert xep_hang([u]) == []


def test_chua_nghe_lai_thi_van_qua_duoc():
    """Vòng chấm đầu chưa cho STT nghe lại - đừng loại sạch ở đó."""
    assert len(xep_hang([_ung_vien()])) == 1
