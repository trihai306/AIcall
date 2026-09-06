"""Phiên CHƯA BIẾT sản phẩm thì không được trộn tài liệu của nhiều sản phẩm.

VÌ SAO CÓ FILE NÀY. Cuộc gọi thật `9874c82c` (06-09-2026), số 0386503822:

    khách: hạn mức bao nhiêu
    AI   : Hạn mức vay tối đa là 10 TỶ đồng ạ. Anh/chị có bất động sản nào để
           làm tài sản đảm bảo không?

Sai 20 lần so với hạn mức thật của vay tín chấp (500 triệu), và còn hỏi tài sản
thế chấp — đã trượt hẳn sang sản phẩm khác. "10 tỷ" nằm trong `vay_mua_nha.md`.

Chuỗi nhân quả, đã xác nhận từng mắt: liên hệ `ct_7a641310` chưa khai sản phẩm
-> `call_sessions.product = ''` -> `_mat_na_loc` không có mốc nên giữ NGUYÊN mọi
mảnh -> RAG trộn cả ba sản phẩm -> mô hình lấy số của sản phẩm khác. `chan_tien_sai`
cho qua ĐÚNG LUẬT vì 10 tỷ CÓ trong ngữ cảnh: lưới an toàn không hỏng, nó bị
bịt mắt.

Cách chữa (người dùng chốt 06-09-2026): phiên chưa rõ sản phẩm mà truy vấn lôi
về mảnh của NHIỀU sản phẩm thì bỏ hết mảnh `products`, giữ FAQ/chính sách. Khi
đó ngữ cảnh không còn con số sản phẩm nào, `chan_tien_sai` tự chặn mọi số bịa,
và mô hình chỉ còn đường hỏi lại khách đang quan tâm sản phẩm nào — đúng nghiệp
vụ, vì thật sự chưa ai nói khách muốn gì.

Dùng lại đúng khuôn của ca (b) trong `_mat_na_loc` (sản phẩm không có tài liệu).
"""
import pytest

from backend.services.rag_service import RAGService


def _meta(ten: str, thu_muc: str = "products"):
    return {"source": f"knowledge/{thu_muc}/{ten}"}


DOCS3 = ["Hạn mức: lên đến 500 triệu",
         "Hạn mức: lên đến 10 tỷ, cần tài sản đảm bảo",
         "Hồ sơ chung: căn cước và sao kê lương"]
METAS3 = [_meta("vay_tin_chap.md"), _meta("vay_mua_nha.md"),
          _meta("ho_so.md", "faq")]


def _giu(docs, metas, san_pham=""):
    return RAGService._mat_na_loc(docs, metas, san_pham,
                                  {"vay_tin_chap", "vay_mua_nha", "the_tin_dung"})


# --- Chưa rõ sản phẩm + nhiều sản phẩm -> bỏ hết mảnh products ------------

def test_chua_ro_san_pham_thi_bo_manh_cua_moi_san_pham():
    giu = _giu(DOCS3, METAS3, san_pham="")
    assert giu[0] is False, "phải bỏ mảnh vay tín chấp"
    assert giu[1] is False, "phải bỏ mảnh vay mua nhà (chứa 10 tỷ)"
    assert giu[2] is True, "FAQ/chính sách vẫn giữ để mô hình còn ngữ cảnh chung"


def test_khong_con_con_so_san_pham_nao_trong_ngu_canh():
    """Đây mới là thứ chặn được '10 tỷ': ngữ cảnh sạch số thì `chan_tien_sai`
    thấy `hop_le` rỗng và thay cả câu."""
    giu = _giu(DOCS3, METAS3, san_pham="")
    con = [d for d, k in zip(DOCS3, giu) if k]
    assert not any("tỷ" in d or "triệu" in d for d in con)


# --- Nhưng đừng cắt khi chỉ có MỘT sản phẩm ------------------------------

def test_chi_mot_san_pham_thi_giu_nguyen():
    """Chưa rõ sản phẩm nhưng mọi mảnh cùng một sản phẩm thì không có gì để lẫn."""
    docs = [DOCS3[0], "Lãi suất từ 7.9%/năm", DOCS3[2]]
    metas = [_meta("vay_tin_chap.md"), _meta("vay_tin_chap.md"), METAS3[2]]
    assert _giu(docs, metas, san_pham="") == [True, True, True]


def test_khong_co_manh_products_thi_giu_nguyen():
    docs = ["Giờ làm việc 8h-17h", "Hồ sơ chung"]
    metas = [_meta("gio_lam.md", "faq"), _meta("ho_so.md", "faq")]
    assert _giu(docs, metas, san_pham="") == [True, True]


# --- Có sản phẩm thì hành vi cũ giữ nguyên -------------------------------

def test_co_san_pham_van_loc_nhu_cu():
    giu = _giu(DOCS3, METAS3, san_pham="vay tín chấp")
    assert giu[0] is True, "mảnh đúng sản phẩm phải giữ"
    assert giu[1] is False, "mảnh sản phẩm khác phải bỏ"
    assert giu[2] is True


def test_thieu_metas_thi_khong_dung_gi():
    assert _giu(DOCS3, None, san_pham="") == [True, True, True]
    assert _giu(DOCS3, METAS3[:2], san_pham="") == [True, True, True]


# --- Phiên chưa rõ nhưng CÂU KHÁCH đã nói rõ -> neo theo câu --------------

def test_cau_khach_neu_ro_san_pham_thi_neo_theo_cau():
    """Thiếu mắt này thì bản sửa đi quá tay: khách nói rõ "tín chấp" mà vẫn bị
    bỏ sạch mảnh, AI đáp "em xin phép kiểm tra lại" ba lượt liền y hệt nhau."""
    assert RAGService._san_pham_trong_cau(
        "máy tín chấp hạn mức bao nhiêu",
        {"vay_tin_chap", "vay_mua_nha", "the_tin_dung"}) == "vay_tin_chap"


def test_cau_khong_neu_san_pham_thi_tra_rong():
    """Phần lớn lượt trong cuộc gọi thật rơi vào đây - lúc đó mới bỏ mảnh."""
    assert RAGService._san_pham_trong_cau(
        "hạn mức bao nhiêu", {"vay_tin_chap", "vay_mua_nha"}) == ""
