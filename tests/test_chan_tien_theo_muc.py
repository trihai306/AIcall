"""Lưới chặn tiền phải đối chiếu theo MỤC tài liệu, và không được tha khi
ngữ cảnh rỗng số.

Hai lỗ hổng bắt được 05-09-2026 khi chạy lại cuộc gọi thật `4cd44fb7` bằng
chính giọng khách (`scripts/goi_lai_bang_giong_that.py`). Khách hỏi hạn mức,
máy nghe sai thành "hắn mừng được mời nhiều", AI trả lời:

    "Hạn mức vay tín chấp bên em từ 200 triệu đến ba trăm triệu ạ."

Tài liệu ghi 500 triệu. Sai, và LẶP LẠI cả 3 lần chạy độc lập.

LỖ HỔNG A - ngữ cảnh rỗng số thì lưới THA HẲN.
`ngu_canh` thật của lượt đó chỉ 63 ký tự ("ngân hàng nào dám cho vay quá nhiều
ạ / ợ trước hạn sau 3 năm") vì câu hỏi méo kéo RAG đi lạc. Không có số tiền nào
-> `hop_le` rỗng -> `if not hop_le: return text, None`. Số bịa đi thẳng ra loa.
Đây mới là đường mà câu "300 triệu" thật sự đi qua.

LỖ HỔNG B - có tài liệu thì lại lấy số của MỤC KHÁC.
Với ngữ cảnh đầy đủ, lưới chặn nhưng sửa "200 triệu" -> "ba trăm triệu", vì
`vay_tin_chap.md` có dòng ví dụ trả góp "Vay 300 triệu, 48 tháng" và 300 là số
GẦN NHẤT. Kết quả "từ ba trăm triệu đến ba trăm triệu" - vô nghĩa, mà vẫn sai
(hạn mức đúng là 500). Lưới chỉ hỏi "số này có trong tài liệu không", không hỏi
"số này thuộc MỤC nào".

Ràng buộc #2 trong docstring `chan_tien_sai` ("để nguyên kể cả khi nằm ở phần
ví dụ") vẫn ĐÚNG ở thời điểm nó được viết: câu dẫn ví dụ trả góp cần đúng con số
ví dụ. Nay siết lại CÓ ĐIỀU KIỆN - chỉ khi câu nêu rõ chủ đề và mục đó có số.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from backend.pipeline.text_normalizer import CAU_KIEM_TRA_LAI, chan_tien_sai

# Tài liệu THẬT của vay tín chấp: hạn mức ở một mục, ví dụ trả góp ở mục khác.
TL_DAY_DU = """# Vay Tín Chấp Cá Nhân

## Lãi suất
- Lãi suất: từ 7.9%/năm

## Hạn mức
- Hạn mức: lên đến 500 triệu đồng

## Ví dụ khoản vay
- Vay 200 triệu, 36 tháng: trả hàng tháng khoảng 6.8 triệu
- Vay 300 triệu, 48 tháng: trả hàng tháng khoảng 8.2 triệu
"""

# Ngữ cảnh THẬT của lượt 6, đo bằng rag.retrieve(top_k=2) đúng như pipeline.
NC_RONG_SO = "ngân hàng nào dám cho vay quá nhiều ạ\n---\nợ trước hạn sau 3 năm"

CAU_LOI = ("Hạn mức vay tín chấp bên em từ 200 triệu đến ba trăm triệu ạ. "
           "Anh/chị cần vay số tiền bao nhiêu?")


# --- LỖ HỔNG A: ngữ cảnh không có số tiền nào -------------------------------

def test_chan_khi_ngu_canh_khong_co_so_tien():
    """Đúng câu đã tới tai khách trong cuộc gọi thật."""
    ra, sua = chan_tien_sai(CAU_LOI, NC_RONG_SO,
                            khach_noi="hắn mừng được mời nhiều")
    assert sua is not None, "phải chặn - đây là số bịa từ trí nhớ model"
    assert "200 triệu" not in ra and "ba trăm triệu" not in ra
    assert CAU_KIEM_TRA_LAI in ra


def test_ngu_canh_rong_nhung_so_do_KHACH_neu_thi_tha():
    """AI nhắc lại con số của khách là đúng, kể cả khi tài liệu rỗng."""
    ra, sua = chan_tien_sai("Dạ anh vay 80 triệu đúng không ạ.", NC_RONG_SO,
                            khach_noi="anh cần vay 80 triệu")
    assert sua is None and "80 triệu" in ra


@pytest.mark.parametrize("cau", [
    "Hồ sơ duyệt trong 24 giờ ạ.",
    "Anh sinh năm 1990 phải không ạ.",
    "Số điện thoại của em là 0912345678 ạ.",
    "Dạ em xin phép kiểm tra lại thông tin ạ.",
])
def test_ngu_canh_rong_khong_chan_cau_khong_co_tien(cau):
    """Chỉ chặn khi câu thật sự nêu SỐ TIỀN."""
    ra, sua = chan_tien_sai(cau, NC_RONG_SO, khach_noi="")
    assert sua is None, f"đã chặn nhầm: {ra}"
    assert ra == cau


# --- LỖ HỔNG B: đối chiếu theo mục ------------------------------------------

def test_han_muc_khong_duoc_lay_so_cua_muc_vi_du():
    """200/300 có thật trong tài liệu, nhưng ở mục VÍ DỤ - không phải hạn mức.

    Thu hẹp theo mục VẪN cần dù nay thay cả câu: không thu hẹp thì 200/300 đều
    "có trong tài liệu" nên lưới tha, và câu sai đi thẳng ra loa.
    """
    ra, sua = chan_tien_sai(CAU_LOI, TL_DAY_DU, khach_noi="")
    assert sua is not None, "phải chặn"
    assert ra == CAU_KIEM_TRA_LAI, f"phải thay cả câu: {ra}"
    assert "ba trăm triệu" not in ra and "200 triệu" not in ra


def test_khong_de_lai_dai_trung_lap():
    """Thay xong không được ra "từ năm trăm triệu đến năm trăm triệu".

    Nay thay cả câu nên dải trùng không còn sinh ra nữa, nhưng `_DAI_TRUNG_RE`
    vẫn giữ: đường sửa-số vẫn sống cho con số khách vừa nêu.
    """
    ra, _ = chan_tien_sai(CAU_LOI, TL_DAY_DU, khach_noi="")
    assert "đến năm trăm triệu" not in ra, f"dải trùng chưa rút gọn: {ra}"


def test_cau_dan_vi_du_tra_gop_van_giu_nguyen_so():
    """Van an toàn: câu KHÔNG nói về hạn mức thì số ví dụ vẫn hợp lệ."""
    cau = "Vay 300 triệu trong 48 tháng thì trả hàng tháng khoảng 8.2 triệu ạ."
    ra, sua = chan_tien_sai(cau, TL_DAY_DU, khach_noi="")
    assert sua is None, f"đã siết oan câu dẫn ví dụ: {ra}"
    assert "300 triệu" in ra


def test_cau_han_muc_dung_so_thi_khong_dung_toi():
    ra, sua = chan_tien_sai("Hạn mức vay tín chấp lên đến 500 triệu đồng ạ.",
                            TL_DAY_DU, khach_noi="")
    assert sua is None and "500 triệu" in ra


def test_khong_nhan_ra_chu_de_thi_giu_hanh_vi_cu():
    """Van an toàn: câu không nêu chủ đề nào -> vẫn đối chiếu cả tài liệu."""
    cau = "Bên em hỗ trợ 300 triệu ạ."
    ra, sua = chan_tien_sai(cau, TL_DAY_DU, khach_noi="")
    assert sua is None, f"300 có trong tài liệu, không được chặn: {ra}"


# --- HOI QUY do chinh ban sua nay, bat duoc 05-09-2026 khi chay 8 vong --------
#
# `scripts/do_luoi_nhieu_vong.py` 8 vong x 15 luot. Nhom "han muc mo ho" no 8/8
# vong, va no lam cau tra loi TE DI chu khong tot len:
#
#   AI  : "Han muc vay tin chap thap nhat la 50 trieu, cao nhat len den 500 trieu"
#   luoi: 50 trieu -> nam tram trieu
#   ra  : "thap nhat la nam tram trieu, cao nhat len den 500 trieu"  <- vo nghia
#
# Goc: thu hep ve muc "Han muc" chi con {500 trieu}, nen MOI so khac trong cau
# deu bi ep ve 500 - ke ca muc san (50 trieu) von hop ly va vo hai.
#
# Phan biet duoc hai truong hop bang mot dau hieu don gian: cau da nhac DUNG so
# cua muc chua. Co roi thi model dang bam tai lieu, chi them mot muc san hop ly
# -> de yen. Khong co so nao cua muc thi no dang tu bia ca dai -> moi can chan.

def test_giu_nguyen_khi_cau_da_nhac_dung_so_cua_muc():
    """Dai "tu 100 den 500 trieu": 500 la dung trong tai lieu -> khong duoc dung."""
    cau = "Hạn mức vay tín chấp từ 100 triệu đồng đến 500 triệu đồng ạ."
    ra, sua = chan_tien_sai(cau, TL_DAY_DU, khach_noi="")
    assert sua is None, f"da lam hong cau von dung: {ra}"
    assert "100 triệu" in ra and "500 triệu" in ra


def test_giu_nguyen_muc_san_khi_da_co_tran_dung():
    cau = ("Hạn mức vay tín chấp thấp nhất là 50 triệu đồng, "
           "cao nhất lên đến 500 triệu đồng ạ.")
    ra, sua = chan_tien_sai(cau, TL_DAY_DU, khach_noi="")
    assert sua is None, f"muc san hop ly bi ep ve tran: {ra}"
    assert "50 triệu" in ra


def test_van_chan_khi_cau_KHONG_co_so_nao_cua_muc():
    """Ca xau that: "tu 200 den 300" - khong nhac 500, tu bia ca dai."""
    ra, sua = chan_tien_sai(CAU_LOI, TL_DAY_DU, khach_noi="")
    assert sua is not None
    assert ra == CAU_KIEM_TRA_LAI and "ba trăm triệu" not in ra


def test_van_chan_so_VUOT_tran_du_cau_da_nhac_so_dung():
    """Tha muc san la mot chuyen, tha noi vong len tran la chuyen khac."""
    cau = "Hạn mức vay tín chấp từ 500 triệu đồng đến 2 tỷ đồng ạ."
    ra, sua = chan_tien_sai(cau, TL_DAY_DU, khach_noi="")
    assert sua is not None, f"2 ty phai bi chan: {ra}"
    assert "2 tỷ" not in ra


def test_chu_dinh_so_khong_duoc_lam_hong_phep_so_voi_muc():
    """Mô hình hay viết dính "lên đến500 triệu" - `_TIEN_SO_RE` đòi ranh giới
    trước số nên bỏ sót đúng con số ĐÚNG, phép so với mục thành rỗng, rồi mức
    sàn hợp lý bị ép về trần.

    Bắt được ở lần chạy 8 vòng THỨ HAI (sau khi đã vá lần một): vẫn hỏng 6 lần,
    tất cả đều mang chuỗi "lên đến500". Bản vá lần một dùng câu có dấu cách nên
    test xanh mà thực địa vẫn đỏ - phải lấy ĐÚNG chuỗi quan sát được làm test.
    """
    cau = ("Hạn mức vay tín chấp thấp nhất là 50 triệu đồng, "
           "cao nhất lên đến500 triệu đồng ạ.")
    ra, sua = chan_tien_sai(cau, TL_DAY_DU, khach_noi="")
    assert sua is None, f"chu dinh lam luoi ep muc san ve tran: {ra}"
    assert "50 triệu" in ra


# --- ĐỔI THIẾT KẾ 05-09-2026: thay CẢ CÂU thay vì thay số ---------------------
#
# Ba lần vá liên tiếp không dứt được cùng một kiểu hỏng (8 -> 6 -> 7 ca qua ba
# lần chạy 8 vòng). Gốc không nằm ở các biến thể mà ở chính cơ chế: "thay số bịa
# bằng số gần nhất trong tài liệu" biến một câu sai thành một câu KHÁC cũng sai,
# đôi khi vô lý hơn:
#
#   AI   : "gửi tiết kiệm tối thiểu 5 triệu"     (bịa, nhưng hợp lý)
#   lưới : "gửi tiết kiệm tối thiểu 200 triệu"   (bịa, và vô lý hơn)
#
# `knowledge/` không có tài liệu tiết kiệm nào - 200 triệu là hạn mức VAY TÍN
# CHẤP bị RAG kéo nhầm vào. Lưới lấy số của sản phẩm khác để "sửa".
#
# Nay: không có căn cứ thì THAY CẢ CÂU, giống `chan_lai_suat_bia`. Thà im còn
# hơn nói số sai.
#
# GIỮ LẠI một trường hợp thay số: con số KHÁCH VỪA NÊU. "khách nói 80, model nói
# 78" -> sửa về 80 vẫn đúng và hữu ích hơn hẳn việc im lặng.

TL_VAY = "# Vay Tín Chấp\n\n## Hạn mức\n- Hạn mức: lên đến 500 triệu đồng\n"


def test_khong_co_can_cu_thi_thay_ca_cau():
    """Hỏi tiết kiệm, tài liệu chỉ có vay tín chấp -> không được mượn số 500."""
    cau = "Dạ hiện tại bên em quy định gửi tiết kiệm tối thiểu 5 triệu đồng ạ."
    ra, sua = chan_tien_sai(cau, TL_VAY, khach_noi="")
    assert sua is not None
    assert ra == CAU_KIEM_TRA_LAI, f"phai thay ca cau, khong thay so: {ra}"
    assert "500" not in ra and "năm trăm" not in ra


def test_van_sua_ve_con_so_KHACH_vua_neu():
    """Ngoại lệ cố ý giữ: số của khách là căn cứ chắc chắn nhất."""
    ra, sua = chan_tien_sai("anh vay 78 triệu đồng", TL_VAY,
                            khach_noi="anh cần vay 80 triệu")
    assert "tám mươi triệu" in ra
    assert ra != CAU_KIEM_TRA_LAI, "cau nay sua duoc thi dung im lang"


def test_noi_vong_len_tran_thi_thay_ca_cau():
    ra, sua = chan_tien_sai("Hạn mức vay tín chấp lên đến 2 tỷ đồng ạ.", TL_VAY)
    assert sua is not None and ra == CAU_KIEM_TRA_LAI


def test_cau_dung_van_khong_bi_dung_toi():
    cau = "Hạn mức vay tín chấp lên đến 500 triệu đồng ạ."
    ra, sua = chan_tien_sai(cau, TL_VAY, khach_noi="")
    assert sua is None and ra == cau
