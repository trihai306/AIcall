"""Bảng mẫu của bên A 13-10-2026: trả lời một ý, rồi hành động theo ngữ cảnh."""
from backend.pipeline.dan_dat import cau_hoi_tiep
from backend.pipeline.du_kien_khoan_vay import resolve
from backend.pipeline.hanh_dong_ngu_canh import dang_che, gon_cau, hanh_dong, ngu_canh
from backend.pipeline.luot_theo_ngu_canh import tra_loi_theo_ngu_canh
from backend.pipeline.ngu_canh_tai_lieu import toan_van
from backend.pipeline.tra_loi_khoan_vay import tra_loi

CHAO = {"role": "assistant", "content": "Dạ em chào anh chị, em là Lan bên Ngân hàng Quân đội ạ."}


def _chay(cac_luot):
    """Diễn lại đúng thứ tự pipeline: luật -> rút gọn -> hành động. Trả [(mã, câu, mã hỏi, lời nối)]."""
    vay = toan_van("vay tín chấp")
    h, da, vua, ra = [dict(CHAO)], set(), "", []
    for c in cac_luot:
        r = tra_loi_theo_ngu_canh(c, h) or tra_loi(c, vay, history=h)
        ma, cau = r or ("", "Dạ vâng ạ.")
        cau = gon_cau(ma, cau)
        khach = " ".join(m["content"] for m in h if m["role"] == "user") + " " + c
        dd = cau_hoi_tiep(ma_san_pham="vay_tin_chap", trang_thai=resolve(h, c),
                          loi_khach_ca_cuoc=khach, loi_khach_luot_nay=c, cau_tra_loi=cau,
                          da_hoi=da, ma_luat=ma, vua_hoi=vua, tai_lieu=vay, lich_su=h)
        if dd:
            da.add(dd[0])
        vua = dd[0] if dd else ""
        ra.append((ma, cau, dd[0] if dd else "", dd[1] if dd else ""))
        h += [{"role": "user", "content": c},
              {"role": "assistant", "content": (cau + " " + (dd[1] if dd else "")).strip()}]
    return ra


def test_dung_cac_dong_trong_bang_mau():
    kq = _chay(["lãi bao nhiêu", "cao thế", "vay được bao nhiêu", "thấp thế",
                "cần giấy tờ gì", "phức tạp vậy"])
    # 1.x quan tâm -> đồng tình + hỏi
    assert kq[0][0] == "lai_suat_san_pham" and kq[0][2] == "dt_tung_vay"
    # 2.x chê lãi -> trấn an bằng dòng ưu đãi CỦA TÀI LIỆU + hỏi
    assert kq[1][0] == "che_lai_cao" and kq[1][1] == "Dạ em hiểu băn khoăn của anh chị ạ."
    assert "giảm 0.5% lãi suất" in kq[1][3] and kq[1][3].endswith("?")
    # 3.x hạn mức: một ý, không còn lời rào
    assert kq[2][1] == "Dạ hạn mức tối đa của gói vay hiện là 500 triệu đồng ạ."
    assert kq[2][2] == "so_tien"
    # 4.x chê hạn mức ngay sau đó: không hỏi lại số tiền vừa hỏi
    assert kq[3][0] == "che_han_muc" and kq[3][2] == "dt_muc_dich"
    # 6.x chê thủ tục -> trấn an bằng dòng giải ngân
    assert kq[5][0] == "che_thu_tuc" and "24 giờ" in kq[5][3]


def test_khong_con_hoi_nhu_dien_phieu():
    kq = _chay(["muốn vay hai trăm triệu", "anh muốn vay mười hai tháng", "lương bảy triệu",
                "thế giờ anh có vay được không"])
    assert kq[0][1] == "Dạ 200 triệu đồng thì trong hạn mức ạ."
    assert kq[1][1] == "Dạ vay 12 tháng thì được ạ."
    assert kq[0][2] != "dt_tung_vay"          # khách nói số tiền thì không hỏi sang chuyện lãi
    assert kq[3][0] == "thu_nhap_dat_muc" and "7 triệu" in kq[3][1] and "5 triệu" in kq[3][1]
    assert "500 triệu" not in kq[3][1]
    # chỉ bỏ LỜI RÀO, không cắt câu hỏi chốt hay câu xác nhận đứng sau
    assert gon_cau("ky_han_trong_khung", "Dạ vay 2 đến 3 năm thì được ạ. Anh chị chốt giúp em một thời hạn cụ thể ạ?") \
        == "Dạ vay 2 đến 3 năm thì được ạ. Anh chị chốt giúp em một thời hạn cụ thể ạ?"
    assert gon_cau("nhu_cau_vay", "Dạ vay 16 tháng thì được ạ. Số tiền 400 triệu đồng cũng trong hạn mức, "
                   "còn hạn mức thực tế thì cần thẩm định theo hồ sơ ạ.") \
        == "Dạ vay 16 tháng thì được ạ. Số tiền 400 triệu đồng cũng trong hạn mức ạ."
    assert gon_cau("tinh_tra_gop", "Dạ tạm tính ạ. Bên em cho vay tối đa 500 triệu.") \
        == "Dạ tạm tính ạ. Bên em cho vay tối đa 500 triệu."


def test_moi_hanh_dong_chi_mot_lan():
    kq = _chay(["lãi bao nhiêu", "lãi suất thế nào em", "cao thế", "vẫn cao quá"])
    assert [k[2] for k in kq].count("dt_tung_vay") == 1
    assert [k[2] for k in kq].count("ta_luong_qua_nh") == 1


def test_khong_co_dong_tai_lieu_thi_khong_tu_che_loi_tran_an():
    hd = hanh_dong(ma_san_pham="vay_tin_chap", tai_lieu="# Vay\n- Lãi suất: từ 9%/năm\n",
                   lich_su=[dict(CHAO)], loi_khach="lãi cao thế", da_hoi=set(), da_biet_so_tien=False)
    assert hd == ("tran_an", "so_tien", "Anh chị đang cần khoảng bao nhiêu ạ?")


def test_ngu_canh_va_nhan_loi_che():
    assert dang_che("cao thế") and dang_che("sao phức tạp vậy em") and dang_che("lãi cắt cổ")
    assert not dang_che("lãi bao nhiêu") and not dang_che("vay cao nhất được bao nhiêu")
    nc = ngu_canh([dict(CHAO), {"role": "user", "content": "lãi bao nhiêu"},
                   {"role": "assistant", "content": "Dạ từ 7.9%/năm ạ."}], "cao thế")
    assert nc == {"da_biet_sp": True, "quan_tam": True, "che": True}
    assert hanh_dong(ma_san_pham="tiet_kiem", tai_lieu="", lich_su=[], loi_khach="lãi thấp thế",
                     da_hoi=set(), da_biet_so_tien=False) is None


def test_khach_tra_loi_cau_hoi_hanh_dong_khong_roi_xuong_mo_hinh():
    from backend.pipeline.hanh_dong_ngu_canh import dap_cau_hoi_hanh_dong as dap
    hoi = "Dạ lãi suất từ 7.9%/năm ạ. Anh chị đã từng vay tín chấp bao giờ chưa ạ?"
    assert dap("rồi anh từng vay rồi", hoi)[0] == "dap_tung_vay"
    assert "không sao" in dap("chưa em ạ", hoi)[1]
    assert dap("thế lãi tính thế nào", hoi) is None           # hỏi lại chuyện khác
    luong = "Bên em đang giảm 0.5% ạ. Anh chị có đang nhận lương qua ngân hàng không ạ?"
    assert "áp dụng" in dap("có anh nhận chuyển khoản", luong)[1]
    assert dap("anh nhận tiền mặt", luong)[1] == "Dạ không sao ạ."
    nghe = "Dạ vâng ạ. Anh chị đang đi làm hưởng lương hay tự kinh doanh ạ?"
    assert dap("ừ anh làm công ty lương chuyển khoản", nghe)[0] == "dap_nghe"
    assert dap("anh muốn vay hai trăm triệu", "Dạ em hiểu ạ. Anh chị định dùng khoản này vào việc gì ạ?") is None
    kq = _chay(["lãi bao nhiêu", "rồi anh từng vay rồi"])
    assert kq[1][0] == "dap_tung_vay" and kq[1][2] == "so_tien"   # nhận lời rồi mới hỏi tiếp
    assert dap("thủ tục nhanh không", "Dạ em hiểu ạ. Anh chị định dùng khoản này vào việc gì ạ?") is None
    assert dap("rồi anh từng vay rồi", luong) is None
    assert dap("rồi anh từng vay rồi", luong, hoi + " " + luong)[0] == "dap_tung_vay"   # trả lời muộn một lượt
    assert dap("cần giấy tờ gì", "Dạ em hiểu ạ. Anh chị định dùng khoản này vào việc gì ạ?") is None
    assert dap("sửa nhà em ạ", "Dạ em hiểu ạ. Anh chị định dùng khoản này vào việc gì ạ?")[0] == "dap_muc_dich"
