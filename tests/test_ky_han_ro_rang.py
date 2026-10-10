"""Kỳ hạn khách nêu nằm ngoài thời hạn sản phẩm: phải nói thẳng CHƯA ĐƯỢC.

Người dùng (09-10-2026): "hỏi 4-5 tháng nó trả lời chả rõ ràng". Bản cũ đáp
"thời hạn 4 tháng nằm ngoài khung từ 12 đến 60 tháng" rồi hỏi sang thu nhập;
"vay 4-5 tháng" thì đọc "4" thành số tiền và hỏi "triệu hay tỷ".
"""
import pytest

from backend.pipeline.du_kien_khoan_vay import khoang_ky_han, resolve
from backend.pipeline.tra_loi_khoan_vay import tra_loi

TIN_CHAP = ("# Vay Tín Chấp Cá Nhân\n\n## Thông tin sản phẩm\n- Lãi suất: từ 7.9%/năm\n"
            "- Hạn mức: lên đến 500 triệu đồng\n- Thời hạn: 12 - 60 tháng\n")
MUA_NHA = ("# Vay Mua Nhà\n\n## Thông tin sản phẩm\n- Lãi suất ưu đãi: từ 6.5%/năm trong 2 năm đầu\n"
           "- Hạn mức: lên đến 80% giá trị bất động sản, tối đa 10 tỷ đồng\n"
           "- Thời hạn: tối đa 25 năm\n")
DA_NOI_300 = [{"role": "user", "content": "anh muốn vay 300 triệu"},
              {"role": "assistant", "content": "Dạ 300 triệu đồng nằm trong hạn mức. "
                                               "Anh chị muốn vay trong bao lâu ạ?"}]


def _noi(luot: list[str], tai_lieu: str = TIN_CHAP) -> list[tuple[str, str] | None]:
    lich_su, ra = [], []
    for cau in luot:
        got = tra_loi(cau, tai_lieu, history=list(lich_su))
        ra.append(got)
        lich_su += [{"role": "user", "content": cau},
                    {"role": "assistant", "content": got[1] if got else "(đường khác)"}]
    return ra


@pytest.mark.parametrize("cau, khoang", [
    ("anh muốn vay 4-5 tháng được không", (4, 5)),
    ("vay 4, 5 tháng thôi", (4, 5)),
    ("anh vay 200 triệu 4 5 tháng", (4, 5)),
    ("anh chỉ cần vay 200 triệu trong 4 đến 5 tháng thôi", (4, 5)),
    ("anh vay bốn năm tháng thôi được không", (4, 5)),
    ("vay năm sáu tháng được không", (5, 6)),          # từng bị đọc thành 56 tháng
    ("anh vay 500 triệu trong ba bốn năm", (36, 48)),
    ("vay ngắn hạn vài tháng có được không em", (2, 9)),
])
def test_khoang_ky_han_khong_bi_doc_thanh_so_tien(cau, khoang):
    so = resolve([], cau)
    assert so.term.khoang == khoang and so.term_updated and so.term.value is None
    assert so.amount.status in ("unknown", "known")      # không còn "4" thiếu đơn vị


@pytest.mark.parametrize("cau", [
    "anh vay một năm sáu tháng",          # 18 tháng, không phải "năm, sáu tháng"
    "anh vay 100 triệu hai bốn tháng",    # 24 tháng
    "vay ba sáu tháng",                   # 36 tháng
    "anh đi làm được 4-5 tháng rồi",      # không phải kỳ hạn vay
    "nợ anh tất toán được 4-5 tháng rồi",
])
def test_khong_nhan_nham_khoang(cau):
    assert resolve([], cau).term.khoang is None


def test_mot_nam_sau_thang_khong_phai_khoang():
    assert khoang_ky_han("anh vay một năm sáu tháng") is None


@pytest.mark.parametrize("cau", [
    "khoảng 4 5 tháng", "4-5 tháng thôi", "bốn năm tháng", "vài tháng thôi",
])
def test_dap_cut_mot_khoang_cho_cau_ai_vua_hoi(cau):
    got = tra_loi(cau, TIN_CHAP, history=list(DA_NOI_300))
    assert got and got[0] == "ky_han_ngoai_khung" and "chưa được" in got[1]


@pytest.mark.parametrize("cau, co", [
    ("anh muốn vay 500tr trong 4 tháng dược không", ["500 triệu", "vay 4 tháng thì chưa được"]),
    ("anh muốn vay 4-5 tháng được không", ["vay 4 đến 5 tháng thì chưa được"]),
    ("vay 5 tháng được không em", ["vay 5 tháng thì chưa được"]),
    ("vay 500 triệu 4 tháng thì mỗi tháng trả bao nhiêu", ["vay 4 tháng thì chưa được"]),
])
def test_ngan_hon_khung_thi_noi_thang_va_de_nghi_dau_ngan_nhat(cau, co):
    ma, dap = tra_loi(cau, TIN_CHAP, history=[])
    assert ma == "ky_han_ngoai_khung"
    for cum in co:
        assert cum in dap
    assert "ngắn nhất là 12 tháng" in dap and dap.endswith("Anh chị vay 12 tháng được không ạ?")
    assert "khung" not in dap and "trần" not in dap      # chữ khách không hiểu
    assert "triệu đồng; " not in dap                      # không tính trả góp cho kỳ hạn không có


def test_dai_hon_khung_doc_theo_don_vi_khach_noi():
    ma, dap = tra_loi("anh vay 100 triệu trong 7 năm được không", TIN_CHAP, history=[])
    assert ma == "ky_han_ngoai_khung" and "vay 7 năm thì chưa được" in dap
    assert "dài nhất là 5 năm" in dap and dap.endswith("Anh chị vay 5 năm được không ạ?")


def test_trong_khung_thi_noi_duoc():
    ma, dap = tra_loi("anh vay 12 tháng được không", TIN_CHAP, history=[])
    assert ma == "ky_han_trong_khung" and "vay 12 tháng thì được" in dap
    ma, dap = tra_loi("anh vay 100 triệu trong 12 tháng được không", TIN_CHAP, history=[])
    assert ma == "nhu_cau_vay" and dap.startswith("Dạ vay 12 tháng thì được ạ.")
    assert "Số tiền 100 triệu đồng cũng trong hạn mức" in dap and "cần thẩm định" in dap
    ma, dap = tra_loi("anh vay 18 đến 24 tháng được không", TIN_CHAP, history=[])
    assert ma == "ky_han_trong_khung" and "thì được" in dap and dap.endswith("?")


def test_khoang_vat_qua_dau_khung_thi_khong_doan():
    ma, dap = tra_loi("anh vay 6 đến 18 tháng được không", TIN_CHAP, history=[])
    assert ma == "ky_han_ngoai_khung" and "từ 12 đến 60 tháng" in dap and dap.endswith("?")


def test_tai_lieu_chi_co_tran_thoi_han():
    ma, dap = tra_loi("chị muốn vay 2 tỷ trong 30 năm được không", MUA_NHA, history=[])
    assert ma == "ky_han_ngoai_khung" and "vay 30 năm thì chưa được" in dap
    assert "dài nhất là 25 năm" in dap
    ma, dap = tra_loi("chị vay 20 năm được không", MUA_NHA, history=[])
    assert ma == "ky_han_trong_khung" and "dài nhất là 25 năm" in dap


@pytest.mark.parametrize("gat", ["ừ được", "được em", "ok em", "thế cũng được", "vâng"])
def test_khach_gat_voi_thoi_han_ai_de_nghi_thi_ghi_nhan(gat):
    ra = _noi(["anh muốn vay 500tr trong 4 tháng dược không", gat, "thế mỗi tháng trả bao nhiêu"])
    assert ra[1] and ra[1][0] == "ghi_nhan_ky_han" and "thời hạn vay 12 tháng" in ra[1][1]
    # Lượt sau tính theo 12 tháng, không quay lại báo "4 tháng chưa được".
    assert ra[2] and ra[2][0] == "tinh_tra_gop" and "trong 12 tháng" in ra[2][1]


@pytest.mark.parametrize("khong_gat", ["thôi không cần nữa", "thế thôi vậy", "không được",
                                       "để anh nghĩ đã"])
def test_khong_gat_thi_khong_tu_ghi_thoi_han(khong_gat):
    ra = _noi(["anh vay 5 tháng được không", khong_gat])
    assert not (ra[1] and ra[1][0] == "ghi_nhan_ky_han")
    so = resolve([{"role": "user", "content": "anh vay 5 tháng được không"},
                  {"role": "assistant", "content": ra[0][1]},
                  {"role": "user", "content": khong_gat}])
    assert not so.nhan_de_nghi and so.term.value != 12


def test_so_cua_ai_o_cau_khac_van_khong_duoc_lay():
    # Chỉ câu ĐỀ NGHỊ thời hạn mới được gật; câu AI kể thời hạn thì không.
    so = resolve([{"role": "user", "content": "anh muốn vay"},
                  {"role": "assistant", "content": "Dạ bên em cho vay từ 12 đến 60 tháng ạ."},
                  {"role": "user", "content": "ừ được"}])
    assert so.term.status == "unknown" and not so.nhan_de_nghi


def test_khach_nhac_lai_ky_han_bi_tu_choi_thi_khong_doc_lai_nguyen_cau():
    ra = _noi(["anh vay 4 tháng được không", "anh vay 4 tháng thôi"])
    assert ra[0][1] != ra[1][1] and ra[1][0] == "ky_han_ngoai_khung"
    assert ra[1][1].endswith("Anh chị vay 12 tháng được không ạ?")


@pytest.mark.parametrize("cau", ["thế ngắn nhất là bao lâu", "vay tối thiểu mấy tháng hả em"])
def test_hoi_dau_ngan_nhat(cau):
    ma, dap = tra_loi(cau, TIN_CHAP, history=[])
    assert ma == "ky_han_ngan_nhat" and "ngắn nhất là 12 tháng" in dap


@pytest.mark.parametrize("cau, gia_tri", [("khoảng 300 triệu", 300_000_000), ("tầm 2 tỷ", 2_000_000_000)])
def test_tu_rao_don_truoc_con_so_dap_cut(cau, gia_tri):
    so = resolve([{"role": "user", "content": "anh muốn vay 100 triệu"},
                  {"role": "assistant", "content": "Dạ vâng ạ."}], cau)
    assert so.amount.value == gia_tri and so.amount_updated


def test_khach_gat_di_roi_neu_lai_ky_han_cu():
    ra = _noi(["anh muốn vay 4-5 tháng được không", "không anh chỉ cần 4 tháng thôi",
               "thế cũng được"])
    assert ra[1] and ra[1][0] == "ky_han_ngoai_khung" and ra[1][1].startswith("Dạ em hiểu ạ")
    assert ra[1][1].endswith("Anh chị vay 12 tháng được không ạ?")
    assert ra[2] and ra[2][0] == "ghi_nhan_ky_han" and "12 tháng" in ra[2][1]


def test_khach_chon_ky_han_khac_sau_khi_bi_tu_choi():
    ra = _noi(["anh muốn vay 300 triệu", "khoảng 4 5 tháng", "thế 2 năm đi"])
    assert ra[2] and ra[2][0] == "ky_han_trong_khung" and "vay 2 năm thì được" in ra[2][1]


@pytest.mark.parametrize("cau", ["không cần 4 tháng", "không phải 4 tháng"])
def test_phu_dinh_chinh_con_so_thi_khong_thanh_ky_han(cau):
    so = resolve([{"role": "user", "content": "anh muốn vay 300 triệu"},
                  {"role": "assistant", "content": "Dạ vâng ạ."}], cau)
    assert so.term.value is None


def test_hoi_dau_dai_nhat():
    ma, dap = tra_loi("thế dài nhất thì bao lâu", TIN_CHAP, history=[])
    assert ma == "ky_han_dai_nhat" and "dài nhất là 60 tháng" in dap


def test_so_uoc_tinh_tron_khong_doc_phay_khong():
    ra = _noi(["anh muốn vay 500tr trong 4 tháng dược không", "ừ được",
               "thế mỗi tháng anh trả bao nhiêu"])
    assert "khoảng 45 triệu đồng" in ra[2][1] and "45,0" not in ra[2][1]


def test_moi_cau_ngan_chi_mang_mot_con_so():
    """Tiếng cất theo từng câu ngắn: gộp số tiền với kỳ hạn vào một câu là thành
    hàng nghìn tổ hợp, không dựng sẵn được (xem `services/dung_san_manh_so`)."""
    import re as _re
    for cau in ("anh muốn vay 310 triệu trong 5 tháng được không",
                "anh vay 270 triệu trong 18 tháng được không",
                "anh vay 100 triệu trong 7 năm được không"):
        _, dap = tra_loi(cau, TIN_CHAP, history=[])
        for cau_ngan in _re.split(r"(?<=[.?!])\s+", dap):
            co_tien = bool(_re.search(r"\d+ (?:triệu|tỷ)", cau_ngan))
            co_han_khach = bool(_re.search(r"vay \d+ (?:tháng|năm) thì", cau_ngan))
            assert not (co_tien and co_han_khach), cau_ngan
        # Câu mở đầu là phán quyết về kỳ hạn - bộ nhỏ, dựng sẵn được hết.
        assert _re.match(r"Dạ vay \d+ (?:tháng|năm) thì (?:chưa )?được ạ", dap)


def test_tinh_tra_gop_mo_dau_bang_cau_dan_co_dinh():
    ra = _noi(["vay 170 triệu trong 2 năm thì mỗi tháng trả bao nhiêu",
               "vay 230 triệu trong 3 năm thì mỗi tháng trả bao nhiêu"])
    dau = [r[1].split(". ")[0] for r in ra]
    assert ra[0][0] == ra[1][0] == "tinh_tra_gop" and dau[0] == dau[1]      # câu dẫn không mang số của khách
    assert "170 triệu đồng trong 2 năm" in ra[0][1] and "8,2 triệu" in ra[0][1]


@pytest.mark.parametrize("cau, thang", [
    ("vay bốn lăm tháng được không", 45),     # từng bị đáp "4 đến 5 tháng thì chưa được"
    ("vay hai lăm tháng", 25),
    ("vay hai tư tháng", 24),
    ("vay bốn mươi lăm tháng", 45),
])
def test_lam_mot_tu_la_hang_don_vi_khong_phai_mot_dau_cua_khoang(cau, thang):
    """ "lăm / mốt / tư" chỉ là chữ số hàng đơn vị của số ghép, không đứng riêng."""
    assert khoang_ky_han(cau) is None
    assert resolve([], cau).term.value == thang
    got = tra_loi(cau, TIN_CHAP, history=[])
    assert got and f"vay {thang} tháng thì được" in got[1]


def test_bon_nam_thang_van_la_khoang():
    got = tra_loi("vay bốn năm tháng được không", TIN_CHAP, history=[])
    assert got and "4 đến 5 tháng thì chưa được" in got[1]
