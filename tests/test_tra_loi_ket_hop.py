"""Chế độ KẾT HỢP: kho + luật trả lời trước, kho không có thì mô hình trả lời.

Hai chốt riêng của chế độ này: không cho mô hình tự tính tiền, và ép câu sinh ra
gọn như lời nói qua điện thoại. Các câu mẫu lấy nguyên từ bộ thử 304 lượt
(08-10-2026), lúc Qwen 9B trả lời tự do.
"""
import asyncio

from backend.pipeline.chan_tuan_thu import CAU_THAY_TU_TINH, chan_tu_tinh_tien
from backend.pipeline.streaming_pipeline import StreamingPipeline


def test_chan_cau_tu_tinh_tien_tra_hang_thang():
    for cau in (
        "Anh/chị muốn vay 12 tháng thì khoản trả góp khoảng 3,4 triệu mỗi tháng ạ.",
        "Dạ nếu vay khoảng 1-2 tỷ thì hàng tháng trả khoảng 9.5-16.5 triệu ạ.",
        "Nếu vay 300 triệu trong 36 tháng thì khoản trả góp khoảng 8.2 triệu mỗi tháng ạ.",
        "Dạ tiền lãi khoảng 20 triệu ạ.",
    ):
        ra, ly_do = chan_tu_tinh_tien(cau)
        assert ly_do and ra == CAU_THAY_TU_TINH, cau


def test_khong_chan_du_kien_cua_tai_lieu():
    for cau in (
        "Mức lãi suất vay tín chấp của bên em là từ 7.9% một năm ạ.",
        "Dạ điều kiện là thu nhập từ 5 triệu mỗi tháng trở lên ạ.",
        "Dạ thẻ yêu cầu trả tối thiểu 5% dư nợ mỗi tháng ạ.",
        "Dạ hạn mức vay tín chấp lên đến 500 triệu đồng ạ.",
        "Dạ anh chị muốn trả khoảng bao nhiêu triệu mỗi tháng ạ?",
    ):
        assert chan_tu_tinh_tien(cau) == (cau, None), cau


def _chay(tokens, toi_da_cau=2):
    async def nguon():
        for t in tokens:
            yield t

    async def gom():
        return "".join([t async for t in StreamingPipeline._gon_cau_sinh(nguon(), toi_da_cau)])

    return asyncio.run(gom())


def test_cau_sinh_duoc_them_da_va_ha_chu_dau():
    assert _chay(["Mức", " lãi", " suất", " từ", " 7.9%", " một", " năm", " ạ."]) == \
        "Dạ mức lãi suất từ 7.9% một năm ạ."
    # Đã có "Dạ" thì giữ nguyên.
    assert _chay(["Dạ", " em", " hiểu", " ạ."]) == "Dạ em hiểu ạ."
    # Từ viết hoa toàn bộ không bị hạ chữ.
    assert _chay(["CMND", " hoặc", " CCCD", " ạ."]).startswith("Dạ CMND")


def test_cau_sinh_dung_sau_hai_cau_va_khong_cat_o_dau_cham_trong_so():
    ra = _chay(["Dạ", " lãi", " suất", " từ", " 7.9%", " ạ.", " Hạn", " mức", " 500",
                " triệu", " ạ.", " Thủ", " tục", " đơn", " giản", " ạ."])
    assert ra == "Dạ lãi suất từ 7.9% ạ. Hạn mức 500 triệu ạ."


_TL = {
    "vay_tin_chap": "# Vay Tín Chấp\n- Lãi suất: từ 7.9%/năm\n- Hạn mức: lên đến 500 triệu đồng\n- Thời hạn: 12 - 60 tháng\n",
    "vay_mua_nha": "# Vay Mua Nhà\n- Lãi suất ưu đãi: từ 6.5%/năm trong 2 năm đầu\n- Thời hạn: tối đa 25 năm\n",
    "the_tin_dung": "# Thẻ Tín Dụng\n- Hạn mức: 10 triệu - 500 triệu đồng\n",
}


def _ss(cau, ma_phien=""):
    from backend.pipeline.so_sanh_san_pham import tra_loi
    return tra_loi(cau, set(_TL), lambda ma: _TL.get(ma, ""), ma_phien=ma_phien)


def test_so_sanh_dat_hai_du_kien_canh_nhau():
    ma, cau = _ss("thế lãi suất vay mua nhà với vay tín chấp cái nào thấp hơn")
    assert ma == "so_sanh_lai_suat"
    assert "6.5%" in cau and "7.9%" in cau and cau.index("mua nhà") < cau.index("tín chấp")


def test_so_sanh_dung_san_pham_phien_lam_ve_thu_hai():
    ma, cau = _ss("vay tín chấp thì vay được nhiều hơn thẻ đúng không em", ma_phien="the_tin_dung")
    assert ma == "so_sanh_han_muc" and "500 triệu" in cau and "10 triệu" in cau
    # Mô hình từng đáp "Dạ đúng ạ"; luật không được kết luận hộ khách.
    assert "đúng" not in cau


def test_khong_phai_so_sanh_thi_tra_none():
    assert _ss("lãi suất vay tín chấp bao nhiêu") is None
    assert _ss("vay tín chấp có cao hơn bên khác không") is None


def _dd(**kw):
    from backend.pipeline.dan_dat import cau_hoi_tiep
    from backend.pipeline.du_kien_khoan_vay import resolve
    lich_su = [{"role": "user", "content": c} for c in kw.pop("khach")]
    mac_dinh = dict(ma_san_pham="vay_tin_chap", trang_thai=resolve(lich_su),
                    loi_khach_ca_cuoc=" ".join(m["content"] for m in lich_su),
                    loi_khach_luot_nay=lich_su[-1]["content"],
                    cau_tra_loi="Dạ lãi suất từ 7.9%/năm ạ.", da_hoi=set())
    mac_dinh.update(kw)
    return cau_hoi_tiep(**mac_dinh)


def test_dan_dat_hoi_thu_con_thieu_theo_thu_tu():
    assert _dd(khach=["lãi suất bao nhiêu em"])[0] == "so_tien"
    assert _dd(khach=["anh muốn vay ba trăm triệu"])[0] == "ky_han"
    assert _dd(khach=["anh muốn vay ba trăm triệu trong hai năm"])[0] == "thu_nhap"
    # Đã hỏi rồi thì không hỏi lại ý đó.
    assert _dd(khach=["lãi suất bao nhiêu em"], da_hoi={"so_tien"})[0] == "ky_han"


def test_dan_dat_khong_hoi_don_khi_khach_khep_hoac_cau_da_la_cau_hoi():
    assert _dd(khach=["thôi để anh suy nghĩ thêm đã"]) is None
    assert _dd(khach=["lãi suất bao nhiêu em"], y_dinh_thuong_gap="tu_choi") is None
    assert _dd(khach=["lãi suất bao nhiêu em"],
               cau_tra_loi="Dạ anh chị muốn vay bao nhiêu ạ?") is None
    assert _dd(khach=["lãi suất bao nhiêu em"], ma_luat="kho_khong_co_0") is None
    assert _dd(khach=["có bảo hiểm không em"], ma_san_pham="bao_hiem") is None


def test_dan_dat_khong_hoi_sang_y_moi_khi_khach_chua_dap_y_vua_hoi():
    # Lượt trước hỏi số tiền, khách nói chuyện khác -> lượt này im, không hỏi thời hạn.
    assert _dd(khach=["vay tiêu dùng ấy vay cá nhân"], da_hoi={"so_tien"}, vua_hoi="so_tien") is None
    # Khách đã đáp số tiền -> hỏi tiếp thời hạn.
    assert _dd(khach=["anh muốn vay ba trăm triệu"], da_hoi={"so_tien"}, vua_hoi="so_tien")[0] == "ky_han"


def test_dap_cut_ky_han_cho_cau_ai_vua_hoi_thi_xac_nhan_khong_roi_xuong_mo_hinh():
    from backend.pipeline.tra_loi_khoan_vay import tra_loi
    doc = ("# Vay Tín Chấp Cá Nhân\n\n## Thông tin sản phẩm\n- Lãi suất: từ 7.9%/năm\n"
           "- Hạn mức: lên đến 500 triệu đồng\n- Thời hạn: 12 - 60 tháng\n")
    lich_su = [
        {"role": "user", "content": "anh muốn vay ba trăm triệu"},
        {"role": "assistant", "content": "Dạ 300 triệu nằm trong hạn mức ạ. Anh chị muốn vay trong bao lâu ạ?"},
        {"role": "user", "content": "mười hai tháng"},
    ]
    got = tra_loi("mười hai tháng", doc, None, lich_su)
    assert got and got[0] == "ky_han_trong_khung" and "12 tháng" in got[1]


def test_chan_mo_hinh_tu_ket_luan_khach_khong_vay_duoc():
    from backend.pipeline.chan_tuan_thu import CAU_THAY_TU_CHOI, chan_ket_luan_tu_choi
    for cau in (
        "Vâng ạ, vì anh đang thuê nên hồ sơ vay mua nhà sẽ không được xét duyệt.",
        "Nếu anh chị đang có khoản vay chưa hết hạn thì sẽ ảnh hưởng đến hồ sơ vay mới ạ.",
        "Dạ anh chị nghỉ hưu chưa đủ điều kiện tuổi từ 22 - 60 tuổi ạ.",
        "Hiện tại bên em chưa có gói hỗ trợ riêng cho mua xe ạ.",
    ):
        ra, ly_do = chan_ket_luan_tu_choi(cau)
        assert ly_do and ra == CAU_THAY_TU_CHOI, cau
    for cau in (
        "Dạ em chưa có thông tin về phần này ạ.",
        "Dạ điều kiện là không có nợ xấu tại CIC ạ.",
        "Dạ anh chị đã đủ điều kiện chưa ạ?",
        "Dạ lãi suất từ 7.9%/năm ạ.",
    ):
        assert chan_ket_luan_tu_choi(cau) == (cau, None), cau


def test_luat_chi_nhuong_khi_cau_cua_kho_dung_chu_de():
    """"thế cần giấy tờ gì" sau lượt nói thời hạn: kho chọn câu thời hạn thì giữ câu của luật."""
    from backend.pipeline.streaming_pipeline import kho_cung_chu_de
    assert not kho_cung_chu_de(
        "ho_so_can_thiet", "Dạ, anh chị được vay với thời hạn từ 12 đến 60 tháng ạ.")
    assert not kho_cung_chu_de(
        "ho_so_can_thiet", "Dạ, hạn mức vay lên đến 500 triệu đồng ạ. Anh chị cần chuẩn bị "
                           "hồ sơ để em kiểm tra điều kiện xét duyệt cụ thể ạ.")
    assert kho_cung_chu_de(
        "ho_so_can_thiet", "Dạ anh chị cần CMND/CCCD, hộ khẩu hoặc KT3 và hợp đồng lao động ạ.")
    assert kho_cung_chu_de("lai_suat_san_pham", "Dạ, lãi suất từ 7.9%/năm ạ.")
    assert not kho_cung_chu_de("lai_suat_san_pham", "Dạ anh chị được vay từ 12 đến 60 tháng ạ.")
    # Mã luật không nằm trong bảng soát thì kho vẫn được ưu tiên như cũ.
    assert kho_cung_chu_de("uu_dai_hien_tai", "Dạ câu nào cũng được ạ.")
