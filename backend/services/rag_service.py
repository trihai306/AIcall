import hashlib
import logging
import re
import time
import unicodedata
from pathlib import Path, PurePath
import chromadb
from backend.config import settings
from backend.core.logging_config import Timer

logger = logging.getLogger(__name__)
CHUNKER_VERSION = "markdown-sections-v2"


def cat_manh(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Giữ từng mục Markdown nguyên vẹn khi có tiêu đề cấp hai.

    Mỗi dữ kiện dưới ``##`` thành một mảnh có tên tài liệu và tên mục. Mục quá
    dài vẫn cắt nhỏ; tài liệu thường giữ đường cắt cũ. Khung xem trước và lúc
    nạp Chroma gọi cùng hàm này nên số mảnh không lệch nhau.
    """
    text = text.strip()
    headings = list(re.finditer(r"(?m)^##\s+.+$", text))
    if headings:
        title = next((line.strip() for line in text.splitlines()
                      if re.match(r"^#\s+", line)), "")
        result = []
        preface = text[:headings[0].start()].strip()
        # Giữ lời dẫn/định nghĩa ở đầu tài liệu. Riêng khối nguồn PDF + hash
        # chỉ là provenance, không có dữ kiện để mô hình trả lời.
        useful_lines = [line for line in preface.splitlines()
                        if line.strip() and line.strip() != title
                        and not line.startswith(("Nguồn PDF", "SHA-256 PDF", "Phạm vi:"))]
        if useful_lines:
            result.extend(_cat_theo_ky_tu(preface, chunk_size, overlap))
        for i, heading in enumerate(headings):
            end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
            section = text[heading.start():end].strip()
            block = (title + "\n" + section).strip() if title else section
            if len(block) <= chunk_size:
                result.append(block)
            else:
                result.extend(_cat_theo_ky_tu(block, chunk_size, overlap))
        return result
    return _cat_theo_ky_tu(text, chunk_size, overlap)


def _cat_theo_ky_tu(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Đường dự phòng cho mục dài hoặc văn bản không có cấu trúc Markdown."""
    if len(text) <= chunk_size:
        return [text] if text else []

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        if end >= len(text):
            break
        start = end - overlap

    return chunks


# Chèn vào đầu ngữ cảnh khi phiên chưa rõ sản phẩm và mảnh sản phẩm đã bị bỏ.
# Viết như một CHỈ DẪN chứ không như dữ liệu: mô hình đọc ngữ cảnh để lấy số,
# nên phải nói thẳng rằng ở đây không có số nào để lấy.
CHUA_RO_SAN_PHAM = (
    "[CHƯA RÕ SẢN PHẨM] Khách chưa cho biết đang quan tâm sản phẩm nào, nên "
    "không có số liệu nào áp dụng được. TUYỆT ĐỐI không nêu lãi suất, hạn mức "
    "hay số tiền. Hãy hỏi khách đang quan tâm vay tín chấp, vay mua nhà hay "
    "thẻ tín dụng."
)


def _la_manh_products(meta: dict | None) -> bool:
    src = ((meta or {}).get("source") or "").replace("\\", "/")
    return PurePath(src).parent.name == "products"


class RAGService:
    """ChromaDB + embedding model for retrieval-augmented generation."""

    def __init__(self):
        self._client = None
        self._collection = None
        self._embedder = None
        self._is_loaded = False
        # Danh mục sản phẩm có tài liệu riêng, dựng lười. None = chưa biết.
        self._ma_sp_co_tai_lieu: set[str] | None = None
        # Mảnh ĐẦU tài liệu của từng sản phẩm (tiêu đề + định nghĩa). Nhớ lại
        # vì `retrieve` chạy ba lần mỗi lượt, ngay trên đường găng độ trễ.
        self._manh_dau_nho: dict[str, str] = {}

    def load(self):
        if self._is_loaded:
            return

        logger.info("Loading RAG service...")

        # ChromaDB
        db_path = settings.chroma_db_path
        Path(db_path).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=db_path)
        self._collection = self._client.get_or_create_collection(
            name="banking_knowledge",
            metadata={"hnsw:space": "cosine"},
        )

        # Embedding model (default CPU to save GPU VRAM for STT/LLM/TTS)
        from sentence_transformers import SentenceTransformer
        device = settings.embedding_device
        logger.info(f"Loading embedding model: {settings.embedding_model} ({device})...")
        self._embedder = SentenceTransformer(settings.embedding_model, device=device)

        # Warm up: first encode() call pays tokenizer/graph init cost (~hundreds of ms)
        self._embedder.encode(["khởi động"])

        self._is_loaded = True
        count = self._collection.count()
        logger.info(f"RAG ready: {count} documents in knowledge base")

    def embed(self, texts: list[str]) -> "np.ndarray":
        """Nhúng danh sách chuỗi. Hình (n, d), CHƯA chuẩn hoá.

        Công khai để phần chọn tình huống dùng lại đúng model này thay vì nạp
        thêm một model nữa - VRAM 12GB đã phải chia cho STT, LLM và TTS.
        """
        import numpy as np
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        return np.asarray(self._embedder.encode(texts), dtype=np.float32)

    async def retrieve(self, query: str, top_k: int = 3, san_pham: str = "") -> str:
        """Retrieve relevant documents for the query.

        Chỉ trả phần ngữ cảnh ghép sẵn - đúng thứ đường thoại cần. Muốn biết
        đoạn nào được lấy, khớp bao nhiêu, đoạn nào bị lọc thì gọi
        `retrieve_chi_tiet`.
        """
        ngu_canh, _ = await self.retrieve_chi_tiet(query, top_k, san_pham)
        return ngu_canh

    async def retrieve_chi_tiet(
        self, query: str, top_k: int = 3, san_pham: str = "",
    ) -> tuple[str, list[dict]]:
        """Như `retrieve` nhưng GIỮ LẠI điểm khớp, tên nguồn và mảnh bị lọc.

        Runs the blocking encode/query in a thread so it can overlap
        with other pipeline work (e.g. sending the filler audio).

        `san_pham` là sản phẩm phiên đang tư vấn ("vay tín chấp", ...). Có nó thì
        các mảnh thuộc sản phẩm KHÁC bị loại - xem `_mat_na_loc`.

        Trả `(ngữ_cảnh, chi_tiết)`. `chi_tiết` xếp theo đúng thứ hạng ChromaDB:

            {"doan": str, "diem": float, "nguon": str, "bi_loc": bool}

        `diem` là độ tương đồng cosine (càng cao càng khớp), đổi từ `distance`
        Chroma trả về - collection tạo với `hnsw:space=cosine` nên
        `diem = 1 - distance`.

        `bi_loc=True` là mảnh `_mat_na_loc` đã bỏ. Giữ lại trong chi tiết
        vì chính nó là dấu vết của lỗi "RAG lạc sản phẩm": thấy mảnh
        vay_mua_nha.md bị loại khi đang tư vấn vay tín chấp thì biết ngay lưới
        lọc vừa ăn - và thấy nó KHÔNG bị loại thì biết lưới đang hở.

        Đường thoại đi qua `retrieve` rồi bỏ phần chi tiết. Chi phí dựng danh
        sách nhiều nhất `top_k` phần tử, không đáng kể cạnh một lần truy vấn
        vector, nên không tách đôi đường truy vấn để tránh lệch hành vi.
        """
        if not self._is_loaded:
            self.load()

        if self._collection.count() == 0:
            return "", []

        import asyncio

        # Tài liệu Shinhan có nguồn đã đối chiếu; các file products đi kèm bản
        # demo là số giả. Khi khách hỏi rõ Shinhan, chỉ tra đúng ngân hàng này.
        # Lọc ở Chroma trước khi xếp hạng để top_k không bị tài liệu mẫu chiếm.
        shinhan_query = "shinhan" in (query or "").casefold()
        digital_card_query = shinhan_query and any(
            phrase in (query or "").casefold()
            for phrase in ("thẻ điện tử", "thẻ ảo")
        )

        def _query():
            embedding = self._embedder.encode([query])[0].tolist()
            kwargs = dict(
                query_embeddings=[embedding],
                n_results=min(top_k, self._collection.count()),
                include=["documents", "distances", "metadatas"],
            )
            if shinhan_query:
                kwargs["where"] = {"bank": "shinhan"}
            if digital_card_query:
                # Cùng một ngân hàng vẫn có thẻ vật lý và thẻ điện tử. Câu
                # hỏi về thẻ điện tử từng lấy toàn mảnh mất thẻ vật lý, khiến
                # Qwen nói không có tài liệu dù mục thẻ điện tử đã lập chỉ mục.
                kwargs["where_document"] = {"$contains": "thẻ điện tử"}
            result = self._collection.query(**kwargs)
            if digital_card_query and not (result.get("documents") or [[]])[0]:
                kwargs.pop("where_document")
                result = self._collection.query(**kwargs)
            return result

        with Timer("RAG", logger):
            results = await asyncio.to_thread(_query)

        if not results["documents"] or not results["documents"][0]:
            return "", []

        docs = results["documents"][0]
        metas = (results.get("metadatas") or [[]])[0] or []
        dists = (results.get("distances") or [[]])[0] or []

        co_tl = self._san_pham_co_tai_lieu()

        # PHIÊN chưa biết sản phẩm, nhưng CÂU KHÁCH có thể đã nói rõ. Neo theo
        # câu trước khi tính tới chuyện bỏ hết mảnh sản phẩm.
        #
        # Thiếu mắt này thì bản sửa ca (c) đi quá tay: đo được ngay sau khi thêm,
        # lượt "máy tín chấp hạn mức bao nhiêu" - khách đã nói rõ TÍN CHẤP - vẫn
        # bị bỏ sạch mảnh và AI đáp "em xin phép kiểm tra lại" ba lượt liền y hệt
        # nhau. Neo theo câu thì lượt đó trả lời đúng 500 triệu.
        if not san_pham:
            tu_cau = self._san_pham_trong_cau(query, co_tl)
            if tu_cau and tu_cau != "khong_co_tai_lieu":
                san_pham = tu_cau
                logger.info("RAG: phiên chưa rõ sản phẩm - neo theo CÂU KHÁCH: %r",
                            tu_cau)
        # Câu hỏi nêu rõ một sản phẩm mà kho KHÔNG có tài liệu -> bỏ hết mảnh
        # `products`, giữ FAQ/chính sách. Phải xét TRƯỚC `_mat_na_loc` vì hàm đó
        # chỉ soi sản phẩm của phiên, mà phiên thường là sản phẩm CÓ tài liệu.
        if self._san_pham_trong_cau(query, co_tl) == "khong_co_tai_lieu":
            def _la_products(meta):
                src = ((meta or {}).get("source") or "").replace("\\", "/")
                return PurePath(src).parent.name == "products"
            giu = [not _la_products(metas[i] if i < len(metas) else None)
                   for i in range(len(docs))]
            if not all(giu):
                logger.info(
                    "RAG: câu hỏi nêu sản phẩm không có tài liệu - bỏ %d mảnh "
                    "products để mô hình khỏi đọc số của sản phẩm khác",
                    giu.count(False))
        else:
            giu = self._mat_na_loc(docs, metas, san_pham, co_tl)

        chi_tiet = []
        for i, doc in enumerate(docs):
            meta = metas[i] if i < len(metas) else None
            nguon = PurePath(((meta or {}).get("source") or "").replace("\\", "/")).name
            chi_tiet.append({
                "doan": doc,
                # Không có distance (Chroma đổi API, hoặc bản giả lập trong test)
                # thì để None chứ đừng bịa số 0 - 0 nghĩa là "khớp hoàn hảo".
                "diem": round(1.0 - dists[i], 3) if i < len(dists) else None,
                "nguon": nguon,
                "bi_loc": not giu[i],
            })

        ngu_canh = "\n---\n".join(d for d, k in zip(docs, giu) if k)

        # MANG THEO mảnh mở đầu của sản phẩm đang neo, kể cả khi nó thua điểm.
        #
        # Cuộc gọi thật `009d9fb3`: khách hỏi "khoản vay bên mình vay tín chấp",
        # hai mảnh thắng điểm là bảng trả góp (0.377) và câu xử lý từ chối
        # (0.284); mảnh định nghĩa xếp sau nên không vào ngữ cảnh. Mô hình đáp
        # "vay tín chấp là hình thức cho vay CÓ BẢO ĐẢM BẰNG TÀI SẢN" - ngược
        # hẳn tài liệu của chính nó.
        #
        # Đặt LÊN ĐẦU: đây là câu trả lời cho "sản phẩm này là gì", phải đứng
        # trước mọi con số. Chỉ làm khi ĐÃ neo sản phẩm - chưa neo mà tự kéo
        # định nghĩa vào là chọn hộ khách sản phẩm họ chưa nói.
        if san_pham and not shinhan_query:
            ma_neo = self._ma_san_pham(san_pham)
            mo_dau = self._manh_mo_dau(ma_neo)
            dau = (mo_dau or "")[:60]
            if mo_dau and not any(dau in (d or "") for d, k in zip(docs, giu) if k):
                ngu_canh = mo_dau + ("\n---\n" + ngu_canh if ngu_canh else "")
                chi_tiet.append({"doan": mo_dau, "diem": None,
                                 "nguon": f"{ma_neo}.md", "bi_loc": False,
                                 "mang_theo": True})
                logger.info("RAG: mang theo mảnh mở đầu của %s (không thắng điểm "
                            "nhưng chứa định nghĩa sản phẩm)", ma_neo)

        # KHÁCH NÊU ĐÍCH DANH SẢN PHẨM KHÁC trong câu ("lãi suất vay mua nhà với
        # vay tín chấp cái nào thấp hơn"): mang theo mảnh mở đầu của sản phẩm đó
        # nữa. Bộ lọc theo sản phẩm của phiên đã bỏ hết mảnh của nó, nên mô hình
        # đáp "em chưa có thông tin về lãi suất vay mua nhà" dù tài liệu ghi rõ
        # (bộ thử 304 lượt, 08-10-2026 - hai lượt so sánh đều hỏng kiểu này).
        if not shinhan_query:
            thap = (query or "").lower()
            ma_neo = self._ma_san_pham(san_pham) if san_pham else ""
            co_tl = self._san_pham_co_tai_lieu() or set()
            for ma, tu_khoa in self._TU_KHOA_SP:
                if ma == ma_neo or ma not in co_tl or not any(t in thap for t in tu_khoa):
                    continue
                mo_dau = self._manh_mo_dau(ma)
                if mo_dau and mo_dau[:60] not in ngu_canh:
                    ngu_canh = (ngu_canh + "\n---\n" if ngu_canh else "") + mo_dau
                    chi_tiet.append({"doan": mo_dau, "diem": None, "nguon": f"{ma}.md",
                                     "bi_loc": False, "mang_theo": True})
                    logger.info("RAG: mang theo mảnh mở đầu của %s (khách nêu đích "
                                "danh trong câu)", ma)

        # Ca (c) đã bỏ hết mảnh sản phẩm: NÓI THẲNG cho mô hình biết vì sao ngữ
        # cảnh trống, nếu không nó bịa số từ trí nhớ rồi bị lưới chặn cắt dở.
        # Đo được ngay sau khi thêm ca (c): câu ra "Hạn mức tín dụng
        # thường5003000" - vỡ vụn, tệ hơn cả câu sai ban đầu.
        if not san_pham and metas and len(metas) == len(docs):
            bo_products = [i for i, k in enumerate(giu)
                           if not k and _la_manh_products(metas[i])]
            if bo_products:
                ngu_canh = (CHUA_RO_SAN_PHAM + ("\n---\n" + ngu_canh if ngu_canh else ""))

        return ngu_canh, chi_tiet

    # Từ khoá nhận ra sản phẩm KHÁCH ĐANG HỎI, không phải sản phẩm của phiên.
    #
    # Vì sao cần dù `_mat_na_loc` đã có ca (b): ca đó chỉ soi `san_pham` của
    # PHIÊN. Cuộc gọi thật đang tư vấn vay tín chấp (sản phẩm CÓ tài liệu) nên
    # ca (b) không bao giờ chạy, dù khách vừa hỏi sang tiết kiệm. Đo 8 vòng
    # 05-09-2026: "gửi tiết kiệm tối thiểu bao nhiêu" -> AI đáp "200 triệu",
    # đó là hạn mức VAY.
    #
    # Danh sách CỨNG và cố ý để hẹp. Đã đo và BÁC BỎ hướng ngưỡng điểm khớp
    # (`scripts/do_nguong_rag.py`): hai nhóm chồng nhau, mà neo sản phẩm còn kéo
    # chúng chồng nhiều hơn. Cụm phải đủ đặc trưng - "thẻ" hay "vay" trơ trọi
    # thì quá rộng, câu nào cũng dính.
    _TU_KHOA_SP = [
        ("tiet_kiem", ("tiết kiệm",)),
        ("bao_hiem", ("bảo hiểm",)),
        ("chung_khoan", ("chứng khoán",)),
        ("ngoai_te", ("ngoại tệ", "đổi tiền")),
        # "tính chấp": nghe nhầm thật của STT. Bộ thử 10k (13-09): "độ tuổi vay
        # tính chấp là bao nhiêu" không neo được sản phẩm, rơi xuống mô hình
        # KHÔNG có tài liệu -> "chưa có thông tin về độ tuổi".
        ("vay_tin_chap", ("vay tín chấp", "tín chấp", "tính chấp")),
        ("vay_mua_nha", ("vay mua nhà", "mua bất động sản")),
        ("the_tin_dung", ("thẻ tín dụng",)),
    ]

    @classmethod
    def ten_san_pham(cls, ma: str) -> str:
        """Mã -> TÊN hiển thị. `"vay_tin_chap"` -> `"vay tín chấp"`; "" nếu lạ.

        Phải là tên người đọc được chứ không phải mã: nó đi thẳng vào dòng
        "Sản phẩm quan tâm" của lời dặn, khách nghe AI đọc "vay_tin_chap" thì
        hỏng cả cuộc.
        """
        for m, cum in cls._TU_KHOA_SP:
            if m == ma:
                return cum[0]
        return ""

    @classmethod
    def neo_moi_tu_cau(cls, cau: str, ma_co_tai_lieu: set[str] | None) -> str:
        """Tên sản phẩm khách VỪA NHẮC trong câu này; "" nếu câu không nêu gì.

        Dùng để NHỚ sản phẩm qua các lượt. `san_pham_neo` chỉ trả lời "lượt này
        neo vào đâu" rồi quên; phiên không có `product` thì lượt sau lại trắng.

        Lỗi thật trên cuộc gọi `73992c8d`: khách hỏi "bên bạn có cho vay tín
        chấp không" ở lượt 1, tới lượt 4 hỏi "mức lãi suất là bao nhiêu" thì AI
        đáp "cần tư vấn sản phẩm nào cụ thể không?" - khách phải tự nhắc lại.

        Trả "" cho cả hai ca KHÔNG neo được, và đó là chủ ý: câu không nêu sản
        phẩm nào (phần lớn lượt), và sản phẩm nêu ra mà kho không có tài liệu -
        neo vào thứ không có tài liệu là mời mô hình đọc số của sản phẩm khác.
        """
        ma = cls._san_pham_trong_cau(cau, ma_co_tai_lieu)
        return "" if ma in ("", "khong_co_tai_lieu") else cls.ten_san_pham(ma)

    @classmethod
    def _san_pham_trong_cau(cls, query: str, ma_co_tai_lieu: set[str] | None) -> str:
        """Mã sản phẩm mà CÂU HỎI nhắc tới.

        Trả `"khong_co_tai_lieu"` khi câu hỏi nêu rõ một sản phẩm mà kho không
        có tài liệu nào - lúc đó mọi mảnh `products` lấy được đều chắc chắn là
        của sản phẩm KHÁC.

        Trả `""` khi câu không nêu sản phẩm nào. Đó là phần lớn lượt trong cuộc
        gọi thật ("hạn mức được bao nhiêu"), và giữ nguyên hành vi cũ ở đó là
        VAN AN TOÀN - siết chỗ này là làm hỏng cả những lượt đang chạy tốt.
        """
        thap = (query or "").lower()
        for ma, cum in cls._TU_KHOA_SP:
            if any(c in thap for c in cum):
                if ma_co_tai_lieu is not None and ma not in ma_co_tai_lieu:
                    return "khong_co_tai_lieu"
                return ma
        return ""

    def san_pham_neo(self, query: str, san_pham: str = "") -> str:
        """Mã sản phẩm mà lượt này THẬT SỰ neo vào; "" khi không xác định được.

        Cùng phép neo mà `retrieve_chi_tiet` đang dùng, tách ra cho bên ngoài
        đọc được. `so_can_cu.SoCanCu` cần nó để biết lúc nào phải xoá sổ: căn cứ
        của vay mua nhà mà còn nằm lại khi đã chuyển sang vay tín chấp thì nó
        bảo chứng cho đúng con số "10 tỷ" mà `test_chua_ro_san_pham` sinh ra để
        chặn.

        KHÔNG tự nạp kho: hàm chạy trên đường găng độ trễ của cuộc gọi. Kho chưa
        nạp thì neo theo mỗi câu hỏi, không đối chiếu danh mục.
        """
        if san_pham:
            return self._ma_san_pham(san_pham)
        co_tl = self._san_pham_co_tai_lieu() if self._is_loaded else None
        ma = self._san_pham_trong_cau(query, co_tl)
        return "" if ma == "khong_co_tai_lieu" else ma

    @staticmethod
    def _ma_san_pham(s: str) -> str:
        """"Vay Tín Chấp" / "vay_tin_chap.md" -> "vay_tin_chap"."""
        s = PurePath(s.replace("\\", "/")).name
        s = s[:-3] if s.endswith(".md") else s
        s = unicodedata.normalize("NFD", s.lower())
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
        s = s.replace("đ", "d")
        return re.sub(r"[^a-z0-9]+", "_", s).strip("_")

    def _san_pham_co_tai_lieu(self) -> set[str] | None:
        """Mã của những sản phẩm THẬT SỰ có tài liệu trong kho đang tìm kiếm.

        Lấy từ chính collection chứ không đọc thư mục trên đĩa: kho có thể được
        nạp từ nơi khác, và thứ quyết định kết quả tìm kiếm là thứ ĐÃ NẠP.

        Nhớ lại kết quả vì nó chỉ đổi khi nạp/xoá tài liệu - `_quen_danh_muc`
        xoá bộ nhớ đó ở cả hai chỗ. Không nhớ thì mỗi lượt gọi thêm một lần đọc
        toàn bộ metadata, mà đường thoại gọi `retrieve` ba lần mỗi lượt.
        """
        if self._ma_sp_co_tai_lieu is None:
            ma: set[str] = set()
            try:
                got = self._collection.get(include=["metadatas"])
                for m in (got.get("metadatas") or []):
                    src = (m or {}).get("source") or ""
                    p = PurePath(src.replace("\\", "/"))
                    if p.parent.name == "products":
                        ma.add(self._ma_san_pham(p.name))
            except Exception as e:
                # Không đọc được thì trả tập RỖNG là sai hướng an toàn: nó biến
                # mọi sản phẩm thành "không có tài liệu" và lọc sạch. Trả None
                # để `_mat_na_loc` giữ nguyên hành vi cũ.
                logger.warning("Không đọc được danh mục sản phẩm của kho: %s", e)
                return None
            self._ma_sp_co_tai_lieu = ma
            logger.info("RAG: sản phẩm có tài liệu riêng: %s",
                        ", ".join(sorted(ma)) or "(không có)")
        return self._ma_sp_co_tai_lieu

    def _manh_mo_dau(self, ma: str) -> str:
        """Mảnh ĐẦU tài liệu của sản phẩm `ma` (tiêu đề + định nghĩa); "" nếu không có.

        Mảnh 0 là chỗ người soạn viết sản phẩm này LÀ GÌ. Nó hiếm khi thắng
        điểm cosine - câu khách hỏi thường chạm bảng số hoặc câu xử lý từ chối -
        nên với `top_k=2` nó gần như không bao giờ vào ngữ cảnh. Xem
        `tests/test_mang_theo_dinh_nghia.py` để biết cái giá thật của việc đó.

        Nhớ cả kết quả RỖNG: kho không đổi giữa cuộc gọi, mà hàm này nằm trên
        đường găng. `_quen_danh_muc` xoá bộ nhớ khi nạp/xoá tài liệu.
        """
        if ma in self._manh_dau_nho:
            return self._manh_dau_nho[ma]
        ra = ""
        try:
            co = self._collection.get(ids=[f"{ma}_chunk_0"],
                                      include=["documents"]) or {}
            docs = co.get("documents") or []
            ra = (docs[0] or "") if docs else ""
        except Exception as e:
            logger.warning("Không đọc được mảnh mở đầu của %r: %s", ma, e)
        self._manh_dau_nho[ma] = ra
        return ra

    def _quen_danh_muc(self):
        """Kho vừa đổi -> dựng lại danh mục sản phẩm ở lần hỏi sau."""
        self._ma_sp_co_tai_lieu = None
        self._manh_dau_nho.clear()

    @classmethod
    def _mat_na_loc(cls, docs: list[str], metas: list[dict] | None,
                    san_pham: str,
                    ma_co_tai_lieu: set[str] | None = None) -> list[bool]:
        """Mảnh nào thuộc SẢN PHẨM KHÁC với sản phẩm đang tư vấn thì bỏ.

        Trả MẶT NẠ (`True` = giữ) chứ không trả danh sách đã lọc: chỗ soi cần
        biết đoạn nào bị bỏ, mà nhìn phần còn lại thì không suy ra được.

        Vì sao cần: truy vấn đã được neo theo sản phẩm của phiên, nhưng `top_k`
        vẫn kéo thêm tài liệu sản phẩm bên cạnh - và LLM lấy SỐ ở đó. Đo được
        trong hội thoại dựng thử: khách đang tư vấn VAY TÍN CHẤP hỏi lãi suất,
        RAG trả về vay_tin_chap.md (7.9%) kèm vay_mua_nha.md (6.5%), LLM đọc ra
        **6.5%** - lãi suất của sản phẩm khác, sai hoàn toàn.

        Tệ hơn: `chan_so_sai` không cứu được, vì luật của nó là "tài liệu có
        nhiều hơn một số thập phân thì để nguyên, đoán bừa còn tệ hơn". Chính
        mảnh lạc kia làm ngữ cảnh có hai số, nên lưới an toàn cuối cùng tự tắt
        đúng lúc cần nhất. Phải chặn từ đây.

        Neo theo SẢN PHẨM CỦA PHIÊN chứ không theo mảnh đứng đầu: câu hỏi chung
        chung thì chính mảnh đầu cũng lạc. Đo được: "vay tín chấp cần giấy tờ
        gì" cho mảnh đầu là vay_mua_nha.md, neo theo nó thì lọc xong vẫn sai.

        Chỉ lọc trong thư mục `products` - mảnh FAQ hay chính sách vẫn giữ, vì
        chúng bổ nghĩa chứ không cạnh tranh về số liệu.

        HAI CA KHÁC HẲN NHAU, đừng gộp (bản cũ gộp và đó là lỗi):

        a) Sản phẩm CÓ tài liệu, nhưng truy vấn này không lôi được mảnh nào của
           nó. Đây là hụt truy vấn - giữ nguyên tất cả, vì mảnh sản phẩm khác
           vẫn có thể đang nói chuyện chung (điều kiện, thủ tục).

        b) Sản phẩm KHÔNG HỀ có tài liệu (vd "tiết kiệm" - `knowledge/products/`
           chỉ có thẻ tín dụng, vay mua nhà, vay tín chấp). Lúc này MỌI mảnh
           sản phẩm đều chắc chắn nói về sản phẩm KHÁC, giữ lại là mời mô hình
           đọc số của người ta. Đo được 13-08-2026, lặp lại cả ba lần: hỏi "lãi
           suất gửi tiết kiệm bao nhiêu" thì AI đáp **7,9%/năm** - đó là lãi VAY
           tín chấp. Báo sai lãi suất cho khách trong cuộc gọi bán sản phẩm tài
           chính là lỗi nặng.

        Ca (b) bỏ HẾT mảnh sản phẩm nhưng vẫn giữ FAQ/chính sách, nên mô hình
        còn ngữ cảnh chung để nói "em xin phép kiểm tra lại và báo lại anh chị"
        theo quy tắc 3 - đúng thứ nên nói khi không có dữ liệu.

        `ma_co_tai_lieu` là tập mã sản phẩm THẬT SỰ có tài liệu trong kho.
        Không truyền thì giữ nguyên hành vi cũ - để lối gọi nào chưa biết tập
        này không đổi hành vi âm thầm.
        """
        moc = cls._ma_san_pham(san_pham) if san_pham else ""
        if not metas or len(metas) != len(docs):
            return [True] * len(docs)

        def cua_san_pham(meta: dict | None) -> str:
            src = (meta or {}).get("source") or ""
            p = PurePath(src.replace("\\", "/"))
            return cls._ma_san_pham(p.name) if p.parent.name == "products" else ""

        ma = [cua_san_pham(m) for m in metas]

        # CA (c): PHIÊN CHƯA BIẾT SẢN PHẨM và truy vấn lôi về mảnh của NHIỀU sản
        # phẩm. Không có mốc để neo, giữ nguyên là mời mô hình chọn bừa - và nó
        # chọn con số to nhất.
        #
        # Đo trên cuộc gọi thật `9874c82c` (06-09-2026), liên hệ chưa khai sản
        # phẩm nên `session.product` rỗng: khách hỏi "hạn mức bao nhiêu", AI đáp
        # "tối đa 10 TỶ đồng" rồi hỏi tài sản đảm bảo - số của `vay_mua_nha.md`,
        # sai 20 lần so với hạn mức tín chấp thật. `chan_tien_sai` cho qua ĐÚNG
        # LUẬT vì 10 tỷ CÓ trong ngữ cảnh: lưới không hỏng, nó bị bịt mắt.
        #
        # Bỏ hết mảnh `products`, GIỮ FAQ/chính sách - y như ca (b). Ngữ cảnh
        # hết số sản phẩm thì `chan_tien_sai` tự chặn mọi số, và mô hình chỉ còn
        # đường hỏi lại khách đang quan tâm sản phẩm nào. Đúng nghiệp vụ: thật
        # sự chưa ai nói khách muốn gì.
        #
        # MỘT sản phẩm thì KHÔNG cắt - không có gì để lẫn, mà cắt đi là bỏ mất
        # câu trả lời đang đúng.
        if not moc:
            khac_nhau = {m for m in ma if m}
            if len(khac_nhau) >= 2:
                logger.info(
                    "RAG: phiên CHƯA RÕ sản phẩm mà truy vấn chạm %d sản phẩm "
                    "(%s) - bỏ hết mảnh products để mô hình khỏi đọc số của "
                    "sản phẩm khách không hỏi", len(khac_nhau),
                    ", ".join(sorted(khac_nhau)))
                return [not m for m in ma]
            return [True] * len(docs)
        if moc not in ma:
            if ma_co_tai_lieu is not None and moc not in ma_co_tai_lieu:
                # ca (b): sản phẩm này không có tài liệu nào -> mọi mảnh sản
                # phẩm đều là của người khác.
                giu = [not s for s in ma]
                if not all(giu):
                    logger.info(
                        "RAG: '%s' không có tài liệu riêng - bỏ %d mảnh của sản "
                        "phẩm khác (%s) để mô hình khỏi đọc số của người ta",
                        moc, giu.count(False),
                        ", ".join(sorted({s for s in ma if s})))
                return giu
            # ca (a): hụt truy vấn -> đừng lọc
            return [True] * len(docs)

        giu = [not s or s == moc for s in ma]
        if not all(giu):
            logger.info("RAG: bỏ %d mảnh lạc sản phẩm (%s) vì đang tư vấn %s",
                        giu.count(False),
                        ", ".join(sorted({s for s in ma if s and s != moc})), moc)
        return giu

    def ingest_text(
        self,
        content: str,
        doc_id: str,
        metadata: dict | None = None,
        *,
        _existing_ids: list[str] | None = None,
    ):
        """Add a document to the knowledge base."""
        if not self._is_loaded:
            self.load()

        chunks = self._chunk_text(content, chunk_size=500, overlap=50)
        if not chunks:
            return

        embeddings = self._embedder.encode(chunks).tolist()
        ids = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]
        meta = dict(metadata or {})
        # Hash nằm ngay trong từng mảnh để lần khởi động sau có thể biết file
        # trên đĩa còn y hệt hay đã đổi mà không phải nhúng lại toàn bộ tài liệu.
        # `setdefault` cho phép nguồn dữ liệu đặc biệt tự mang hash riêng nếu cần.
        meta.setdefault("content_sha256", hashlib.sha256(content.encode("utf-8")).hexdigest())
        meta.setdefault("chunker_version", CHUNKER_VERSION)
        meta.setdefault("indexed_at", time.time())
        metadatas = [meta for _ in chunks]

        # XOÁ mảnh cũ của CHÍNH tài liệu này trước đã. Chroma `add` gặp id trùng
        # thì BỎ QUA IM LẶNG chứ không ghi đè, nên thiếu bước này là sửa tài liệu
        # bao nhiêu lần cũng vô ích: kho đứng nguyên ở bản ĐẦU TIÊN từng nạp, mà
        # log vẫn ghi "Ingested N chunks" như đã làm gì đó.
        #
        # Đo trên máy chạy thật 07-09-2026: `ingest_directory` báo nạp 3 mảnh
        # `vay_tin_chap` nhưng số mảnh trong kho không đổi (9 trước, 9 sau), và
        # kho vẫn giữ bản cũ - trong đó có dòng "Nợ xấu vẫn có cách lách để vay
        # được". Đó chính là nguồn câu AI nói với khách; mô hình KHÔNG bịa, nó
        # đọc đúng tài liệu. Grep các file trên đĩa không thấy, vì dòng đó chỉ
        # còn tồn tại trong kho vector.
        #
        # Xoá theo TIỀN TỐ id chứ không theo metadata: cùng một tài liệu từng
        # được nạp với `source` lúc là đường dẫn tuyệt đối lúc là tương đối, lọc
        # theo metadata sẽ sót. Và phải xoá theo id CŨ chứ không phải theo `ids`
        # vừa dựng - bản cũ có thể NHIỀU mảnh hơn bản mới, xoá thiếu thì mảnh
        # thừa sống sót và vẫn được RAG lôi ra.
        try:
            # `ingest_directory` đã snapshot toàn kho một lần nên truyền thẳng
            # danh sách cũ vào đây. Các caller khác vẫn dùng đường cũ để giữ API
            # và hành vi ghi đè hiện tại.
            cu = _existing_ids
            if cu is None:
                cu = [i for i in (self._collection.get(include=[]).get("ids") or [])
                      if isinstance(i, str) and i.startswith(f"{doc_id}_chunk_")]
            if cu:
                self._collection.delete(ids=cu)
                logger.info("Nạp lại %r: bỏ %d mảnh cũ", doc_id, len(cu))
        except Exception as e:
            # Xoá hỏng thì vẫn nạp tiếp - thà có mảnh cũ lẫn vào còn hơn mất
            # trắng tài liệu. Nhưng phải kêu to, vì im lặng ở đây là quay về
            # đúng cái lỗi vừa chữa.
            logger.warning("Không xoá được mảnh cũ của %r (%s) - kho có thể "
                           "còn lẫn bản cũ", doc_id, e)

        self._collection.add(
            documents=chunks,
            embeddings=embeddings,
            ids=ids,
            metadatas=metadatas,
        )
        # Kho vừa có tài liệu mới -> danh mục sản phẩm có thể đã khác.
        self._quen_danh_muc()
        logger.info(f"Ingested {len(chunks)} chunks from '{doc_id}'")

    def ingest_directory(self, directory: str):
        """Đồng bộ .md/.txt vào Chroma, chỉ nhúng file mới hoặc đã thay đổi.

        Trước đây mỗi lần backend khởi động đều đọc, chunk, encode và xoá/nạp
        lại TOÀN BỘ kho. Với vài file thì khó thấy, nhưng khi kho tăng lên hàng
        trăm/hàng nghìn tài liệu thì thời gian mở app tăng gần tuyến tính theo
        tổng dung lượng tài liệu dù không có gì thay đổi.

        Ta snapshot metadata một lần, so SHA-256 của từng file, và chỉ gọi
        `ingest_text` cho file mới/sửa. File đã xoá khỏi thư mục cũng được xoá
        khỏi Chroma để tránh RAG tiếp tục đọc tri thức cũ.
        """
        if not self._is_loaded:
            self.load()

        dir_path = Path(directory)
        if not dir_path.exists():
            logger.warning(f"Knowledge directory not found: {directory}")
            return {"files": 0, "changed": 0, "skipped": 0, "stale_chunks": 0}

        try:
            hien_co = self._collection.get(include=["metadatas"]) or {}
            old_ids = hien_co.get("ids") or []
            old_metas = hien_co.get("metadatas") or []
        except Exception as e:
            logger.warning("Không đọc được metadata RAG để nạp tăng dần (%s) - "
                           "sẽ nạp lại tài liệu như trước", e)
            old_ids, old_metas = [], []

        # Cùng một source có nhiều chunk; gom một lần để mỗi file không phải
        # quét toàn collection. `source` cũ vẫn được hỗ trợ để lần nâng cấp đầu
        # tiên tự chuyển sang metadata mới mà không để mảnh rác sống sót.
        theo_source: dict[str, list[tuple[str, dict]]] = {}
        theo_rel: dict[tuple[str, str], list[tuple[str, dict]]] = {}
        theo_doc_id: dict[str, list[tuple[str, dict]]] = {}
        root_abs = str(dir_path.resolve())
        managed_old_ids: set[str] = set()
        for i, chunk_id in enumerate(old_ids):
            meta = old_metas[i] if i < len(old_metas) and isinstance(old_metas[i], dict) else {}
            source = str(meta.get("source") or "")
            if source:
                theo_source.setdefault(source, []).append((chunk_id, meta))
            root = str(meta.get("knowledge_root") or "")
            rel = str(meta.get("knowledge_relpath") or "")
            if root and rel:
                theo_rel.setdefault((root, rel), []).append((chunk_id, meta))
            if root == root_abs:
                managed_old_ids.add(chunk_id)
            elif source:
                # Chuyển tiếp từ bản cũ chưa có `knowledge_root`: nhận ra các
                # source .md/.txt thực sự nằm dưới thư mục đang đồng bộ. Nhờ đó
                # file đã bị xoá trước lần nâng cấp đầu tiên cũng được dọn sạch.
                try:
                    source_path = Path(source)
                    if (source_path.suffix.lower() in {".md", ".txt"}
                            and source_path.resolve().is_relative_to(dir_path.resolve())):
                        managed_old_ids.add(chunk_id)
                except (OSError, ValueError):
                    pass
            if isinstance(chunk_id, str):
                m = re.match(r"^(.+)_chunk_\d+$", chunk_id)
                if m:
                    theo_doc_id.setdefault(m.group(1), []).append((chunk_id, meta))

        files = sorted(dir_path.rglob("*.md")) + sorted(dir_path.rglob("*.txt"))
        # Cảnh báo va chạm thay vì âm thầm ghi đè. Đổi ID toàn bộ ngay tại đây
        # sẽ phá `_manh_mo_dau`, vốn dùng `<ma_san_pham>_chunk_0` để mang theo
        # định nghĩa sản phẩm. Ta giữ ID cũ và chỉ báo rõ để xử lý có chủ đích.
        stems: dict[str, list[str]] = {}
        for p in files:
            stems.setdefault(p.stem, []).append(p.relative_to(dir_path).as_posix())
        for stem, rels in stems.items():
            if len(rels) > 1:
                logger.warning("RAG: trùng tên file %r trong knowledge: %s; các file "
                               "này đang dùng chung doc_id và có thể ghi đè nhau",
                               stem, ", ".join(rels))

        changed = 0
        skipped = 0
        seen_old_ids: set[str] = set()

        for file_path in files:
            content = file_path.read_text(encoding="utf-8")
            source = str(file_path)
            rel = file_path.relative_to(dir_path).as_posix()
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()

            # Match theo doc_id là lớp cuối cùng rất quan trọng: UI quản lý tri
            # thức từng lưu `source` tuyệt đối, còn startup có thể dùng đường dẫn
            # tương đối. Chroma vẫn nhận ra trùng ID và `add()` sẽ bỏ qua bản mới
            # nếu ta không xóa những ID cũ đó trước.
            old = (theo_rel.get((root_abs, rel)) or theo_source.get(source)
                   or theo_doc_id.get(file_path.stem) or [])
            old_file_ids = [chunk_id for chunk_id, _ in old]
            seen_old_ids.update(old_file_ids)

            # Tất cả chunk của file phải cùng hash. Nếu metadata cũ chưa có hash
            # thì nạp lại đúng một lần để chuyển sang định dạng mới.
            old_hashes = {str(meta.get("content_sha256") or "") for _, meta in old}
            old_chunkers = {str(meta.get("chunker_version") or "") for _, meta in old}
            is_shinhan = rel.startswith("shinhan/")
            old_banks = {str(meta.get("bank") or "") for _, meta in old}
            if (content.strip() and old and old_hashes == {digest}
                    and old_chunkers == {CHUNKER_VERSION}
                    and (not is_shinhan or old_banks == {"shinhan"})):
                skipped += 1
                continue

            # File trở thành rỗng: xoá tri thức cũ nhưng không tạo chunk rỗng.
            if not content.strip():
                if old_file_ids:
                    self._collection.delete(ids=old_file_ids)
                    self._quen_danh_muc()
                    changed += 1
                continue

            self.ingest_text(
                content,
                doc_id=file_path.stem,
                metadata={
                    "source": source,
                    "knowledge_root": root_abs,
                    "knowledge_relpath": rel,
                    "content_sha256": digest,
                    **({"bank": "shinhan"} if is_shinhan else {}),
                },
                _existing_ids=old_file_ids,
            )
            changed += 1

        # Dọn file đã bị xoá khỏi thư mục. Chỉ xóa record do chính root này quản
        # lý; dữ liệu ngoài (`ds:...`, Excel/API, v.v.) dùng cùng collection vẫn
        # được giữ nguyên.
        stale_ids = sorted(managed_old_ids - seen_old_ids)
        if stale_ids:
            self._collection.delete(ids=stale_ids)
            self._quen_danh_muc()
            logger.info("RAG: xoá %d mảnh của tài liệu đã bị xoá khỏi %s",
                        len(stale_ids), directory)

        logger.info("Knowledge sync %s: %d file đổi/mới, %d file giữ nguyên, "
                    "%d chunk cũ bị dọn", directory, changed, skipped, len(stale_ids))
        return {
            "files": len(files),
            "changed": changed,
            "skipped": skipped,
            "stale_chunks": len(stale_ids),
        }

    def _chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
        """Split text into overlapping chunks by character count.

        Gọi thẳng `cat_manh` chứ không chép lại: khung "sẽ cắt thành mấy mảnh"
        trong hộp soạn tài liệu dùng cùng hàm này. Hai bản chép rồi lệch nhau thì
        khung đó nói dối, mà người viết lại tin nó.
        """
        return cat_manh(text, chunk_size, overlap)

    def xoa_theo_nguon(self, source: str) -> int:
        """Xoá mọi mảnh mang metadata `source` này. Trả về số mảnh đã xoá.

        Cần cho việc nạp lại một nguồn dữ liệu ngoài (bảng giá Excel chẳng hạn):
        không xoá cũ trước thì mỗi lần nạp lại là một bản sao mới, và RAG trả về
        cả bảng giá cũ lẫn mới - đúng kiểu lỗi khiến bot đọc sai số cho khách.
        """
        if not self._is_loaded:
            self.load()
        if not source:
            return 0
        try:
            co = self._collection.get(where={"source": source}, include=[])
            ids = co.get("ids") or []
            if ids:
                self._collection.delete(ids=ids)
                # Xoá hết tài liệu của một sản phẩm là nó thành "không có tài
                # liệu" - danh mục phải dựng lại, không thì lưới lọc vẫn tưởng
                # sản phẩm đó còn tài liệu.
                self._quen_danh_muc()
            return len(ids)
        except Exception as e:
            logger.warning(f"Không xoá được mảnh RAG của nguồn '{source}': {e}")
            return 0

    def dem_theo_nguon(self, source: str) -> int:
        if not self._is_loaded:
            self.load()
        try:
            return len((self._collection.get(where={"source": source}, include=[]) or {}).get("ids") or [])
        except Exception:
            return 0

    def thong_tin_nguon(self, sources: list[str]) -> dict:
        """Thông tin chỉ mục của một tài liệu theo mọi dạng `source` có thể có.

        UI quản lý tri thức cần phân biệt ba trạng thái: chưa có vector, vector
        đang khớp file trên đĩa, và file đã đổi nhưng vector còn là bản cũ. Hash
        đã được lưu trong metadata từng chunk nên đọc trạng thái này không cần
        chạy embedding hay gọi Qwen.
        """
        if not self._is_loaded:
            self.load()

        ids: set[str] = set()
        hashes: set[str] = set()
        indexed_at = 0.0
        for source in dict.fromkeys(s for s in sources if s):
            try:
                co = self._collection.get(
                    where={"source": source}, include=["metadatas"]
                ) or {}
            except Exception:
                continue
            row_ids = co.get("ids") or []
            metas = co.get("metadatas") or []
            for i, chunk_id in enumerate(row_ids):
                if isinstance(chunk_id, str):
                    ids.add(chunk_id)
                meta = metas[i] if i < len(metas) and isinstance(metas[i], dict) else {}
                digest = str(meta.get("content_sha256") or "")
                if digest:
                    hashes.add(digest)
                try:
                    indexed_at = max(indexed_at, float(meta.get("indexed_at") or 0.0))
                except (TypeError, ValueError):
                    pass

        return {
            "so_manh": len(ids),
            "hashes": sorted(hashes),
            "indexed_at": indexed_at or None,
        }

    def lay_theo_nguon(self, source: str) -> list[str]:
        """Nội dung các mảnh kho ĐANG giữ cho nguồn này, theo đúng thứ tự tài liệu.

        Đọc từ kho chứ không cắt lại từ file trên đĩa: cắt lại luôn ra kết quả
        đẹp kể cả khi kho còn giữ bản cũ - đúng cái bẫy mà `dem_theo_nguon` sinh
        ra để cảnh báo.

        Sắp theo SỐ trong id `<doc_id>_chunk_<i>`. `get()` của Chroma không hứa
        giữ thứ tự thêm vào, mà sắp theo chuỗi thì mảnh 10 đứng trước mảnh 2 và
        người đọc tưởng tài liệu bị đảo lộn.
        """
        if not self._is_loaded:
            self.load()
        if not source:
            return []
        try:
            co = self._collection.get(where={"source": source},
                                      include=["documents"]) or {}
            ids = co.get("ids") or []
            docs = co.get("documents") or []
        except Exception as e:
            logger.warning(f"Không đọc được mảnh RAG của nguồn '{source}': {e}")
            return []

        def _so(ma: str) -> int:
            m = re.search(r"_chunk_(\d+)$", ma or "")
            return int(m.group(1)) if m else 0

        return [d for _, d in sorted(zip(ids, docs), key=lambda c: _so(c[0]))]

    def clear(self):
        """Clear the entire knowledge base."""
        if self._collection:
            self._client.delete_collection("banking_knowledge")
            self._collection = self._client.get_or_create_collection("banking_knowledge")
            logger.info("Knowledge base cleared")
