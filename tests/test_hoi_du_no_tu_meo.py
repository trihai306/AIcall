"""Khách hỏi DƯ NỢ bằng chữ méo thì phải nhận ra, đừng để rơi xuống LLM.

VÌ SAO CÓ FILE NÀY. Cuộc gọi thật `99ee5360` (05-09-2026): khách hỏi *"doanh thu
khoản vay với mình là bao nhiêu"*, AI đáp *"hợp đồng vay tín chấp của anh có
doanh thu là 142.500.000 đồng"*.

Con số ĐÚNG - hồ sơ của số 0396130621 ghi `du_no = 142.500.000 đồng`, và lưới
`chan_tien_sai` cho qua đúng luật vì số có căn cứ trong ngữ cảnh. Cái sai là
NHÃN: khoản vay không có "doanh thu". Mô hình lặp lại chữ méo của bản phiên âm,
dù prompt đã có quy tắc "đừng nhắc lại chữ sai" - lại một lần nữa xác nhận bài
học cũ: prompt không gỡ được thì chặn bằng code.

Gốc: mẫu `du_no` trong `tra_loi_ho_so.BANG` chỉ khớp "du no", "no con bao nhieu",
"con no bao nhieu", "con thieu bao nhieu". Câu trên trượt hết, nên rơi xuống
RAG+LLM thay vì đọc thẳng từ hồ sơ.

RÀNG BUỘC QUAN TRỌNG: "doanh thu" là từ HỢP LỆ khi khách khai thu nhập của chính
mình - phiên `c5538fc0` có thật câu *"anh có doanh thu một tháng là hai mươi
triệu"*. Bắt trơ chữ "doanh thu" là chặn nhầm đúng câu đó, nên mẫu phải đòi có
thêm dấu hiệu của KHOẢN VAY (khoản vay / hợp đồng / bên mình / với mình).
"""
import pytest

from backend.pipeline.tra_loi_ho_so import nhan_dang, tra_loi

HO_SO = {
    "du_no": "142.500.000 đồng",
    "ky_han_con": "21 tháng",
    "tra_hang_thang": "7.850.000 đồng",
}


# --- Câu méo phải nhận ra là hỏi dư nợ ------------------------------------

@pytest.mark.parametrize("cau", [
    "doanh thu khoản vay với mình là bao nhiêu",     # đúng câu trong cuộc gọi thật
    "doanh thu khoản vay bên mình là bao nhiêu",     # phiên âm kênh khách của chính lượt đó
    "cho anh xem doanh thu khoản vay của anh",
    "doanh thu hợp đồng của anh còn bao nhiêu",
])
def test_hoi_du_no_bang_chu_meo(cau):
    assert nhan_dang(cau) == ("du_no", "du_no")


def test_tra_loi_goi_dung_ten_va_dung_so():
    ra = tra_loi("doanh thu khoản vay với mình là bao nhiêu", HO_SO, "anh")
    assert ra is not None, "câu này phải đi đường hồ sơ, không rơi xuống LLM"
    ten, cau = ra
    assert ten == "du_no"
    assert "142.500.000 đồng" in cau
    assert "doanh thu" not in cau.lower(), "không được lặp lại chữ méo của khách"
    assert "dư nợ" in cau.lower()


# --- KHÔNG được bắt nhầm khi khách khai doanh thu của chính mình ----------

@pytest.mark.parametrize("cau", [
    "anh có doanh thu một tháng là hai mươi triệu",   # có thật trong phiên c5538fc0
    "doanh thu của anh khoảng năm mươi triệu",
    "cửa hàng anh doanh thu tháng này kém",
    "doanh thu năm ngoái của công ty anh tốt",
])
def test_khach_khai_doanh_thu_thi_khong_bat(cau):
    assert nhan_dang(cau) is None


# --- Các cách hỏi cũ vẫn phải chạy ----------------------------------------

@pytest.mark.parametrize("cau", [
    "dư nợ của anh còn bao nhiêu",
    "anh còn nợ bao nhiêu",
    "nợ còn bao nhiêu",
])
def test_cach_hoi_cu_khong_bi_pha(cau):
    assert nhan_dang(cau) == ("du_no", "du_no")


def test_khong_co_du_lieu_thi_ve_duong_llm():
    """Hồ sơ trống thì trả None để lượt đi tiếp đường cũ, đừng đọc ô rỗng."""
    assert tra_loi("doanh thu khoản vay với mình là bao nhiêu", {}, "anh") is None
