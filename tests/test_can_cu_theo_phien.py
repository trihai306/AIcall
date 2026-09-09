"""Căn cứ của lưới chặn số phải theo CẢ CUỘC GỌI, không chỉ lượt hiện tại.

VÌ SAO CÓ FILE NÀY. Cuộc gọi thật `009d9fb3` (06-09-2026), số 0396130621. Log
backend ghi lại hai lần chặn, và CẢ HAI ĐỀU CHẶN NHẦM:

    09:17:35  AI  : "Lãi suất hiện tại là 7.9%/năm và hạn mức lên đến 500 triệu"
                    -> KHÔNG bị chặn, tức tài liệu lượt đó CÓ 7.9%
    09:17:51  CHẶN LÃI SUẤT BỊA: bịa 7.9% (tài liệu chỉ có 8.5%)
                    'Dạ lãi suất 7.9%/năm này đã là mức ưu đãi tốt rồi ạ.'

    09:17:32  khách: "anh muốn vay tầm bốn trăm triệu"
    09:18:10  CHẶN TIỀN SAI: 400 triệu -> thay cả câu (không có căn cứ)

Cùng một gốc: lưới đối chiếu `ngu_canh` của ĐÚNG lượt đang chạy, mà RAG mỗi
lượt lôi về mảnh khác nhau. Câu "lãi cao quá có cách nào giảm" không kéo về bảng
lãi suất, thế là con số vừa nói đúng ở lượt trước thành "bịa".

Hậu quả người dùng nghe thấy, và là câu họ than: *"hỏi lãi cao vậy sao nó trả
lời 1 kiểu"*. Cả hai lượt đều bị thay bằng CÙNG một câu mẫu
`CAU_KIEM_TRA_LAI`, nên nghe như AI chỉ biết mỗi một câu. Mô hình thật ra trả
lời khác nhau - chính lưới làm chúng giống nhau.

CHỖ PHẢI CẨN THẬN: sổ căn cứ chỉ được ghi TÀI LIỆU và LỜI KHÁCH. Ghi lời AI vào
là để nó tự bảo chứng cho số nó bịa - lần sau nói lại con số đó thì lưới hết
chặn được.
"""
import pytest

from backend.pipeline.so_can_cu import SoCanCu
from backend.pipeline.text_normalizer import (CAU_KIEM_TRA_LAI, chan_lai_suat_bia,
                                              chan_so_sai, chan_tien_sai)

CAU_LAI = "Dạ lãi suất 7.9%/năm này đã là mức ưu đãi tốt rồi ạ."
TL_KHAC = "Phí trả nợ trước hạn 8.5% trên dư nợ còn lại."


# --- Lãi suất: số đã có căn cứ ở lượt trước ------------------------------

def test_lai_suat_da_co_can_cu_luot_truoc_thi_khong_chan():
    ra, sua = chan_lai_suat_bia(CAU_LAI, TL_KHAC,
                                can_cu_them="Lãi suất từ 7.9%/năm.")
    assert sua is None, f"chặn nhầm: {sua}"
    assert ra == CAU_LAI


def test_khong_co_so_thi_van_chan_nhu_cu():
    """Hành vi cũ phải giữ nguyên - đây mới là ca lưới sinh ra để bắt."""
    ra, sua = chan_lai_suat_bia(CAU_LAI, TL_KHAC)
    assert sua is not None
    assert ra == CAU_KIEM_TRA_LAI


def test_so_khong_rua_duoc_so_bia():
    """Sổ có 7.9% không làm 4.2% thành hợp lệ."""
    ra, sua = chan_lai_suat_bia("Dạ lãi tiết kiệm bên em 4.2% một năm ạ.",
                                TL_KHAC, can_cu_them="Lãi suất từ 7.9%/năm.")
    assert sua is not None
    assert ra == CAU_KIEM_TRA_LAI


# --- Tiền: số khách nêu ở lượt trước -------------------------------------

def test_tien_khach_neu_luot_truoc_thi_khong_thay():
    cau = "Dạ với 400 triệu thì mỗi tháng anh trả khoảng 8.2 triệu đồng ạ."
    ra, sua = chan_tien_sai(cau, "Kỳ hạn 12 đến 60 tháng.",
                            khach_noi="ví dụ anh vay một lần thì hết bao nhiêu",
                            can_cu_them="anh muốn vay tầm bốn trăm triệu")
    assert ra != CAU_KIEM_TRA_LAI, f"thay cả câu dù khách đã nêu 400 triệu: {sua}"
    assert "400 triệu" in ra


def test_tien_khong_ai_neu_thi_van_chan():
    cau = "Dạ hạn mức bên em lên đến 3 tỷ đồng ạ."
    ra, sua = chan_tien_sai(cau, "Kỳ hạn 12 đến 60 tháng.",
                            can_cu_them="anh muốn vay tầm bốn trăm triệu")
    assert sua is not None
    assert ra == CAU_KIEM_TRA_LAI


# --- Đừng "sửa" số đúng thành số của lượt khác ---------------------------

def test_khong_sua_79_thanh_85_khi_so_da_co_79():
    """Bẫy sinh ra TỪ chính bản sửa này: gỡ chặn ở `chan_lai_suat_bia` xong thì
    câu chạy tiếp xuống `chan_so_sai`, mà tài liệu lượt đó có ĐÚNG MỘT số thập
    phân (8.5) -> nó lặng lẽ đổi 7.9 thành 8.5. Sổ làm số thập phân thành hai,
    hết mơ hồ một nghĩa nên hàm để nguyên - đúng ý 'đoán bừa còn tệ hơn'."""
    ra, sua = chan_so_sai(CAU_LAI, TL_KHAC, can_cu_them="Lãi suất từ 7.9%/năm.")
    assert sua is None, f"sửa nhầm: {sua}"
    assert "7.9" in ra


def test_khong_co_so_thi_chan_so_sai_giu_hanh_vi_cu():
    ra, sua = chan_so_sai(CAU_LAI, TL_KHAC)
    assert sua is not None
    assert "8.5" in ra


# --- Sổ căn cứ ------------------------------------------------------------

def test_so_gop_tai_lieu_va_loi_khach():
    so = SoCanCu()
    so.ghi_tai_lieu("Lãi suất từ 7.9%/năm.")
    so.ghi_khach("anh muốn vay tầm bốn trăm triệu")
    assert "7.9" in so.can_cu
    assert "bốn trăm triệu" in so.can_cu


def test_so_chi_co_dung_hai_duong_ghi():
    """Ranh giới quan trọng nhất của lớp: chỉ TÀI LIỆU và LỜI KHÁCH vào được sổ.

    Kiểm bằng cách liệt kê bề mặt công khai chứ không dò chữ trong tên hàm -
    bản đầu của test này dò chuỗi "ai" và nó khớp ngay "ghi_tAI_lieu", tức là
    luôn đỏ dù code đúng. Thêm một đường ghi mới thì test này đỏ, và người thêm
    phải tự trả lời: nguồn đó có phải chữ mô hình sinh ra không.

    `TRAN_KHACH` thêm 09-09-2026 là HẰNG SỐ, không phải đường ghi: lời khách giữ
    riêng khỏi hàng đợi tài liệu để tài liệu khỏi đẩy nó ra - xem
    `tests/test_so_can_cu_giu_loi_khach.py`.
    """
    assert {t for t in dir(SoCanCu) if not t.startswith("_")} == {
        "TRAN_KY_TU", "TRAN_KHACH", "can_cu", "ghi_tai_lieu", "ghi_khach",
        "doi_neo"}


def test_doi_neo_san_pham_thi_xoa_so():
    so = SoCanCu()
    so.doi_neo("vay_mua_nha")
    so.ghi_tai_lieu("Hạn mức lên đến 10 tỷ đồng.")
    assert "10 tỷ" in so.can_cu
    so.doi_neo("vay_tin_chap")
    assert "10 tỷ" not in so.can_cu, "số của sản phẩm cũ phải rơi khỏi sổ"


def test_neo_khong_doi_thi_giu_nguyen():
    so = SoCanCu()
    so.doi_neo("vay_tin_chap")
    so.ghi_tai_lieu("Hạn mức 500 triệu.")
    so.doi_neo("vay_tin_chap")
    assert "500 triệu" in so.can_cu


def test_neo_rong_khong_xoa_so():
    """Lượt không nhận ra sản phẩm là chuyện thường; nó không được xoá sổ."""
    so = SoCanCu()
    so.doi_neo("vay_tin_chap")
    so.ghi_tai_lieu("Hạn mức 500 triệu.")
    so.doi_neo("")
    assert "500 triệu" in so.can_cu


def test_khong_ghi_trung_lap():
    so = SoCanCu()
    for _ in range(5):
        so.ghi_tai_lieu("Lãi suất từ 7.9%/năm.")
    assert so.can_cu.count("7.9") == 1


def test_co_tran_ky_tu():
    so = SoCanCu()
    for i in range(400):
        so.ghi_tai_lieu(f"Mảnh số {i} " + "x" * 200)
    assert len(so.can_cu) <= SoCanCu.TRAN_KY_TU


def test_tran_giu_doan_moi_nhat():
    """Cắt phải bỏ đoạn CŨ. Số vừa nói ở lượt trước quan trọng hơn số từ đầu cuộc."""
    so = SoCanCu()
    for i in range(400):
        so.ghi_tai_lieu(f"Mảnh số {i} " + "x" * 200)
    assert "Mảnh số 399" in so.can_cu


def test_so_rong_tra_chuoi_rong():
    assert SoCanCu().can_cu == ""
