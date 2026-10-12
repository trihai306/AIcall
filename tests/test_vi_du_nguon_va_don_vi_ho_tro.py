"""Ví dụ công bố và phạm vi đơn vị/tài sản phải bám đúng nguồn sản phẩm."""

from pathlib import Path

import pytest

from backend.pipeline.tra_loi_khoan_vay import (
    _tra_loi_pham_vi_nguon,
    tra_loi,
)


ROOT = Path(__file__).resolve().parents[1]
TIN_CHAP = (ROOT / "knowledge/products/vay_tin_chap.md").read_text(encoding="utf-8")
THE = (ROOT / "knowledge/products/the_tin_dung.md").read_text(encoding="utf-8")
TIET_KIEM = (ROOT / "knowledge/products/tiet_kiem.md").read_text(encoding="utf-8")
MUA_NHA = (ROOT / "knowledge/products/vay_mua_nha.md").read_text(encoding="utf-8")


def users(*texts: str) -> list[dict]:
    return [{"role": "user", "content": text} for text in texts]


@pytest.mark.parametrize(("phuong_an", "khoan_tra"), [
    ("Tôi muốn vay 100 triệu trong 36 tháng.", "3,4 triệu đồng"),
    ("Tôi muốn vay 200 triệu trong 36 tháng.", "6,8 triệu đồng"),
    ("Tôi muốn vay 300 triệu trong 48 tháng.", "8,2 triệu đồng"),
])
def test_doc_dung_vi_du_cong_bo_khop_chinh_xac(phuong_an, khoan_tra):
    ma, dap = tra_loi(
        "Theo ví dụ sản phẩm, mỗi tháng khoảng bao nhiêu, tôi muốn biết đúng ví dụ công bố?",
        TIN_CHAP, history=users(phuong_an))

    assert ma == "vi_du_nguon_khoan_tra"
    assert khoan_tra in dap and "ví dụ công bố" in dap
    assert "không phải thu nhập" in dap
    assert "chưa phải lịch trả nợ chính thức được phê duyệt" in dap


def test_cau_hau_to_tien_tra_khong_bi_hieu_thanh_thu_nhap_toi_thieu():
    ma, dap = tra_loi(
        "Theo ví dụ sản phẩm, mỗi tháng khoảng bao nhiêu, tôi muốn biết đúng ví dụ "
        "công bố? Đây là tiền trả chứ không phải thu nhập.",
        TIN_CHAP, history=users("Tôi muốn vay 200 triệu trong 36 tháng."))

    assert ma == "vi_du_nguon_khoan_tra"
    assert "6,8 triệu đồng" in dap
    assert "5 triệu" not in dap


def test_uoc_tinh_rieng_van_dung_cong_thuc_thay_vi_vi_du_nguon():
    ma, dap = tra_loi(
        "Mỗi tháng phải trả bao nhiêu?", TIN_CHAP,
        history=users("Tôi muốn vay 200 triệu trong 36 tháng."))

    assert ma == "tinh_tra_gop"
    assert "6,9 triệu đồng" in dap
    assert "6,8 triệu đồng" not in dap


def test_vi_du_gia_dinh_cua_khach_khong_bi_coi_la_vi_du_cong_bo():
    ma, dap = tra_loi(
        "Ví dụ tôi vay 200 triệu trong 36 tháng thì mỗi tháng trả bao nhiêu?",
        TIN_CHAP)

    assert ma == "tinh_tra_gop"
    assert "6,9 triệu đồng" in dap and "theo ví dụ công bố" not in dap


def test_khong_co_vi_du_khop_thi_khong_tu_thay_bang_cong_thuc():
    ma, dap = tra_loi(
        "Theo đúng ví dụ công bố thì mỗi tháng trả bao nhiêu?", TIN_CHAP,
        history=users("Tôi muốn vay 250 triệu trong 36 tháng."))

    assert ma == "khong_co_vi_du_nguon_khop"
    assert "chưa có ví dụ công bố khớp" in dap
    assert "chưa tự dùng công thức" in dap
    assert "8,3 triệu" not in dap


def test_thieu_phuong_an_de_chon_vi_du_thi_hoi_lai():
    ma, dap = tra_loi("Đọc đúng ví dụ trong tài liệu giúp tôi.", TIN_CHAP)

    assert ma == "thieu_du_kien_vi_du_nguon"
    assert "số tiền vay và thời hạn vay" in dap


def test_hai_vi_du_nguon_mau_thuan_khong_tu_chon_mot_so():
    doc = TIN_CHAP.replace(
        "- Ví dụ: vay 200 triệu trong 36 tháng thì trả góp khoảng 6.8 triệu mỗi tháng",
        "- Ví dụ: vay 200 triệu trong 36 tháng thì trả góp khoảng 6.8 triệu mỗi tháng\n"
        "- Ví dụ: vay 200 triệu trong 36 tháng thì trả góp khoảng 7.1 triệu mỗi tháng")

    ma, dap = tra_loi(
        "Theo ví dụ trong nguồn thì mỗi tháng bao nhiêu?", doc,
        history=users("Tôi muốn vay 200 triệu trong 36 tháng."))

    assert ma == "vi_du_nguon_mau_thuan"
    assert "nhiều khoản trả khác nhau" in dap and "kiểm tra lại nguồn" in dap
    assert "6,8 triệu" not in dap and "7,1 triệu" not in dap


def test_nguon_khong_co_muc_vi_du_thi_noi_ro_vang_mat():
    doc = TIN_CHAP.split("## Ví dụ tính toán khoản trả góp", 1)[0]
    ma, dap = tra_loi(
        "Theo ví dụ trong tài liệu thì mỗi tháng bao nhiêu?", doc,
        history=users("Tôi muốn vay 200 triệu trong 36 tháng."))

    assert ma == "khong_co_vi_du_nguon"
    assert "chưa có ví dụ khoản trả hàng tháng" in dap


@pytest.mark.parametrize(("doc", "history", "question", "ma", "nhan"), [
    (TIN_CHAP,
     users("Tôi muốn vay bằng USD thay vì đồng Việt Nam.", "Tôi 45 tuổi.",
           "Tôi chỉ muốn dùng thông tin trong sản phẩm đang tư vấn."),
     "Lãi suất USD chính xác có phải 7,9% không?",
     "don_vi_tien_te_chua_co_trong_nguon", "USD"),
    (THE,
     users("Tôi muốn hạn mức thẻ được cấp bằng EUR.", "Tôi 60 tuổi.",
           "Tôi cần câu trả lời có căn cứ từ thông tin công bố."),
     "Biểu phí và hạn mức EUR cụ thể thế nào?",
     "don_vi_tien_te_chua_co_trong_nguon", "EUR"),
    (TIET_KIEM,
     users("Tôi muốn gửi 10 lượng vàng trong 12 tháng.", "Tôi 35 tuổi.",
           "Tôi cần câu trả lời có căn cứ từ thông tin công bố."),
     "Ngân hàng trả lãi vàng cụ thể bao nhiêu?",
     "tien_gui_khong_co_chinh_sach", "vàng"),
    (MUA_NHA,
     users("Tôi chỉ có ô tô để bảo đảm, chưa có bất động sản.", "Tôi 25 tuổi.",
           "Nếu tài liệu chưa có thì nói rõ giúp tôi."),
     "Ô tô có chắc được nhận làm tài sản bảo đảm cho vay mua nhà không?",
     "tai_san_chua_duoc_nguon_xac_nhan", "ô tô"),
    (TIET_KIEM,
     users("Tôi muốn gửi 20.000 USD kỳ hạn 12 tháng.", "Tôi 25 tuổi.",
           "Nếu tài liệu chưa có thì nói rõ giúp tôi."),
     "Lãi suất USD và tiền lãi cuối kỳ chính xác là bao nhiêu?",
     "don_vi_tien_te_chua_co_trong_nguon", "USD"),
    (MUA_NHA,
     users("Tài sản tôi định thế chấp là tiền mã hóa.", "Tôi 35 tuổi.",
           "Tôi cần câu trả lời có căn cứ từ thông tin công bố."),
     "Có thể duyệt vay mua nhà dựa trên tài sản này chứ?",
     "tai_san_chua_duoc_nguon_xac_nhan", "tiền mã hóa"),
])
def test_sau_ca_pilot_khong_ap_chinh_sach_vnd_sang_don_vi_tai_san_khac(
        doc, history, question, ma, nhan):
    got_ma, dap = tra_loi(question, doc, history=history)

    assert got_ma == ma
    assert nhan in dap and "tài liệu" in dap
    assert "chưa" in dap
    assert "chắc chắn được" not in dap


def test_guard_thuan_chan_usd_online_ngay_trong_luot():
    got = _tra_loi_pham_vi_nguon(
        "Gửi online 20.000 USD kỳ hạn 12 tháng lãi bao nhiêu?", TIET_KIEM)

    assert got and got[0] == "don_vi_tien_te_chua_co_trong_nguon"
    assert "USD" in got[1] and "5,7%" not in got[1]


def test_guard_thuan_giu_usd_qua_followup_apr_online_chung():
    got = _tra_loi_pham_vi_nguon(
        "Gửi online kỳ hạn 12 tháng lãi bao nhiêu?", TIET_KIEM,
        history=users("Tôi muốn gửi 20.000 USD kỳ hạn 12 tháng."))

    assert got and got[0] == "don_vi_tien_te_chua_co_trong_nguon"
    assert "USD" in got[1] and "đồng Việt Nam" in got[1]


def test_switch_ro_ve_vnd_xoa_chu_de_usd_va_cho_phep_apr_vnd():
    history = users("Tôi muốn gửi 20.000 USD kỳ hạn 12 tháng.")
    question = "Không tính USD nữa, chuyển sang gửi VND online kỳ hạn 12 tháng, lãi bao nhiêu?"

    assert _tra_loi_pham_vi_nguon(question, TIET_KIEM, history) is None
    ma, dap = tra_loi(question, TIET_KIEM, history=history)
    assert ma == "lai_tiet_kiem_theo_ky"
    assert "5,7%" in dap and "gửi online" in dap


def test_phu_dinh_usd_nhung_chuyen_sang_eur_van_giu_dung_chu_de_moi():
    got = _tra_loi_pham_vi_nguon(
        "Không phải USD, tôi muốn dùng EUR; biểu phí cụ thể thế nào?", THE)

    assert got and got[0] == "don_vi_tien_te_chua_co_trong_nguon"
    assert "EUR" in got[1] and "USD" not in got[1]


def test_chu_de_usd_khong_chan_cau_khai_tuoi_khong_hoi_chinh_sach():
    assert _tra_loi_pham_vi_nguon(
        "Tôi 45 tuổi.", TIN_CHAP,
        history=users("Tôi muốn vay bằng USD thay vì đồng Việt Nam.")) is None


def test_cau_ke_xe_30m_khong_bi_coi_la_yeu_cau_the_chap():
    assert _tra_loi_pham_vi_nguon(
        "Hạn mức vay mua nhà bao nhiêu?", MUA_NHA,
        history=users("Xe của tôi 30 triệu.")) is None


def test_tai_san_khac_khong_du_de_bao_dam_o_to_duoc_nhan():
    ma, dap = _tra_loi_pham_vi_nguon(
        "Ô tô có chắc được nhận làm tài sản bảo đảm không?", MUA_NHA)

    assert ma == "tai_san_chua_duoc_nguon_xac_nhan"
    assert "tài sản khác" in dap and "chưa đủ" in dap
    assert "sẽ được nhận" in dap and "chưa đủ để bảo đảm" in dap


def test_nguon_neu_dich_danh_o_to_thi_guard_khong_chan():
    doc = MUA_NHA.replace(
        "Có tài sản đảm bảo (bất động sản mua hoặc tài sản khác)",
        "Có tài sản đảm bảo (bất động sản mua hoặc ô tô)")

    assert _tra_loi_pham_vi_nguon(
        "Ô tô có được nhận làm tài sản bảo đảm không?", doc) is None


def test_thu_nhap_usd_khong_doi_don_vi_khoan_vay_khi_tinh_ltv():
    history = users(
        "Căn hộ có giá 9 tỷ đồng.",
        "Tôi muốn vay 4 tỷ và thu nhập 30 triệu một tháng.",
        "Tôi còn có thu nhập 2.000 USD từ nước ngoài.",
    )
    question = "Vậy hạn mức tối đa theo giá căn hộ là bao nhiêu, có chắc được vay không?"

    assert _tra_loi_pham_vi_nguon(question, MUA_NHA, history) is None
    ma, dap = tra_loi(question, MUA_NHA, history=history)
    assert ma == "han_muc_theo_gia_bat_dong_san"
    assert "7,2 tỷ đồng" in dap and "2.000 USD" not in dap


def test_usd_gan_voi_gia_can_ho_van_di_nhanh_xac_nhan_gia_vnd():
    question = "Vậy hạn mức tối đa theo giá căn hộ là bao nhiêu, có chắc được vay không?"
    history = users("Căn hộ giá 9 tỷ USD.")

    assert _tra_loi_pham_vi_nguon(question, MUA_NHA, history) is None
    ma, dap = tra_loi(question, MUA_NHA, history=history)
    assert ma == "xac_nhan_gia_bat_dong_san"
    assert "bằng VND" in dap and "7,2 tỷ" not in dap


def test_usd_trong_vi_du_trich_dan_khong_treo_thanh_don_vi_san_pham():
    history = users("Trong ví dụ tham khảo có ghi số tiền 2.000 USD.")

    assert _tra_loi_pham_vi_nguon(
        "Hạn mức vay tối đa bao nhiêu?", TIN_CHAP, history) is None


def test_hoi_dich_danh_chinh_sach_usd_trong_nguon_van_bi_chan():
    got = _tra_loi_pham_vi_nguon(
        "Tài liệu có nêu lãi suất USD không, mức cụ thể bao nhiêu?", TIN_CHAP)

    assert got and got[0] == "don_vi_tien_te_chua_co_trong_nguon"
    assert "USD" in got[1] and "chưa nêu" in got[1]


def test_gia_dinh_usd_khong_de_lai_chu_de_sau_khai_bao_so_vnd_that():
    history = users(
        "Nếu gửi USD thì sao?",
        "Sổ thật của tôi100triệu đồng12tháng online.",
    )

    assert _tra_loi_pham_vi_nguon(
        "Lãi suất online hiện tại bao nhiêu?", TIET_KIEM, history) is None


def test_khai_bao_khoan_vay_vnd_moi_xoa_chu_de_usd_cu():
    history = users(
        "Tôi muốn vay bằng USD.",
        "Phương án thật là vay100triệu đồng trong24tháng.",
    )

    assert _tra_loi_pham_vi_nguon(
        "Mỗi tháng trả bao nhiêu?", TIN_CHAP, history) is None


def test_usd_cua_khoan_vay_cu_khong_dinh_sang_the_gold():
    history = users(
        "Tôi muốn vay bằng USD.",
        "Bỏ khoản vay, giờ chỉ hỏi thẻ Gold.",
    )

    assert _tra_loi_pham_vi_nguon(
        "Hạn mức thẻ Gold cụ thể bao nhiêu?", THE, history) is None


def test_usd_gui_that_van_duoc_giu_cho_followup_apr_cung_san_pham():
    history = users("Tôi muốn gửi20.000USD online.")
    got = _tra_loi_pham_vi_nguon(
        "Lãi suất online hiện tại bao nhiêu?", TIET_KIEM, history)

    assert got and got[0] == "don_vi_tien_te_chua_co_trong_nguon"
    assert "USD" in got[1]


@pytest.mark.parametrize("ten_tai_san", ["Bitcoin", "ETH", "tiền mã hóa"])
def test_tien_ma_hoa_duoc_yeu_cau_gui_lai_khong_nhan_apr_vnd(ten_tai_san):
    question = f"Tôi có 0,2{ten_tai_san}, gửi tiết kiệm online được 5,7% chứ?"

    ma, dap = _tra_loi_pham_vi_nguon(question, TIET_KIEM)
    assert ma == "tien_gui_khong_co_chinh_sach"
    assert "tiền mã hóa" in dap and "chưa nêu chính sách" in dap
    assert "5,7%" not in dap

    full_ma, full_dap = tra_loi(question, TIET_KIEM)
    assert full_ma == ma and full_dap == dap


def test_tien_gui_bitcoin_that_duoc_giu_cho_followup_apr():
    history = users("Tôi muốn gửi0,2Bitcoin online.")
    got = _tra_loi_pham_vi_nguon(
        "Lãi suất online hiện tại bao nhiêu?", TIET_KIEM, history)

    assert got and got[0] == "tien_gui_khong_co_chinh_sach"
    assert "tiền mã hóa" in got[1] and "đồng Việt Nam" in got[1]


def test_khoan_gui_vnd_moi_xoa_chu_de_bitcoin_cu():
    history = users(
        "Tôi muốn gửi0,2Bitcoin online.",
        "Sổ thật của tôi100triệu đồng12tháng online.",
    )

    assert _tra_loi_pham_vi_nguon(
        "Lãi suất online hiện tại bao nhiêu?", TIET_KIEM, history) is None


def test_gia_bitcoin_chi_la_tai_san_ke_khong_doi_don_vi_ltv():
    history = users("Căn hộ của tôi giá 9 tỷ đồng.", "Bitcoin của tôi trị giá 1 tỷ.")
    question = "Hạn mức theo giá nhà là bao nhiêu?"

    assert _tra_loi_pham_vi_nguon(question, MUA_NHA, history) is None
    ma, dap = tra_loi(question, MUA_NHA, history=history)
    assert ma == "han_muc_theo_gia_bat_dong_san" and "7,2 tỷ đồng" in dap


def test_bitcoin_the_chap_van_la_tai_san_can_kiem_tra_nguon():
    ma, dap = _tra_loi_pham_vi_nguon(
        "Bitcoin có chắc được nhận làm tài sản thế chấp không?", MUA_NHA)

    assert ma == "tai_san_chua_duoc_nguon_xac_nhan"
    assert "tiền mã hóa" in dap and "chưa xác nhận riêng" in dap


def test_cau_hoi_chinh_sach_crypto_chung_van_noi_nguon_chua_neu():
    ma, dap = _tra_loi_pham_vi_nguon(
        "Bitcoin có được hỗ trợ không?", TIET_KIEM)

    assert ma == "tien_gui_khong_co_chinh_sach"
    assert "chưa nêu chính sách" in dap and "cần kiểm tra lại nguồn" in dap
    assert "không hỗ trợ" not in dap


def test_nguon_neu_ro_chinh_sach_bitcoin_thi_guard_khong_thay_the():
    doc = TIET_KIEM.replace(
        "- Hình thức: gửi tại quầy hoặc gửi online",
        "- Hình thức: gửi tại quầy hoặc gửi online\n"
        "- Tài sản hỗ trợ: nhận gửi Bitcoin online")

    assert _tra_loi_pham_vi_nguon(
        "Tôi có 0,2 Bitcoin, gửi tiết kiệm online được không?", doc) is None


@pytest.mark.parametrize("question", [
    "Bitcoin của tôi trị giá1tỷ. SổVND online lãi suất bao nhiêu?",
    "Tôi cóBitcoin để đầu tư, còn muốn gửi100triệu đồng online lãi suất bao nhiêu?",
    "Tôi có0,2Bitcoin, nhưng sổ thật là100triệu đồng online; lãi suất bao nhiêu?",
])
def test_crypto_ke_rieng_khong_cuop_yeu_cau_gui_vnd_cung_luot(question):
    assert _tra_loi_pham_vi_nguon(question, TIET_KIEM) is None

    got = tra_loi(question, TIET_KIEM)
    assert got and got[0] != "tien_gui_khong_co_chinh_sach"
    assert "chưa nêu chính sách gửi hoặc trả lãi bằng tiền mã hóa" not in got[1]


def test_khoan_gui_vnd_dung_truoc_van_thang_crypto_ke_sau():
    question = (
        "Tôi muốn gửi100triệu đồng online, lãi suất bao nhiêu? "
        "Bitcoin của tôi chỉ để đầu tư thôi.")

    assert _tra_loi_pham_vi_nguon(question, TIET_KIEM) is None


def test_yeu_cau_gui_bitcoin_moi_sau_khoan_vnd_cu_duoc_uu_tien():
    question = (
        "Sổ hiện tại là100triệu đồng. Giờ tôi muốn gửi0,2Bitcoin online, "
        "lãi suất bao nhiêu?")
    got = _tra_loi_pham_vi_nguon(question, TIET_KIEM)

    assert got and got[0] == "tien_gui_khong_co_chinh_sach"
    assert "tiền mã hóa" in got[1] and "đồng Việt Nam" in got[1]
