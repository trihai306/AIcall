"""Các lỗi của tầng luật lộ ra ở bộ thử 156 lượt ngày 12-10-2026."""

from pathlib import Path

from backend.pipeline.luot_thuong_gap import nhan_dang
from backend.pipeline.tra_loi_dieu_kien import nhan_xet_tuoi, tra_loi_dieu_kien
from backend.pipeline.tra_loi_khoan_vay import tra_loi

GOC = Path(__file__).resolve().parents[1] / "knowledge" / "products"


def _doc(ten: str) -> str:
    return (GOC / f"{ten}.md").read_text(encoding="utf-8")


def test_khong_ranh_khong_phai_khong_ranh_roi():
    assert nhan_dang("cháu ơi bác già rồi không rành cháu nói chậm thôi nhé") != "dang_ban"
    assert nhan_dang("anh không rảnh đâu") == "dang_ban"


def test_hai_chu_so_doc_roi_la_tuoi():
    ma, cau = tra_loi_dieu_kien("anh ba hai tuổi", "vay_tin_chap", _doc("vay_tin_chap"))
    assert ma == "dieu_kien_tuoi_khop" and "32" in cau


def test_khung_tuoi_tro_len_cua_the():
    doc = _doc("the_tin_dung")
    assert tra_loi_dieu_kien("chị mười chín tuổi làm thẻ được không", "the_tin_dung", doc)[0] \
        == "dieu_kien_tuoi_khop"
    assert tra_loi_dieu_kien("cháu mười sáu tuổi làm thẻ được không", "the_tin_dung", doc)[0] \
        == "dieu_kien_tuoi_khong_khop"
    assert "19 tuổi" in nhan_xet_tuoi("chị lương sáu triệu mười chín tuổi làm được không", doc)
    assert nhan_xet_tuoi("chị lương sáu triệu làm được không", doc) == ""


def test_khach_neu_ty_le_muon_vay():
    from backend.pipeline.ngu_canh_tai_lieu import toan_van
    tl = toan_van("vay mua nhà")
    ma, cau = tra_loi("nhà hai tỷ tám anh vay bảy mươi phần trăm", tl)
    assert ma == "ty_le_vay_trong_muc" and "1,96 tỷ" in cau
    assert tra_loi("nhà ba tỷ anh muốn vay 90%", tl)[0] == "ty_le_vay_vuot_muc"
    assert tra_loi("nhà 20 tỷ vay 70 phần trăm", tl)[0] == "ty_le_vay_vuot_muc"
    assert tra_loi("vay mua nhà lãi bao nhiêu phần trăm", tl)[0] == "lai_suat_san_pham"


def test_luoi_lai_suat_chap_nhan_phep_cong_cua_tai_lieu():
    from backend.pipeline.text_normalizer import chan_lai_suat_bia
    tl = _doc("tiet_kiem")
    dung = "Gửi online kỳ hạn 12 tháng thì lãi suất là 5,7% một năm ạ."
    assert chan_lai_suat_bia(dung, tl) == (dung, None)
    assert chan_lai_suat_bia("Gửi online 12 tháng thì lãi suất là 5,9% một năm ạ.", tl)[1]
    # sản phẩm không có dòng "cộng thêm" thì không được nới
    assert chan_lai_suat_bia("Lãi suất 8,1% ạ.", _doc("vay_tin_chap"))[1]


def test_ba_luat_cho_luot_qwen_hay_lech():
    from backend.pipeline.ngu_canh_tai_lieu import toan_van
    ma, cau = tra_loi("thế có cần sổ đỏ không em", toan_van("vay mua nhà"))
    assert ma == "can_so_do" and "sổ đỏ" in cau
    assert tra_loi("có cần sổ đỏ không", toan_van("vay tín chấp")) is None
    ke = ("chả là thế này em ạ nhà anh đang sửa cái bếp mà thợ nó báo giá cao quá vợ anh thì cứ "
          "giục mà tiền thì đang kẹt nên anh mới tính hỏi xem bên em cho vay thế nào")
    ma, cau = tra_loi(ke, toan_van("vay tín chấp"))
    assert ma == "gioi_thieu_vay" and "7.9%" in cau and "500 triệu" in cau
    assert tra_loi("anh muốn vay hai trăm triệu thì thế nào", toan_van("vay tín chấp"))[0] == "nhu_cau_vay"
    ma, cau = tra_loi("anh xài mỗi tháng chừng mười lăm hai chục củ thì nên làm thẻ gì", toan_van("thẻ tín dụng"))
    assert ma == "goi_y_the_theo_chi_tieu" and "15 đến 20 triệu" in cau and "Classic" in cau and "Gold" in cau
    assert tra_loi("anh tiêu tám trăm triệu một tháng nên làm thẻ nào", toan_van("thẻ tín dụng")) is None


def test_khach_moi_tu_van_san_pham():
    from backend.pipeline.ngu_canh_tai_lieu import toan_van
    ma, cau = tra_loi("ừ tư vấn với anh về sản phẩm thẻ tín dụng", toan_van("thẻ tín dụng"))
    assert ma == "moi_tu_van" and "Classic" in cau and cau.endswith("?")
    assert tra_loi("em tư vấn gửi tiết kiệm cho chị đi", toan_van("tiết kiệm"))[0] == "moi_tu_van"
    vay = toan_van("vay tín chấp")
    assert tra_loi("tư vấn cho anh về vay tín chấp", vay)[0] == "moi_tu_van"
    assert tra_loi("không cần tư vấn vay đâu", vay) is None
    assert tra_loi("ai giới thiệu em gọi cho anh vay thế", vay) is None
    # hỏi một hạng thẻ cụ thể vẫn là việc của luật riêng
    assert tra_loi("tư vấn thẻ gold cho anh", toan_van("thẻ tín dụng"))[0] == "gioi_thieu_loai_the"


def test_hai_luot_cut_cua_khach_gui_tiet_kiem():
    from backend.pipeline.ngu_canh_tai_lieu import toan_van
    tl = toan_van("tiết kiệm")
    ma, cau = tra_loi("năm chục triệu", tl)
    assert ma == "ghi_nhan_tien_gui" and "50 triệu" in cau
    ma, cau = tra_loi("kỳ hạn", tl)
    assert ma == "ky_han_tiet_kiem" and "1, 3, 6, 12, 24 và 36 tháng" in cau
    assert tra_loi("bác có trăm triệu để trong nhà", tl) is None
    # sản phẩm vay: số tiền trần vẫn là nhu cầu vay
    assert tra_loi("năm chục triệu", toan_van("vay tín chấp"))[0] == "nhu_cau_vay"


def test_khach_dong_vai_12_10():
    from backend.pipeline.ngu_canh_tai_lieu import toan_van
    vay, the = toan_van("vay tín chấp"), toan_van("thẻ tín dụng")
    ma, cau = tra_loi("anh đang còn nợ thẻ bên ngân hàng khác có sao không", vay)
    assert ma == "dang_co_no_khac" and "tất toán" not in cau
    assert tra_loi("anh có nợ xấu nhóm 2", vay)[0] == "no_xau_cau_nen_noi"
    ma, cau = tra_loi("thẻ này có mất phí gì không", the)
    assert ma == "phi_the" and "200.000" in cau
    assert tra_loi("chị lương tám triệu thì mở được hạng nào", the)[0] == "thu_nhap_dat_muc"
    assert nhan_dang("ừ để mai cô ra") == "hen_ra_quay"
    assert nhan_dang("mai gọi lại nhé") != "hen_ra_quay"


def test_khach_dong_vai_vong_hai():
    from backend.pipeline.ngu_canh_tai_lieu import toan_van
    from backend.pipeline.text_normalizer import chan_lai_suat_bia
    the, tk = toan_van("thẻ tín dụng"), toan_van("tiết kiệm")
    # "mất" là TỐN thời gian, không phải mất thẻ
    assert tra_loi("mở thẻ mất bao lâu", the)[0] == "chua_co_thong_tin_chu_de"
    assert tra_loi("thẻ chị bị mất rồi", the)[0] == "mat_the"
    # đáo hạn không có trong tài liệu: nói thật, không lấy câu rút trước hạn
    ma, cau = tra_loi("đến hạn anh không ra rút thì sao", tk)
    assert ma == "chua_co_thong_tin_chu_de" and "0.5%" not in cau
    assert nhan_dang("ok em ghi lại đi") == "dong_y_ghi_nhan"
    assert nhan_dang("ghi lại lãi suất cho anh") != "dong_y_ghi_nhan"
    doc = _doc("tiet_kiem")
    assert chan_lai_suat_bia("Gửi 6 tháng lãi 4.5%/năm, 12 tháng lãi 5.5%/năm, chênh nhau 1% ạ.", doc)[1] is None
    assert chan_lai_suat_bia("Gửi 12 tháng lãi 1% ạ.", doc)[1]


def test_khach_dong_vai_vong_ba():
    from backend.pipeline.chan_tu_che import chan_phan_theo_thu_nhap
    from backend.pipeline.luot_theo_ngu_canh import tra_loi_theo_ngu_canh
    from backend.pipeline.ngu_canh_tai_lieu import toan_van
    from backend.pipeline.sua_nghe_sai import neo_so_tien_vay
    vay, nha = toan_van("vay tín chấp"), toan_van("vay mua nhà")
    ma, cau = tra_loi("phí thẩm định có mất không", nha)
    assert ma == "phi_khoan_vay" and "miễn phí thẩm định tài sản" in cau
    assert tra_loi("trả trước hạn có mất phí không", vay)[0] == "phi_tra_truoc_han"
    assert tra_loi("hồ sơ nộp ở đâu", vay)[0] == "noi_nop_ho_so_chua_co"
    assert tra_loi("làm thủ tục ở đâu", toan_van("tiết kiệm")) is None
    assert neo_so_tien_vay("chị cần gấp tám chục triệu đóng học cho con", [], "vay tín chấp")[0] \
        == "chị cần vay gấp tám chục triệu đóng học cho con"
    assert neo_so_tien_vay("anh cần giấy tờ gì", [], "vay tín chấp")[1] == ""
    assert nhan_dang("chú nghe") == "chao_bat_may"
    h = [{"role": "assistant", "content": "Hiện bên em có mức từ 7.9% một năm ạ."}]
    assert tra_loi_theo_ngu_canh("bảy phẩy chín là một năm hay một tháng", h)[0] == "don_vi_lai"
    assert tra_loi_theo_ngu_canh("vay một năm hay hai năm thì hơn", h) is None
    assert chan_phan_theo_thu_nhap(
        "Anh chuẩn bị 500 triệu cho đất giá 1,2 tỷ thì đủ điều kiện vay mua bất động sản rồi ạ.")[1]
    cau = "Dạ anh chị cần thu nhập từ 5 triệu mới đủ điều kiện ạ."
    assert chan_phan_theo_thu_nhap(cau) == (cau, "")


def test_khach_dong_vai_vong_bon():
    from backend.pipeline.chan_tu_che import chan_loai_lai_bia
    from backend.pipeline.chan_tuan_thu import chan_gan_thu_nhap
    from backend.pipeline.ngu_canh_tai_lieu import toan_van
    vay, nha, tk, the = (toan_van(x) for x in ("vay tín chấp", "vay mua nhà", "tiết kiệm", "thẻ tín dụng"))
    # khách xưng cô/chú hoặc bỏ chủ ngữ vẫn là thu nhập của chính khách
    for cau in ("cô lương mười bốn triệu chuyển khoản", "lương mười bốn triệu"):
        ma, dap = tra_loi(cau, vay)
        assert ma == "ghi_nhan_thu_nhap" and "14 triệu" in dap
    assert tra_loi("lương bao nhiêu thì vay được", vay)[0] != "ghi_nhan_thu_nhap"
    assert (tra_loi("lương nó hai mươi lăm triệu", vay) or ("",))[0] != "ghi_nhan_thu_nhap"
    # mô hình lấy số của điều kiện sản phẩm gán cho khách
    k = "cô lương mười bốn triệu chuyển khoản"
    assert chan_gan_thu_nhap("Thu nhập 5 triệu đồng của cô đã vượt mức yêu cầu ạ.", khach_da_noi=k)[1]
    assert chan_gan_thu_nhap("Thu nhập 14 triệu đồng của cô đã vượt mức yêu cầu ạ.", khach_da_noi=k)[1] is None
    assert chan_gan_thu_nhap("Điều kiện là thu nhập từ 5 triệu đồng một tháng ạ.", khach_da_noi=k)[1] is None
    # hỏi tiền lãi kèm chữ online phải ra con số
    ma, dap = tra_loi("mười triệu gửi sáu tháng online được bao nhiêu lãi", tk)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem" and "4,7%" in dap
    assert tra_loi("gửi sáu tháng lãi bao nhiêu", tk)[0] == "lai_tiet_kiem_theo_ky"
    # hạng thẻ theo hạn mức khách muốn
    ma, dap = tra_loi("muốn hạn mức ba trăm triệu thì làm thẻ nào", the)
    assert ma == "hang_the_theo_han_muc" and "Platinum" in dap and "Classic" not in dap
    assert tra_loi("hạn mức cao nhất được bao nhiêu", the)[0] == "han_muc_the"
    # lãi cố định hay thả nổi: đọc tài liệu, không có thì nói chưa có
    ma, dap = tra_loi("lãi có thay đổi không hay cố định", vay)
    assert ma == "lai_co_dinh_hay_tha_noi" and "thả nổi" not in dap and "7.9%" in dap
    assert "thả nổi" in tra_loi("lãi cố định hay thả nổi", nha)[1]
    assert tra_loi("lãi có thay đổi không", tk) is None
    assert (tra_loi("thế lãi sáu rưỡi là cố định mấy năm", nha) or ("",))[0] != "lai_co_dinh_hay_tha_noi"
    assert chan_loai_lai_bia("Lãi suất vay tín chấp của bên em là thả nổi ạ. Mức cụ thể chuyên viên sẽ báo.", vay)[1]
    cau = "Lãi suất sau ưu đãi thả nổi theo thị trường ạ."
    assert chan_loai_lai_bia(cau, nha) == (cau, "")


def test_khach_dong_vai_vong_nam():
    from backend.pipeline.ngu_canh_tai_lieu import toan_van
    from backend.pipeline.sua_nghe_sai import sua_nghe_sai
    nha, tk, the = (toan_van(x) for x in ("vay mua nhà", "tiết kiệm", "thẻ tín dụng"))
    # lời nói không có dấu phẩy: "tỷ rưỡi" và "hai mươi năm" phải tách khỏi "tháng trả"
    cau = sua_nghe_sai("vay một tỷ rưỡi hai mươi năm tháng trả bao nhiêu")[0]
    ma, dap = tra_loi(cau, nha)
    assert ma == "tinh_tra_gop" and "1,5 tỷ" in dap and "20 năm" in dap
    assert sua_nghe_sai("vay năm tháng trả bao nhiêu")[0] == "vay năm tháng trả bao nhiêu"
    assert sua_nghe_sai("lương năm triệu rưỡi một tháng")[0] == "lương năm triệu rưỡi một tháng"
    # "phí rút" của thẻ không phải phí thường niên
    assert tra_loi("phí rút là bao nhiêu", the)[0] == "chua_co_thong_tin_chu_de"
    assert tra_loi("phí thường niên bao nhiêu", the)[0] == "phi_the"
    # số tiền khách nói kiểu "có ... muốn gửi" phải được nhớ sang lượt hỏi tiền lãi
    h = [{"role": "user", "content": "em có năm chục triệu muốn gửi"},
         {"role": "assistant", "content": "Dạ anh chị muốn gửi kỳ hạn bao lâu ạ?"},
         {"role": "user", "content": "gửi một năm lãi bao nhiêu phần trăm"},
         {"role": "assistant", "content": "Dạ kỳ hạn 12 tháng lãi suất 5,5% một năm ạ."}]
    ma, dap = tra_loi("thế một năm được bao nhiêu tiền", tk, history=h)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem" and "50 triệu" in dap and "2,75 triệu" in dap


def test_khach_ke_so_tien_muon_gui_va_hoi_uu_dai():
    from backend.pipeline.ngu_canh_tai_lieu import toan_van
    from backend.pipeline.streaming_pipeline import kho_cung_chu_de
    tk, the = toan_van("tiết kiệm"), toan_van("thẻ tín dụng")
    for cau, so in (("chú có hai trăm triệu muốn gửi", "200 triệu"),
                    ("em có năm chục triệu muốn gửi", "50 triệu"),
                    ("chị muốn gửi hai trăm triệu", "200 triệu")):
        ma, dap = tra_loi(cau, tk)
        assert ma == "ghi_nhan_tien_gui" and so in dap
    assert (tra_loi("gửi được năm chục triệu không", tk) or ("",))[0] != "ghi_nhan_tien_gui"
    ma, dap = tra_loi("có ưu đãi gì không", the)
    assert ma == "uu_dai_hien_tai" and "hoàn tiền 3%" in dap
    assert not kho_cung_chu_de("uu_dai_hien_tai", "Dạ đây là chương trình ưu đãi ngân hàng đang dành "
                               "cho khách hàng ạ. Anh chị muốn nghe trước về lãi suất, hạn mức hay hồ sơ thủ tục ạ?")
    assert kho_cung_chu_de("uu_dai_hien_tai", "Dạ thẻ đang miễn phí thường niên năm đầu ạ.")


def test_khach_dong_vai_vong_sau():
    from backend.pipeline.hanh_dong_ngu_canh import dang_che, dap_cau_hoi_hanh_dong as dap, hanh_dong
    from backend.pipeline.ngu_canh_tai_lieu import toan_van
    from backend.pipeline.xung_ho_khach import xung_ho_theo_loi
    vay, nha, the, tk = (toan_van(x) for x in ("vay tín chấp", "vay mua nhà", "thẻ tín dụng", "tiết kiệm"))
    # "có được không" về chuyện khác không được đáp bằng thu nhập đã khai
    h = [{"role": "user", "content": "lương mười tám triệu"}, {"role": "assistant", "content": "Dạ vâng."}]
    assert tra_loi("quẹt nước ngoài có được không", the, history=h)[0] == "chua_co_thong_tin_chu_de"
    assert tra_loi("thế giờ anh có vay được không", vay, history=h)[0] == "thu_nhap_dat_muc"
    # đổi kỳ hạn ngay sau khi vừa tính: giữ số tiền, tính lại
    h2 = [{"role": "assistant", "content": "Dạ em tạm tính ạ. Nếu được duyệt 150 triệu đồng trong 2 năm "
                                           "thì tháng đầu trả khoảng 7,2 triệu đồng, các tháng sau giảm dần."}]
    ma, dap_ = tra_loi("nhiều thế kéo dài ba năm thì sao", vay, history=h2)
    assert ma == "tinh_tra_gop" and "150 triệu đồng trong 3 năm" in dap_
    assert tra_loi("ba năm thì sao", vay, history=h) is None                 # chưa tính gì thì không đoán
    assert hanh_dong(ma_san_pham="vay_tin_chap", tai_lieu=vay, lich_su=h2, loi_khach="nhiều thế kéo dài ba năm thì sao",
                     da_hoi=set(), da_biet_so_tien=True, ma_luat="tinh_tra_gop") is None
    # giá nhà + vốn sẵn có -> số cần vay, tỷ lệ đọc từ tài liệu
    ma, dap_ = tra_loi("căn một tỷ tám cô có sáu trăm", nha)
    assert ma == "can_vay_theo_gia_nha" and "1,2 tỷ" in dap_ and "80%" in dap_
    assert "chuẩn bị thêm khoảng 300 triệu" in tra_loi("căn hộ ba tỷ anh có sẵn ba trăm triệu", nha)[1]
    assert (tra_loi("căn một tỷ tám cô có sáu trăm", vay) or ("",))[0] != "can_vay_theo_gia_nha"
    # các lượt tạm
    assert nhan_dang("chị nghe em") == "chao_bat_may"
    assert xung_ho_theo_loi(["ai gọi bác đấy", "bác có ít tiền hưu muốn gửi"]) == "bác"
    assert xung_ho_theo_loi(["chị có chương trình gì không"]) == ""
    assert dang_che("thế cũng cao phết") and dang_che("có thế thôi à ít nhỉ") and not dang_che("vay nhiều ạ")
    assert dap("bác không biết dùng điện thoại đâu",
               "Dạ. Anh chị quen giao dịch trên điện thoại hay ra quầy ạ?")[0] == "dap_kenh_quay"
    assert tra_loi("sau hai năm lãi thả nổi là sao", nha)[0] == "nghia_loai_lai"   # hỏi NGHĨA, không đọc lại mức lãi
    assert "thẩm định" not in tra_loi("bác bảy mươi hai tuổi rồi có gửi được không", tk)[1]
    assert "thẩm định" in tra_loi("anh năm mươi tuổi có vay được không", vay)[1]


def test_cac_luot_tam_con_lai_cua_vong_sau():
    from backend.pipeline.ngu_canh_tai_lieu import toan_van
    vay, nha, the, tk = (toan_van(x) for x in ("vay tín chấp", "vay mua nhà", "thẻ tín dụng", "tiết kiệm"))
    ma, dap = tra_loi("chị lương mười tám triệu thì hạn mức được bao nhiêu", the)
    assert ma == "han_muc_the_theo_thu_nhap" and "18 triệu" in dap and "thẩm định" in dap
    assert tra_loi("hạn mức được bao nhiêu", the)[0] == "han_muc_the"
    ma, dap = tra_loi("quẹt nước ngoài có được không", the)
    assert ma == "chua_co_thong_tin_chu_de" and "nước ngoài" in dap
    ma, dap = tra_loi("thế mỗi tháng lĩnh lãi được không", tk)
    assert ma == "linh_lai_tiet_kiem" and "hàng tháng" in dap and "quầy" not in dap
    assert tra_loi("gửi một năm thì lãi bao nhiêu", tk)[0] == "lai_tiet_kiem_theo_ky"
    ma, dap = tra_loi("sau hai năm lãi thả nổi là sao", nha)
    assert ma == "nghia_loai_lai" and "điều chỉnh định kỳ" in dap and "8-10%" in dap
    ma, dap = tra_loi("lãi cố định là gì", vay)
    assert ma == "nghia_loai_lai" and "giữ nguyên" in dap and "Với gói này" not in dap
    assert tra_loi("lãi cố định hay thả nổi", nha)[0] == "lai_co_dinh_hay_tha_noi"
    assert nhan_dang("lại ngân hàng à dạo này gọi suốt") == "bi_goi_nhieu"
    assert nhan_dang("mai em gọi lại nhé") != "bi_goi_nhieu" and nhan_dang("ngân hàng nào đấy") != "bi_goi_nhieu"


def test_khach_dong_vai_vong_bay_nho_du_kien_khach_ke():
    from backend.pipeline.ngu_canh_tai_lieu import toan_van
    from backend.pipeline.sua_nghe_sai import neo_du_kien_ke as neo, sua_nghe_sai
    vay, nha, the, tk = (toan_van(x) for x in ("vay tín chấp", "vay mua nhà", "thẻ tín dụng", "tiết kiệm"))

    def H(*loi):
        return [{"role": "user" if i % 2 == 0 else "assistant", "content": c} for i, c in enumerate(loi)]
    # tiết kiệm: "có khoản X đang để không" -> nhớ là tiền gửi
    moi, _ = neo("chị có khoản năm trăm triệu đang để không", [], "tiết kiệm")
    assert moi == "chị muốn gửi năm trăm triệu đang để không"
    assert tra_loi(moi, tk)[0] == "ghi_nhan_tien_gui"
    h = H(moi, "Dạ em ghi nhận ạ. Chị muốn gửi kỳ hạn bao lâu ạ?")
    ma, dap = tra_loi("sáu tháng thì lãi được bao nhiêu tiền", tk, history=h)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem" and "500 triệu" in dap
    h += H("sáu tháng thì lãi được bao nhiêu tiền", dap)
    ma, dap = tra_loi("nếu chị cần rút gấp một trăm triệu thì sao", tk, history=h)
    assert ma == "lai_rut_mot_phan_tiet_kiem" and "400 triệu" in dap
    assert neo("gửi năm trăm triệu lãi bao nhiêu", [], "tiết kiệm")[1] == ""
    assert neo("chị có hai sổ rồi", [], "tiết kiệm")[1] == ""
    # mua nhà: giá nhà lượt trước + vốn lượt này -> số cần vay, nhớ sang lượt hỏi trả góp
    moi, _ = neo("anh có sẵn một tỷ", ["anh nghe", "anh đang định mua nhà phố ba tỷ rưỡi"], "vay mua nhà")
    assert moi == "anh có sẵn một tỷ, tức cần vay 2,5 tỷ"
    assert tra_loi(moi, nha)[0] == "nhu_cau_vay"
    h = H("anh đang định mua nhà phố ba tỷ rưỡi", "Dạ.", moi, "Dạ 2,5 tỷ đồng thì trong hạn mức ạ.")
    ma, dap = tra_loi("vay hai mươi năm thì tháng đầu trả bao nhiêu", nha, history=h)
    assert ma == "tinh_tra_gop" and "2,5 tỷ đồng trong 20 năm" in dap
    ma, dap2 = tra_loi("cao quá kéo lên hai lăm năm xem", nha,
                       history=h + H("vay hai mươi năm thì tháng đầu trả bao nhiêu", dap))
    assert ma == "tinh_tra_gop" and "25 năm" in dap2
    moi, _ = neo("căn một tỷ tám cô có sáu trăm", [], "vay mua nhà")
    assert moi.endswith(", tức cần vay 1,2 tỷ") and tra_loi(moi, nha)[0] == "can_vay_theo_gia_nha"
    assert neo("anh có sẵn một tỷ", ["alo"], "vay mua nhà")[1] == ""          # chưa biết giá nhà
    assert neo("anh có sẵn một tỷ", ["nhà ba tỷ"], "vay tín chấp")[1] == ""
    # "thì tháng bao nhiêu" là hỏi khoản trả góp
    cau = sua_nghe_sai("trả trong một năm rưỡi thì tháng bao nhiêu")[0]
    ma, dap = tra_loi(cau, vay, history=H("vay khoảng tám chục triệu thôi", "Dạ."))
    assert ma == "tinh_tra_gop" and "80 triệu đồng trong 18 tháng" in dap
    # hai lượt còn lại
    ma, dap = tra_loi("nếu em không trả hết thì lãi tính sao", the)
    assert ma == "lai_the_chua_tra_het" and "55 ngày" in dap and "dư nợ giảm dần" not in dap
    assert tra_loi("trả chậm thì lãi tính sao", vay) is None
    assert nhan_dang("chị đang bận em nói nhanh nhé") == "noi_nhanh"
    assert nhan_dang("anh đang bận") == "dang_ban"
    assert nhan_dang("à à anh đang lái xe em nói nhanh lên") == "dang_ban"
    assert nhan_dang("em nói nhanh quá anh không nghe kịp") != "noi_nhanh"
    assert nhan_dang("dạ alo") == "chao_bat_may"
