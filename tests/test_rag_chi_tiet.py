"""`retrieve_chi_tiet` giữ lại thứ `retrieve` vứt đi: điểm khớp, nguồn, mảnh bị lọc.

Không có pytest-asyncio trong requirements-dev nên gọi bằng `asyncio.run`.
"""
import asyncio

import numpy as np

from backend.services.rag_service import RAGService

VAY_TIN_CHAP = "knowledge/products/vay_tin_chap.md"
VAY_MUA_NHA = "knowledge/products/vay_mua_nha.md"


class _KhoGia:
    """Chroma giả - trả đúng hình dạng lồng một lớp mà `query()` thật trả về."""

    def __init__(self, docs, metas, dists):
        self._docs, self._metas, self._dists = docs, metas, dists

    def count(self):
        return len(self._docs)

    def query(self, **_kw):
        ra = {"documents": [self._docs], "metadatas": [self._metas]}
        # Chroma cũ/bản giả có thể không trả distances - test riêng nhánh đó.
        if self._dists is not None:
            ra["distances"] = [self._dists]
        return ra


class _NhungGia:
    def encode(self, texts):
        return np.zeros((len(texts), 2), dtype=np.float32)


def _dich_vu(docs, metas, dists):
    rag = RAGService()
    rag._is_loaded = True          # khỏi nạp ChromaDB + bge-m3 thật
    rag._collection = _KhoGia(docs, metas, dists)
    rag._embedder = _NhungGia()
    return rag


def _chay(rag, san_pham=""):
    return asyncio.run(rag.retrieve_chi_tiet("lãi suất bao nhiêu", san_pham=san_pham))


def test_giu_diem_khop_va_ten_nguon():
    rag = _dich_vu(["mảnh A", "mảnh B"],
                   [{"source": VAY_TIN_CHAP}, {"source": VAY_MUA_NHA}],
                   [0.1, 0.4])
    _, chi_tiet = _chay(rag)

    # diem = 1 - distance (collection dùng hnsw:space=cosine)
    assert [c["diem"] for c in chi_tiet] == [0.9, 0.6]
    assert [c["nguon"] for c in chi_tiet] == ["vay_tin_chap.md", "vay_mua_nha.md"]


def test_manh_lac_san_pham_bi_danh_dau_nhung_van_hien_ra():
    """Đây là lý do tính năng này tồn tại.

    Lỗi thật đã gặp: đang tư vấn VAY TÍN CHẤP (7.9%) mà RAG kéo thêm
    vay_mua_nha.md (6.5%), LLM đọc ra 6.5%. Lưới lọc bỏ mảnh lạc khỏi ngữ cảnh,
    nhưng nếu chi tiết cũng giấu luôn thì người soi không thấy được nó ĐÃ từng
    được kéo về - mà đó chính là dấu hiệu truy vấn bị lệch neo.
    """
    rag = _dich_vu(["lãi suất 7.9%", "lãi suất 6.5%"],
                   [{"source": VAY_TIN_CHAP}, {"source": VAY_MUA_NHA}],
                   [0.1, 0.2])
    ngu_canh, chi_tiet = _chay(rag, san_pham="vay tín chấp")

    assert [c["bi_loc"] for c in chi_tiet] == [False, True]
    assert len(chi_tiet) == 2, "mảnh bị lọc phải CÒN trong chi tiết"
    assert "6.5%" not in ngu_canh, "mảnh lạc không được vào ngữ cảnh cho LLM"
    assert "7.9%" in ngu_canh


def test_ngu_canh_giong_het_ham_retrieve_cu():
    """`retrieve` giờ gọi lại `retrieve_chi_tiet` - đường thoại không được đổi."""
    docs = ["mảnh A", "mảnh B"]
    metas = [{"source": VAY_TIN_CHAP}, {"source": VAY_MUA_NHA}]

    ngu_canh, _ = _chay(_dich_vu(docs, metas, [0.1, 0.2]), san_pham="vay tín chấp")
    cu = asyncio.run(_dich_vu(docs, metas, [0.1, 0.2]).retrieve(
        "lãi suất bao nhiêu", san_pham="vay tín chấp"))

    assert ngu_canh == cu


def test_thieu_distance_thi_diem_la_none_chu_khong_phai_0():
    """0 nghĩa là "khớp hoàn hảo" - bịa ra số đó còn tệ hơn không có số."""
    rag = _dich_vu(["mảnh A"], [{"source": VAY_TIN_CHAP}], None)
    _, chi_tiet = _chay(rag)

    assert chi_tiet[0]["diem"] is None


def test_kho_rong_tra_ve_rong():
    ngu_canh, chi_tiet = _chay(_dich_vu([], [], []))

    assert ngu_canh == ""
    assert chi_tiet == []


def test_khong_neo_san_pham_ma_nhieu_san_pham_thi_LOC_HET():
    """ĐÃ ĐẢO NGƯỢC 06-09-2026. Trước đây: không neo sản phẩm thì không lọc gì.

    Lý do cũ vẫn đúng ở thời điểm đó: không có mốc thì không biết mảnh nào lạc,
    mà lọc bừa là bỏ mất câu trả lời đang đúng.

    Nay đảo vì lý do cũ bỏ sót đúng ca nguy hiểm nhất: phiên KHÔNG có sản phẩm
    (liên hệ chưa khai) mà truy vấn chạm nhiều sản phẩm thì mô hình chọn bừa -
    và nó chọn con số to nhất. Cuộc gọi thật `9874c82c`: khách hỏi hạn mức, AI
    đáp "10 TỶ đồng" (số của vay mua nhà), sai 20 lần hạn mức tín chấp thật.
    Cái giá nhận về: mất câu trả lời khi phiên chưa rõ sản phẩm - đổi lại mô
    hình phải hỏi khách đang quan tâm gì, đúng thứ nên làm khi chưa ai nói.
    """
    rag = _dich_vu(["mảnh A", "mảnh B"],
                   [{"source": VAY_TIN_CHAP}, {"source": VAY_MUA_NHA}],
                   [0.1, 0.2])
    ngu_canh, chi_tiet = _chay(rag)

    assert [c["bi_loc"] for c in chi_tiet] == [True, True]
    # Ngữ cảnh KHÔNG rỗng: còn dòng chỉ dẫn `CHUA_RO_SAN_PHAM`. Trả rỗng hẳn thì
    # mô hình không biết vì sao trống và bịa số từ trí nhớ - đo được câu ra
    # "Hạn mức tín dụng thường5003000", vỡ vụn.
    assert "mảnh A" not in ngu_canh and "mảnh B" not in ngu_canh
    assert "CHƯA RÕ SẢN PHẨM" in ngu_canh


def test_khong_neo_san_pham_nhung_CHI_MOT_san_pham_thi_giu():
    """Một sản phẩm thì không có gì để lẫn - đây là chỗ giữ lại lý do cũ."""
    rag = _dich_vu(["mảnh A", "mảnh B"],
                   [{"source": VAY_TIN_CHAP}, {"source": VAY_TIN_CHAP}],
                   [0.1, 0.2])
    ngu_canh, chi_tiet = _chay(rag)

    assert [c["bi_loc"] for c in chi_tiet] == [False, False]
    assert "mảnh A" in ngu_canh and "mảnh B" in ngu_canh
