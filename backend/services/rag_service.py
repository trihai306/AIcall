import logging
import re
import unicodedata
from pathlib import Path, PurePath
import chromadb
from backend.config import settings
from backend.core.logging_config import Timer

logger = logging.getLogger(__name__)


def cat_manh(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Cắt văn bản thành mảnh chồng lấn theo SỐ KÝ TỰ.

    Đây là cách cắt duy nhất của hệ thống - RAG nạp tài liệu bằng nó, và khung
    xem trước trong hộp soạn tài liệu cũng gọi chính nó. Cắt theo ký tự nên
    không biết gì về cấu trúc markdown: bảng lãi suất dài sẽ bị chặt mất dòng
    tiêu đề, câu bị bẻ giữa từ. Muốn đổi thì đổi ở ĐÂY, cả hai nơi cùng theo.
    """
    text = text.strip()
    if len(text) <= chunk_size:
        return [text] if text else []

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start = end - overlap

    return chunks


class RAGService:
    """ChromaDB + embedding model for retrieval-augmented generation."""

    def __init__(self):
        self._client = None
        self._collection = None
        self._embedder = None
        self._is_loaded = False
        # Danh mục sản phẩm có tài liệu riêng, dựng lười. None = chưa biết.
        self._ma_sp_co_tai_lieu: set[str] | None = None

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

        def _query():
            embedding = self._embedder.encode([query])[0].tolist()
            return self._collection.query(
                query_embeddings=[embedding],
                n_results=min(top_k, self._collection.count()),
                include=["documents", "distances", "metadatas"],
            )

        with Timer("RAG", logger):
            results = await asyncio.to_thread(_query)

        if not results["documents"] or not results["documents"][0]:
            return "", []

        docs = results["documents"][0]
        metas = (results.get("metadatas") or [[]])[0] or []
        dists = (results.get("distances") or [[]])[0] or []

        co_tl = self._san_pham_co_tai_lieu()
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

        return "\n---\n".join(d for d, k in zip(docs, giu) if k), chi_tiet

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
        ("vay_tin_chap", ("vay tín chấp", "tín chấp")),
        ("vay_mua_nha", ("vay mua nhà", "mua bất động sản")),
        ("the_tin_dung", ("thẻ tín dụng",)),
    ]

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

    def _quen_danh_muc(self):
        """Kho vừa đổi -> dựng lại danh mục sản phẩm ở lần hỏi sau."""
        self._ma_sp_co_tai_lieu = None

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
        if not moc or not metas or len(metas) != len(docs):
            return [True] * len(docs)

        def cua_san_pham(meta: dict | None) -> str:
            src = (meta or {}).get("source") or ""
            p = PurePath(src.replace("\\", "/"))
            return cls._ma_san_pham(p.name) if p.parent.name == "products" else ""

        ma = [cua_san_pham(m) for m in metas]
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

    def ingest_text(self, content: str, doc_id: str, metadata: dict | None = None):
        """Add a document to the knowledge base."""
        if not self._is_loaded:
            self.load()

        chunks = self._chunk_text(content, chunk_size=500, overlap=50)
        if not chunks:
            return

        embeddings = self._embedder.encode(chunks).tolist()
        ids = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [metadata or {} for _ in chunks]

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
        """Ingest all .md and .txt files from a directory."""
        dir_path = Path(directory)
        if not dir_path.exists():
            logger.warning(f"Knowledge directory not found: {directory}")
            return

        count = 0
        for file_path in sorted(dir_path.rglob("*.md")) + sorted(dir_path.rglob("*.txt")):
            content = file_path.read_text(encoding="utf-8")
            if content.strip():
                self.ingest_text(content, doc_id=file_path.stem, metadata={"source": str(file_path)})
                count += 1

        logger.info(f"Ingested {count} files from {directory}")

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
