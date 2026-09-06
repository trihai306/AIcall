"""Neo sản phẩm nào thì LUÔN mang theo mảnh mở đầu (định nghĩa) của sản phẩm đó.

VÌ SAO CÓ FILE NÀY. Cuộc gọi thật `009d9fb3` (06-09-2026), lượt đầu:

    khách: ờ cho anh hỏi khoản vay bên mình vay tín chấp
    AI   : Được ạ, vay tín chấp là hình thức cho vay CÓ BẢO ĐẢM BẰNG TÀI SẢN
           của khách hàng hoặc tín chấp.

Ngược hẳn nghiệp vụ, và ngược hẳn tài liệu của chính dự án -
`knowledge/products/vay_tin_chap.md` mở đầu bằng "Định nghĩa: Là vay KHÔNG CẦN
thế chấp tài sản, chỉ dựa trên uy tín...".

KHÔNG PHẢI mô hình cãi tài liệu. Hỏi thẳng RAG bằng đúng câu đó (top_k=2, neo
'vay tín chấp') thì hai mảnh lấy về là:

    0.377  bảng ví dụ trả góp ("Vay 200 triệu, 36 tháng: 6.8 triệu")
    0.284  câu xử lý từ chối ("ngân hàng nào dám cho vay quá nhiều ạ")

Mảnh định nghĩa xếp thứ ba trở xuống, nên nó KHÔNG vào ngữ cảnh. Mô hình không
có định nghĩa trong tay và nói theo trí nhớ - trí nhớ đó sai.

Hai giả thuyết đã BÁC BỎ trước khi tới đây:
  - "mô hình sai": chạy 10 lượt qua đường chữ với đúng câu đó, 10/10 trả lời
    đúng. Khác biệt duy nhất là ngữ cảnh RAG.
  - "tài liệu sai": đọc file, định nghĩa hoàn toàn đúng.

Vì sao chữa bằng cách mang theo mảnh 0 chứ không tăng `top_k`: tăng top_k kéo
thêm mảnh của sản phẩm khác vào diện phải lọc, và chính nó là nguồn lỗi
"10 tỷ" mà `test_chua_ro_san_pham` sinh ra để chặn. Mảnh 0 thì luôn thuộc đúng
sản phẩm đang neo, không đánh đổi gì.
"""
import asyncio

import numpy as np

from backend.services.rag_service import RAGService

NGUON = "C:\\duan\\chat-ai\\knowledge\\products\\vay_tin_chap.md"
DINH_NGHIA = ("# Vay Tín Chấp Cá Nhân\n- Định nghĩa: Là vay không cần thế chấp "
              "tài sản, chỉ dựa trên uy tín")


class _KhoGia:
    """Chroma giả có cả `query` lẫn `get` theo id - bản ở `test_rag_chi_tiet`
    chỉ có `query`, nên nó không kiểm được đường mang theo mảnh 0."""

    def __init__(self, docs, metas, kho_id=None, no_get=False):
        self._docs, self._metas = docs, metas
        self._kho_id = kho_id or {}
        self._no_get = no_get
        self.so_lan_get = 0

    def count(self):
        return len(self._docs)

    def query(self, **_kw):
        return {"documents": [self._docs], "metadatas": [self._metas],
                "distances": [[0.1] * len(self._docs)]}

    def get(self, **kw):
        if self._no_get:
            raise RuntimeError("kho không cho đọc theo id")
        self.so_lan_get += 1
        ids = kw.get("ids")
        if ids is None:                      # đường `_san_pham_co_tai_lieu`
            return {"ids": list(self._kho_id),
                    "metadatas": [{"source": NGUON} for _ in self._kho_id],
                    "documents": list(self._kho_id.values())}
        co = [i for i in ids if i in self._kho_id]
        return {"ids": co, "documents": [self._kho_id[i] for i in co],
                "metadatas": [{"source": NGUON} for _ in co]}


class _NhungGia:
    def encode(self, texts):
        return np.zeros((len(texts), 2), dtype=np.float32)


def _dich_vu(docs, metas, kho_id=None, no_get=False):
    rag = RAGService()
    rag._is_loaded = True
    rag._collection = _KhoGia(docs, metas, kho_id, no_get)
    rag._embedder = _NhungGia()
    return rag


def _chay(rag, san_pham="vay tín chấp", cau="cho anh hỏi khoản vay bên mình vay tín chấp"):
    return asyncio.run(rag.retrieve_chi_tiet(cau, top_k=2, san_pham=san_pham))


KHO = {"vay_tin_chap_chunk_0": DINH_NGHIA,
       "vay_tin_chap_chunk_2": "Vay 200 triệu, 36 tháng: 6.8 triệu"}
LAY_VE = ["Vay 200 triệu, 36 tháng: 6.8 triệu", "ngân hàng nào dám cho vay quá nhiều ạ"]
META2 = [{"source": NGUON}, {"source": NGUON}]


# --- Ca chính: đúng cảnh của cuộc gọi 009d9fb3 --------------------------

def test_mang_theo_dinh_nghia_khi_lay_ve_khong_co():
    ngu_canh, _ = _chay(_dich_vu(LAY_VE, META2, KHO))
    assert "không cần thế chấp" in ngu_canh, (
        "định nghĩa phải vào ngữ cảnh - thiếu nó mô hình nói theo trí nhớ và "
        "nói ngược nghiệp vụ")


def test_van_giu_manh_lay_ve():
    """Mang theo là THÊM, không phải thay. Bảng trả góp vẫn phải còn."""
    ngu_canh, _ = _chay(_dich_vu(LAY_VE, META2, KHO))
    assert "6.8 triệu" in ngu_canh


def test_khong_lap_khi_da_co_manh_0():
    ngu_canh, _ = _chay(_dich_vu([DINH_NGHIA, LAY_VE[0]], META2, KHO))
    assert ngu_canh.count("Định nghĩa") == 1


def test_hien_ra_trong_chi_tiet_de_soi_duoc():
    """Trang 'Mảnh' là chỗ người soi hiểu vì sao câu trả lời ra như vậy. Mảnh
    tự mang vào mà giấu đi thì họ soi nhầm chỗ."""
    _, chi_tiet = _chay(_dich_vu(LAY_VE, META2, KHO))
    them = [c for c in chi_tiet if c.get("mang_theo")]
    assert len(them) == 1
    assert them[0]["bi_loc"] is False
    assert them[0]["nguon"] == "vay_tin_chap.md"


# --- Không được đụng vào các đường khác ---------------------------------

def test_khong_neo_san_pham_thi_khong_mang_gi():
    """Chưa rõ sản phẩm mà tự kéo định nghĩa vào là chọn hộ khách sản phẩm."""
    kho = _dich_vu(LAY_VE, [{"source": NGUON},
                            {"source": NGUON.replace("tin_chap", "mua_nha")}], KHO)
    ngu_canh, chi_tiet = _chay(kho, san_pham="", cau="hạn mức bao nhiêu")
    assert "Định nghĩa" not in ngu_canh
    assert not any(c.get("mang_theo") for c in chi_tiet)


def test_kho_khong_doc_duoc_thi_khong_vo():
    """Hướng an toàn: mang theo là NỚI thêm, hỏng thì quay về hành vi cũ."""
    ngu_canh, chi_tiet = _chay(_dich_vu(LAY_VE, META2, KHO, no_get=True))
    assert "6.8 triệu" in ngu_canh
    assert not any(c.get("mang_theo") for c in chi_tiet)


def test_san_pham_khong_co_manh_0_thi_thoi():
    ngu_canh, _ = _chay(_dich_vu(LAY_VE, META2, {"vay_tin_chap_chunk_2": "x"}))
    assert "Định nghĩa" not in ngu_canh


def test_nho_lai_khoi_doc_kho_moi_luot():
    """Mỗi lượt gọi `retrieve` ba lần, mà hàm này nằm trên đường găng độ trễ."""
    rag = _dich_vu(LAY_VE, META2, KHO)
    for _ in range(4):
        _chay(rag)
    assert rag._collection.so_lan_get <= 2, (
        f"đọc kho {rag._collection.so_lan_get} lần - phải nhớ lại")
