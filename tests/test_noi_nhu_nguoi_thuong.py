"""Khách nói con số theo kiểu người thường: thiếu đơn vị, tiếng lóng, tự sửa lời.

Bộ thử 156 lượt ngày 10-10-2026 (`data/bo_thu/vao_noi_that.json`): nói ngọng và
giọng vùng miền gần như không gây lỗi; 26/38 lượt sai nằm ở chỗ tầng luật không
đọc được cách nói con số, rồi sai dây chuyền (mất số tiền ở lượt 3 thì lượt 6
không tính được trả góp).
"""
from decimal import Decimal

import pytest

from backend.pipeline.chan_tuan_thu import (
    CAU_GHI_NHAN_THU_NHAP,
    CAU_GHI_NHAN_THU_NHAP_GIA_DINH,
    CAU_HOI_THU_NHAP,
    chan_gan_thu_nhap,
)
from backend.pipeline.dan_dat import cau_hoi_tiep
from backend.pipeline.du_kien_khoan_vay import quantities, resolve
from backend.pipeline.tra_loi_dieu_kien import tra_loi_dieu_kien
from backend.pipeline.tra_loi_khoan_vay import tra_loi

TIN_CHAP = ("# Vay Tín Chấp Cá Nhân\n\n## Thông tin sản phẩm\n- Lãi suất: từ 7.9%/năm\n"
            "- Hạn mức: lên đến 500 triệu đồng\n- Thời hạn: 12 - 60 tháng\n\n"
            "## Điều kiện vay\n- Công dân Việt Nam, từ 22 - 60 tuổi\n"
            "- Có thu nhập ổn định từ 5 triệu đồng/tháng trở lên\n")
MUA_NHA = ("# Vay Mua Nhà\n\n## Thông tin sản phẩm\n- Lãi suất ưu đãi: từ 6.5%/năm trong 2 năm đầu\n"
           "- Hạn mức: lên đến 80% giá trị bất động sản, tối đa 10 tỷ đồng\n"
           "- Thời hạn: tối đa 25 năm\n")
TIET_KIEM = ("# Gửi Tiết Kiệm\n\n## Thông tin sản phẩm\n- Số tiền gửi tối thiểu: 1 triệu đồng\n\n"
             "## Lãi suất theo kỳ hạn\n- Kỳ hạn 1 tháng: lãi suất 3.5%/năm\n"
             "- Kỳ hạn 6 tháng: lãi suất 4.5%/năm\n- Kỳ hạn 12 tháng: lãi suất 5.5%/năm\n"
             "- Kỳ hạn 36 tháng: lãi suất 6%/năm\n")
TR = 10**6


def _noi(luot, tai_lieu=TIN_CHAP, ai_dau=""):
    lich_su = [{"role": "assistant", "content": ai_dau}] if ai_dau else []
    ra = []
    for cau in luot:
        got = tra_loi(cau, tai_lieu, history=list(lich_su))
        ra.append(got)
        lich_su += [{"role": "user", "content": cau},
                    {"role": "assistant", "content": got[1] if got else "(đường khác)"}]
    return ra, lich_su


# --- Cách đọc con số -----------------------------------------------------------

@pytest.mark.parametrize("cau, gia_tri", [
    ("anh vay ba trăm rưỡi", 350 * TR),            # thiếu đơn vị -> triệu
    ("anh muốn vay hai trăm", 200 * TR),
    ("anh cần vay tầm trăm củ", 100 * TR),          # tiếng lóng
    ("anh vay hai trăm chai", 200 * TR),
    ("anh vay trăm rưỡi", 150 * TR),
    ("anh vay trăm triệu", 100 * TR),
    ("thế vay một tỷ hai được không", 1200 * TR),   # đuôi sau đơn vị
    ("anh cần vay thêm hai tỷ hai", 2200 * TR),
    ("anh vay hai triệu ba", Decimal("2.3") * TR),
    ("anh vay một tỷ hai trăm", 1200 * TR),
    ("anh vay hai lăm triệu", 25 * TR),             # "lăm" là hàng đơn vị
    ("anh vay bốn mươi chiệu", 40 * TR),            # "triệu" nói ngọng
    ("anh vay ba tỏi hai", 3200 * TR),
    ("anh muốn vay ba trăm à không hai trăm triệu thôi", 200 * TR),   # tự sửa lời
    ("anh vay 300 triệu à nhầm 250 triệu", 250 * TR),
])
def test_so_tien_noi_kieu_mieng(cau, gia_tri):
    so = resolve(text=cau)
    assert so.amount.status == "known", so.evidence()
    assert so.amount.value == gia_tri


@pytest.mark.parametrize("cau, thang", [
    ("vay năm rưỡi được không", 18),
    ("anh vay hai năm rưỡi", 30),
    ("vay ba năm à mà thôi bốn năm đi cho nhẹ", 48),
    ("trả góp ba năm", 36),
    ("trả mười lăm năm", 180),
])
def test_ky_han_noi_kieu_mieng(cau, thang):
    assert resolve(text=cau).term.value == thang


def test_so_tien_dinh_lien_ky_han():
    so = resolve(text="vậy hai trăm ba năm thì tháng trả bao nhiêu")   # từng ra 230 năm
    assert so.amount.value == 200 * TR and so.term.value == 36


@pytest.mark.parametrize("cau", [
    "anh vay hai", "anh vay năm",                  # dưới 10: triệu hay tỷ đều có thể
])
def test_so_qua_nho_van_hoi_lai_don_vi(cau):
    assert resolve(text=cau).amount.status == "missing_unit"


def test_tat_cong_tac_thi_quay_ve_hoi_lai_don_vi(monkeypatch):
    from backend.config import settings
    monkeypatch.setattr(settings, "suy_don_vi_trieu", False)
    assert resolve(text="anh muốn vay hai trăm").amount.status == "missing_unit"
    got = tra_loi("anh muốn vay hai trăm", TIN_CHAP, history=[])
    assert got and got[0] == "xac_nhan_don_vi_vay"


@pytest.mark.parametrize("cau", [
    "thế máy thì biết gì mà tư vấn",               # "tư" không phải số 4
    "thế lãi sáu rưỡi là cố định mấy năm",          # "mấy năm" không phải số 5
    "nhà hai tỷ tám anh vay bảy mươi phần trăm",   # phần trăm không phải tiền
    "anh vay được bao nhiêu triệu",                # lời hỏi
    "để anh đợi vợ anh về đã",                     # "đợi" bỏ dấu trùng "đổi"
])
def test_chu_thuong_khong_bi_doc_thanh_so_tien(cau):
    so = resolve(text=cau)
    assert so.amount.status == "unknown", so.evidence()
    got = tra_loi(cau, TIN_CHAP, history=[])
    assert not got or not got[0].startswith("xac_nhan_")


def test_cam_on_sau_khi_da_chot_so_tien_khong_bi_doi_nhac_lai():
    """ "dồi" (rồi, nói ngọng) bỏ dấu thành "doi" = "đổi": số tiền đã chốt bị coi là đang sửa."""
    lich_su = [{"role": "user", "content": "anh muốn vay một trăm lăm mươi triệu"},
               {"role": "assistant", "content": "Dạ 150 triệu đồng thì trong hạn mức ạ."}]
    cau = "ừ thế nà được dồi anh cảm ơn"
    assert resolve(lich_su, cau).amount.value == 150 * TR
    assert tra_loi(cau, TIN_CHAP, history=lich_su) is None


def test_lam_viec_sau_nam_khong_thanh_ky_han_vay():
    so = resolve(text="thì anh làm ở công ty may được sáu năm rồi lương tầm chín mười triệu thôi")
    assert so.term.status == "unknown", so.evidence()
    assert so.income.khoang == (9 * TR, 10 * TR)


# --- Cả cuộc: không còn sai dây chuyền ---------------------------------------------

def test_ngap_ngung_tu_so_tien_toi_tinh_tra_gop():
    ra, _ = _noi(["ờ thì tầm tầm ờ khoảng ờ hai trăm gì đấy"],
                 ai_dau="Dạ vâng ạ, anh cần vay bao nhiêu ạ?")
    assert ra[0] and ra[0][1].startswith("Dạ 200 triệu đồng thì trong hạn mức")
    ra, _ = _noi(["anh muốn vay hai trăm", "thì ờ chắc là ờ hai ba năm gì đó",
                  "ừ thì ba năm đi", "thế ờ thì mỗi tháng ờ anh phải đóng bao nhiêu"])
    assert "2 đến 3 năm thì được" in ra[1][1]
    assert ra[2][1].startswith("Dạ vay 3 năm thì được")
    assert ra[3][0] == "tinh_tra_gop" and "200 triệu đồng trong 3 năm" in ra[3][1]


def test_tieng_long_tu_dau_toi_cuoi():
    ra, _ = _noi(["anh cần vay tầm trăm củ", "à không chắc phải trăm rưỡi",
                  "vay năm rưỡi được không", "lương anh hai chục một tháng",
                  "thế mỗi tháng anh mất mấy củ"])
    assert "100 triệu" in ra[0][1] and "150 triệu" in ra[1][1]
    assert ra[2][1].startswith("Dạ vay 18 tháng thì được")
    assert "thu nhập 20 triệu đồng một tháng" in ra[3][1]
    assert ra[4][0] == "tinh_tra_gop" and "150 triệu đồng trong 18 tháng" in ra[4][1]


@pytest.mark.parametrize("suy_don_vi, ma_dau", [
    (True, "ky_han_trong_khung"), (False, "xac_nhan_ky_han_vay"),
])
def test_ai_vua_hoi_thoi_han_thi_so_tran_la_thoi_han_khong_phai_tien(
        monkeypatch, suy_don_vi, ma_dau):
    from backend.config import settings
    monkeypatch.setattr(settings, "suy_don_vi_trieu", suy_don_vi)
    ra, lich_su = _noi(["ba mươi sáu", "tháng"],
                       ai_dau="Dạ 200 triệu thì trong hạn mức ạ. Anh chị muốn vay trong bao lâu ạ?")
    assert ra[0][0] == ma_dau                        # không thành "36 triệu"
    assert resolve(lich_su).term.value == 36
    assert resolve(lich_su).amount.status == "unknown"
    if suy_don_vi:
        assert ra[0][1].startswith("Dạ vay 36 tháng thì được")
        assert ra[1] is None  # đã xác nhận ở lượt trước, không đọc lặp lại
    else:
        assert ra[1][1].startswith("Dạ vay 36 tháng thì được")


def test_mua_nha_so_tien_va_ky_han():
    ra, _ = _noi(["anh có sẵn một tỷ rồi cần vay thêm hai tỷ hai", "vay hai chục năm"], MUA_NHA)
    assert "2,2 tỷ đồng thì trong hạn mức" in ra[0][1]
    assert ra[1][1].startswith("Dạ vay 20 năm thì được")


def test_loi_mo_dau_bo_lung():
    got = tra_loi("à thì ờ anh đang ờ muốn vay ít tiền ấy mà", TIN_CHAP, history=[])
    assert got == ("muon_vay", "Dạ vâng ạ, gói vay bên em hỗ trợ tối đa 500 triệu đồng ạ.")
    got = tra_loi("chị muốn gửi", TIET_KIEM, history=[])
    assert got == ("muon_gui_tiet_kiem", "Dạ vâng ạ, bên em nhận gửi tiết kiệm từ 1 triệu đồng ạ.")


# --- Thu nhập ---------------------------------------------------------------------

def test_hoi_luon_vay_duoc_khong_thi_doi_chieu_muc_thu_nhap_toi_thieu():
    got = tra_loi("anh ba mươi tuổi lương mười hai triệu có hợp đồng lao động rồi thì vay được "
                  "không và được bao nhiêu", TIN_CHAP, history=[])
    assert got[0] == "thu_nhap_dat_muc"
    assert "12 triệu đồng một tháng thì đạt mức thu nhập tối thiểu 5 triệu đồng" in got[1]
    assert "tối đa là 500 triệu đồng" in got[1] and "thẩm định" in got[1]
    got = tra_loi("chị lương ba triệu thì có vay được không", TIN_CHAP, history=[])
    assert got[0] == "thu_nhap_duoi_muc" and "yêu cầu thu nhập từ 5 triệu đồng" in got[1]
    # Chỉ khai thu nhập, không hỏi gì: vẫn chỉ ghi nhận.
    assert tra_loi("lương anh mười hai triệu", TIN_CHAP, history=[])[0] == "ghi_nhan_thu_nhap"


def test_khoang_thu_nhap_duoc_doc_lai_dung_khoang():
    got = tra_loi("à lương anh mười lăm mười sáu gì đấy", TIN_CHAP, history=[])
    assert got[1] == "Dạ em ghi nhận anh chị thu nhập khoảng 15 đến 16 triệu đồng một tháng ạ."


@pytest.mark.parametrize("ai, khach", [
    ("Với thu nhập 7 triệu, anh chị đã đáp ứng điều kiện mở thẻ rồi.", "lương chị có bảy triệu à"),
    ("Với thu nhập 20 triệu thì hồ sơ được xem xét.", "lương anh hai chục một tháng"),
    ("Với thu nhập 40 triệu, hồ sơ đáp ứng điều kiện.", "thu nhập chị là bốn mươi chiệu một tháng"),
    ("Tổng thu nhập của anh chị là 50 triệu ạ.", "lương anh ba chục vợ anh hai chục"),
])
def test_khach_noi_thu_nhap_bang_chu_thi_ai_duoc_nhac_lai_bang_so(ai, khach):
    assert chan_gan_thu_nhap(ai, khach) == (ai, None)


@pytest.mark.parametrize("ai, khach, expected", [
    ("Với thu nhập 15 triệu thì anh đủ điều kiện.", "anh muốn vay ba trăm triệu",
     CAU_HOI_THU_NHAP),
    ("Với thu nhập 5 triệu, anh đã đáp ứng.", "lương anh hai mươi triệu",
     CAU_GHI_NHAN_THU_NHAP),
])
def test_con_so_khach_chua_noi_thi_van_chan(ai, khach, expected):
    assert chan_gan_thu_nhap(ai, khach)[0] == expected


# --- Luật bắt nhầm / câu hỏi nối đuôi ---------------------------------------------------

def test_khach_hoi_tuoi_cua_nhan_vien_thi_khong_doc_dieu_kien_tuoi():
    assert tra_loi_dieu_kien("em bao nhiêu tuổi rồi có người yêu chưa", "vay_tin_chap", TIN_CHAP) is None
    got = tra_loi_dieu_kien("anh 45 tuổi vay được không", "vay_tin_chap", TIN_CHAP)
    assert got and got[0] == "dieu_kien_tuoi_khop"
    assert "45" in got[1] and "thẩm định" in got[1]


def _dd(khach, cau_tra_loi="Dạ lãi suất từ 7,9% một năm ạ.", ma_san_pham="vay_tin_chap", **kw):
    return cau_hoi_tiep(ma_san_pham=ma_san_pham, trang_thai=resolve(
        [{"role": "user", "content": c} for c in khach]),
        loi_khach_ca_cuoc=" ".join(khach), loi_khach_luot_nay=khach[-1],
        cau_tra_loi=cau_tra_loi, da_hoi=kw.pop("da_hoi", set()), **kw)


def test_khong_noi_cau_hoi_sau_khi_khach_tu_choi_hoac_cau_tra_loi_da_khep():
    assert _dd(["lại gọi mời vay à tôi không có nhu cầu"],
               "Dạ em xin lỗi anh chị ạ. Em xin ghi nhận ngay để bên em không liên hệ lại ạ.") is None
    assert _dd(["à à anh đang lái xe em nói nhanh lên"],
               "Dạ vậy anh chị tập trung lái xe ạ. Em xin phép liên hệ lại, em chào anh chị ạ.") is None
    assert _dd(["em nói nhanh quá anh không nghe kịp"],
               "Dạ em xin lỗi ạ, em sẽ nói chậm hơn ạ.") is None
    # Câu trả lời thường thì vẫn hỏi tiếp như cũ.
    assert _dd(["lãi suất bao nhiêu em"])[0] == "so_tien"


def test_tiet_kiem_khong_hoi_lai_so_tien_ky_han_khach_da_noi():
    dd = _dd(["chị muốn gửi hai trăm triệu kỳ hạn mười hai tháng"],
             "Dạ gửi tiết kiệm kỳ hạn 12 tháng lãi suất 5,5% một năm ạ.", "tiet_kiem")
    assert dd is None
    dd = _dd(["sáu tháng thì được bao nhiêu phần trăm"],
             "Dạ gửi tiết kiệm kỳ hạn 6 tháng lãi suất 4,5% một năm ạ.", "tiet_kiem")
    assert dd and dd[0] == "so_tien"               # kỳ hạn có rồi, số tiền thì chưa


# --- Tiết kiệm theo mạch ----------------------------------------------------------

def test_lai_tiet_kiem_theo_mach_hoi_thoai():
    ra, _ = _noi(["thì gửi ấy gửi tiết kiệm ấy lãi thế nào",
                  "sáu tháng thì ờ được bao nhiêu phần trăm", "thế một năm"], TIET_KIEM)
    assert "4,5%" in ra[1][1] and "6 tháng" in ra[1][1]
    assert "5,5%" in ra[2][1] and "12 tháng" in ra[2][1]     # từng nhận lại câu 6 tháng
    ra, _ = _noi(["sáu tháng", "lãi bao nhiêu"], TIET_KIEM)
    assert ra[1] and "kỳ hạn 6 tháng lãi suất 4,5%" in ra[1][1]   # không đọc lại cả dải


def test_tach_so_lien_nhau_va_tan_suat():
    assert [(q.raw, q.value) for q in quantities("mười lăm mười sáu")] == [
        ("mười lăm", 15), ("mười sáu", 16)]
    q = quantities("lương anh hai chục một tháng")[0]
    assert (q.raw, q.value, q.kind) == ("hai chục", 20, "bare")
    assert quantities("hai mươi mốt tháng")[0].value == 21      # 21 tháng vẫn là 21 tháng


# --- Vòng sửa thứ hai (chạy lại bộ thử thì lộ thêm) ----------------------------------

def test_tu_sua_so_tien_dung_luc_ai_dang_hoi_thoi_han():
    ra, _ = _noi(["à không chắc phải trăm rưỡi"],
                 ai_dau="Dạ 100 triệu đồng thì trong hạn mức ạ. Anh chị muốn vay trong bao lâu ạ?")
    assert ra[0] and "150 triệu" in ra[0][1]          # không thành "150 tháng hay năm"


def test_khach_hoi_lai_con_so_thi_khong_thanh_so_tien_vay():
    ra, lich_su = _noi(["ừ anh nghe ờ mà cái gì ba trăm cơ", "à à anh đang lái xe em nói nhanh lên"],
                       ai_dau="Dạ em đang nghe ạ. Anh chị dự định vay khoảng bao nhiêu ạ?")
    assert ra[0][0] == "xac_nhan_y_nghe_lai" and ra[0][1].endswith("?")
    assert ra[1] is None
    assert resolve(lich_su).amount.status == "unknown"


def test_em_noi_nhanh_len_khong_xoa_so_tien_da_chot():
    lich_su = [{"role": "user", "content": "anh muốn vay ba trăm triệu"},
               {"role": "assistant", "content": "Dạ 300 triệu đồng thì trong hạn mức ạ."}]
    assert resolve(lich_su, "à à anh đang lái xe em nói nhanh lên").amount.value == 300 * TR
    # Sửa thật thì vẫn sửa.
    assert resolve(lich_su, "anh bảo là hai trăm thôi").amount.value == 200 * TR
    assert resolve(lich_su, "đổi sang số khác").amount.value is None


def test_day_la_vay_giong_mien_nam():
    got = tra_loi("dậy anh muốn day chừng hai trăm chai được hông", TIN_CHAP, history=[])
    assert got and got[1].startswith("Dạ 200 triệu đồng thì trong hạn mức")


def test_so_luong_nguoi_khong_phai_thu_nhap():
    assert resolve(text="thu nhập hai vợ chồng chị là bốn mươi triệu một tháng").income.value == 40 * TR
    got = tra_loi("lương anh ba chục vợ anh hai chục", MUA_NHA, history=[])
    assert got[1] == ("Dạ em ghi nhận anh chị thu nhập hai vợ chồng là 30 triệu "
                      "và 20 triệu đồng một tháng ạ.")


THE = ("# Thẻ Tín Dụng\n\n## Thông tin sản phẩm\n- Hạn mức: 10 triệu - 500 triệu đồng\n\n"
       "## Điều kiện mở thẻ\n- Từ 18 tuổi trở lên\n- Thu nhập từ 5 triệu đồng/tháng\n")


def test_the_tin_dung_khai_luong_roi_hoi_lam_duoc_khong():
    got = tra_loi("lương chị có bảy triệu à mần được hông", THE, history=[])
    assert got[0] == "thu_nhap_dat_muc" and "7 triệu đồng một tháng thì đạt mức" in got[1]
    got = tra_loi("chị lương sáu triệu mười chín tuổi làm được không", THE, history=[])
    assert got[0] == "thu_nhap_dat_muc" and "6 triệu đồng" in got[1]
    got = tra_loi("lương anh ba triệu làm thẻ được không", THE, history=[])
    assert got[0] == "thu_nhap_duoi_muc"


def test_luoi_thu_nhap_xet_theo_cau_chua_loi_gan():
    khach = "thu nhập hai vợ chồng chị là bốn mươi triệu một tháng"
    ai = "Với thu nhập 10 triệu, hồ sơ của chị đáp ứng điều kiện ạ. Chị có cần em tính không?"
    ra, ly_do = chan_gan_thu_nhap(ai, khach, khach_da_noi_thu_nhap=True)
    assert ly_do and "thu nhập 10" in ly_do
    assert ra == CAU_GHI_NHAN_THU_NHAP_GIA_DINH
    # Câu chứa lời gán là câu HỎI thì vẫn cho qua.
    hoi = "Thu nhập của anh chị là 10 triệu đúng không ạ?"
    assert chan_gan_thu_nhap(hoi, khach) == (hoi, None)


def test_tieng_long_doi_ve_chu_chuan_cho_mo_hinh_doc():
    from backend.pipeline.du_kien_khoan_vay import doc_lai_tien_long
    assert doc_lai_tien_long("mua căn chung cư ba tỏi hai, vay trăm củ") == (
        "mua căn chung cư ba tỷ hai, vay trăm triệu")
    assert doc_lai_tien_long("mua củ khoai, uống chai nước") == "mua củ khoai, uống chai nước"


def test_cau_xin_du_kien_cua_luat_thi_khong_noi_them_cau_hoi():
    assert _dd(["trả góp ba năm thì mỗi tháng đóng nhiêu"],
               "Dạ để tính khoản trả hàng tháng, anh chị cho em biết số tiền muốn vay kèm đơn vị ạ.",
               ma_luat="thieu_du_kien_tinh_lai") is None


def test_muc_dich_vay_khong_phai_loi_sua_so_tien():
    lich_su = [{"role": "user", "content": "anh muốn vay hai trăm triệu"},
               {"role": "assistant", "content": "Dạ 200 triệu đồng thì trong hạn mức ạ."}]
    for cau in ("cô muốn vay để sửa nhà thì có ảnh hưởng đến xét duyệt không",
                "anh định đổi xe mới", "chốt thế nhé em"):
        assert resolve(lich_su, cau).amount.value == 200 * TR, cau
    for cau in ("đổi sang số khác", "sửa lại số tiền giúp anh", "à nhầm"):
        assert resolve(lich_su, cau).amount.value is None, cau


def test_neu_nhu_cau_kem_khoan_tien_uoc_chung():
    assert resolve(text="chị muốn mua xe máy khoảng năm mươi triệu").amount.value == 50 * TR
    # Giá nhà không phải số tiền vay.
    assert resolve(text="anh muốn mua căn nhà khoảng ba tỷ").amount.status == "unknown"


def test_vuot_han_muc_thi_khong_hoi_tiep_thoi_han():
    assert _dd(["anh đang cần vay một tỷ hai em à"],
               "Dạ gói này hỗ trợ tối đa 500 triệu đồng. Nhu cầu 1,2 tỷ đồng đang vượt trần ạ.",
               ma_luat="vuot_han_muc") is None


def test_mot_so_tien_khong_phai_so_mot():
    assert resolve(text="anh muốn vay một số tiền").amount.status == "unknown"
    got = tra_loi("anh muốn vay một số tiền", TIN_CHAP, history=[])
    assert got and got[0] == "muon_vay"


def test_hai_muc_tien_co_du_don_vi_thi_xin_chot_mot_muc():
    got = tra_loi("khoảng một tỷ đến hai tỷ gì đó", MUA_NHA,
                  history=[{"role": "assistant", "content": "Dạ anh chị dự định vay khoảng bao nhiêu ạ?"}])
    assert got == ("xac_nhan_so_tien_vay", "Dạ anh chị chốt giúp em một số tiền cụ thể muốn vay ạ.")


# --- Suy đơn vị theo HẠN MỨC SẢN PHẨM (thay cho "cứ hiểu là triệu") ---------------------
# Đo trên 313 cuộc gọi thật đã lưu (10-10-2026): khách nêu số tiền 100 lần thì 12
# lần không kèm đơn vị, cả 12 là triệu; mỗi lần AI hỏi lại tốn 13-16 giây.

HOI_TIEN = [{"role": "assistant", "content": "Dạ anh chị dự định vay khoảng bao nhiêu ạ?"}]


@pytest.mark.parametrize("tai_lieu, cau, mong", [
    (TIN_CHAP, "anh vay năm mươi", "50 triệu đồng thì trong hạn mức"),
    (TIN_CHAP, "tám trăm", "800 triệu đồng đang vượt trần"),
    (MUA_NHA, "anh muốn vay hai", "2 tỷ đồng thì trong hạn mức"),         # tỷ, không phải 2 triệu
    (MUA_NHA, "anh muốn vay hai rưỡi", "2,5 tỷ đồng thì trong hạn mức"),
    (MUA_NHA, "anh vay mười lăm", "15 tỷ đồng đang vượt trần"),
    (MUA_NHA, "anh vay năm trăm", "500 triệu đồng thì trong hạn mức"),
])
def test_don_vi_suy_theo_han_muc_san_pham(tai_lieu, cau, mong):
    got = tra_loi(cau, tai_lieu, history=list(HOI_TIEN))
    assert got and mong in got[1], got


@pytest.mark.parametrize("tai_lieu, cau", [
    (TIN_CHAP, "anh muốn vay hai"),       # 2 triệu hay 2 tỷ đều không hợp sản phẩm
    (MUA_NHA, "anh vay năm mươi"),        # 50 triệu hay 50 tỷ đều lạ với vay mua nhà
    (MUA_NHA, "anh vay năm"),             # "năm" còn là năm (thời gian)
])
def test_khong_chac_don_vi_thi_van_hoi_lai(tai_lieu, cau):
    got = tra_loi(cau, tai_lieu, history=list(HOI_TIEN))
    assert got and got[0] == "xac_nhan_don_vi_vay"


def test_so_du_kien_qua_ham_cua_san_pham_khop_voi_luat():
    from backend.pipeline.tra_loi_khoan_vay import du_kien_cua_luot
    assert du_kien_cua_luot(HOI_TIEN, "anh muốn vay hai", MUA_NHA).amount.value == 2 * 10**9
    assert du_kien_cua_luot(HOI_TIEN, "anh muốn vay hai", TIN_CHAP).amount.status == "missing_unit"
    # Ra khỏi lượt là hết hiệu lực: lần gọi trần không còn nhớ hạn mức của lượt trước.
    assert resolve(HOI_TIEN, "anh muốn vay hai").amount.status == "missing_unit"


@pytest.mark.parametrize("cau", [
    "khoản vay của anh bao giờ thì đến hạn",       # "anh bao giờ" bỏ dấu trùng "anh bảo": 69 lần trong cuộc gọi thật
    "em nói lại giúp anh toàn bộ điều kiện và thủ tục một lượt được không",   # "một lượt": 38 lần
    "ví dụ anh vay một lần thì hết bao nhiêu",
    "mà lãi bảy phẩy chín đấy là cố định hay sau này nó tăng lên",
    "là từ bảy phẩy chín phần",
])
def test_cau_trong_cuoc_goi_that_tung_bi_doi_nhac_lai_so_tien(cau):
    lich_su = [{"role": "user", "content": "anh muốn vay ba trăm triệu"},
               {"role": "assistant", "content": "Dạ 300 triệu đồng thì trong hạn mức ạ."}]
    assert resolve(lich_su, cau).amount.value == 300 * TR
    got = tra_loi(cau, TIN_CHAP, history=lich_su)
    assert not got or not got[0].startswith("xac_nhan_")


def test_khong_ket_cau_la_loi_hoi_khong_phai_so_khong():
    so = resolve(text="anh muốn vay tầm bốn trăm triệu không")       # 7 lần trong cuộc gọi thật
    assert so.amount.value == 400 * TR
    assert quantities("hai không năm")[0].raw == "hai không năm"        # giữa dãy số thì vẫn là chữ số
