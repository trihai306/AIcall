"""Hai lưới tuân thủ: chữ cấm, và gán thu nhập cho khách khi khách chưa nói.

Cả hai đều tìm ra từ bản diễn lại cuộc 08c0d3e0 (07-09-2026).

## Chữ cấm

    AI: "Bên em vẫn có cách LÁCH để anh/chị vay được ạ."

Chữ "lách" KHÔNG có trong tri thức, kịch bản, bảng hỏi-đáp hay kho tình huống -
mô hình tự sinh. Nó ứng biến vì tri thức sản phẩm ghi nợ xấu là KHÔNG đủ điều
kiện, mà câu trả lời đúng nằm ở `knowledge/faq/faq_banking.md` lại không được
RAG lôi về. Với tư vấn ngân hàng thì đây là rủi ro tuân thủ, phải chặn CỨNG chứ
không dặn bằng prompt - dự án đã đo ba lần prompt bị luật khác đè.

## Gán thu nhập cho khách

    AI: "Anh/chị có lương từ 3.4 triệu/tháng, bên em có thể hỗ trợ vay 200 triệu..."

Khách chưa hề nói lương. Lưới `chan_so_sai` cho qua vì 3.4 CÓ trong tài liệu -
lỗi không nằm ở con số mà ở CHỦ THỂ. Mảnh RAG số 6 (487 ký tự, sát trần 500)
chứa liền nhau:

    ## Điều kiện vay
    - Có lương từ 5 triệu đồng/tháng trở lên          <- câu chữ
    ...
    - Vay 100 triệu, 36 tháng: trả hàng tháng khoảng 3.4 triệu   <- con số

Mô hình mượn cụm "Có lương từ ... triệu đồng/tháng" rồi thay số bằng 3.4 (vốn là
khoản TRẢ GÓP của gói 100 triệu).
"""
from backend.pipeline.chan_tuan_thu import chan_gan_thu_nhap, chan_tu_cam


# --- Chữ cấm --------------------------------------------------------------

def test_chan_chu_lach():
    ra, ly_do = chan_tu_cam("Bên em vẫn có cách lách để anh/chị vay được ạ.")
    assert ly_do, "chữ 'lách' phải bị chặn"
    assert "lách" not in ra.lower()


def test_chan_chay_ho_so():
    _, ly_do = chan_tu_cam("Anh cứ để bên em chạy hồ sơ cho ạ.")
    assert ly_do


def test_cau_binh_thuong_khong_bi_dung_toi():
    cau = "Dạ lãi suất vay tín chấp từ 7.9%/năm ạ."
    ra, ly_do = chan_tu_cam(cau)
    assert ly_do is None and ra == cau


def test_khong_bat_nham_tu_chua_chuoi_con():
    """`lách` là TỪ, không phải chuỗi con bất kỳ - tránh chặn oan."""
    for cau in ("Dạ hồ sơ sạch thì duyệt nhanh ạ.",
                "Dạ em tách khoản này ra ạ."):
        _, ly_do = chan_tu_cam(cau)
        assert ly_do is None, f"chặn oan: {cau!r}"


# --- Gán thu nhập cho khách ----------------------------------------------

CAU_BIA = "Anh/chị có lương từ 3.4 triệu/tháng, bên em hỗ trợ vay 200 triệu ạ."


def test_chan_khi_khach_chua_he_noi_luong():
    ra, ly_do = chan_gan_thu_nhap(CAU_BIA, khach_da_noi="lãi suất bao nhiêu")
    assert ly_do, "khách chưa nói lương mà AI khẳng định -> phải chặn"
    assert "3.4" not in ra


def test_khong_chan_khi_chinh_khach_da_noi_con_so_do():
    """Khách tự nêu thì AI nhắc lại là ĐÚNG - chặn mới là sai.

    Cùng ràng buộc `chan_tien_sai` đã đặt ra cho số tiền.
    """
    ra, ly_do = chan_gan_thu_nhap(
        CAU_BIA, khach_da_noi="lương anh 3.4 triệu một tháng")
    assert ly_do is None and ra == CAU_BIA


def test_khong_chan_cau_noi_ve_DIEU_KIEN_chu_khong_gan_cho_khach():
    """'Điều kiện là có lương từ 5 triệu' là nói về SẢN PHẨM, không gán cho ai."""
    cau = "Dạ điều kiện là có lương từ 5 triệu đồng một tháng trở lên ạ."
    ra, ly_do = chan_gan_thu_nhap(cau, khach_da_noi="")
    assert ly_do is None and ra == cau


def test_khong_chan_cau_HOI_thu_nhap():
    """Hỏi thì được, khẳng định thay khách mới là lỗi."""
    cau = "Dạ anh/chị cho em xin mức thu nhập hàng tháng ạ?"
    _, ly_do = chan_gan_thu_nhap(cau, khach_da_noi="")
    assert ly_do is None


def test_cau_thay_the_la_cau_HOI_de_cuoc_goi_di_tiep():
    """Thay bằng câu hỏi chứ không phải 'em kiểm tra lại': ở đây thứ còn thiếu
    đúng là con số của khách, hỏi thẳng là cách gỡ nhanh nhất."""
    ra, _ = chan_gan_thu_nhap(CAU_BIA, khach_da_noi="")
    assert "?" in ra
