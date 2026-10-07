"""Qwen TỰ ĐẶT câu hỏi như một khách hàng để làm dày kho trả lời.

Bộ dựng kho cũ đi từ TÀI LIỆU ra câu hỏi: đọc từng mảnh rồi hỏi về đúng mảnh đó,
nên kho chỉ có những câu "soạn theo tài liệu". Khách thật thì hỏi theo nhu cầu
của họ, không theo mục lục. Ở đây đi chiều ngược lại:

1. Qwen đóng vai khách, chỉ biết TÊN và mô tả ngắn của sản phẩm, nghĩ ra những
   câu khách hay hỏi qua điện thoại - kể cả câu chung chung, câu tài liệu có thể
   không nhắc tới.
2. Câu nào kho của tài liệu đó đã có thì bỏ.
3. Câu còn lại đưa cho bộ soạn đáp án CÓ CĂN CỨ sẵn có (`generate_document`):
   đáp án phải trích được bằng chứng trong tài liệu và qua bước xác minh.
4. Câu tài liệu KHÔNG trả lời được thì KHÔNG bịa đáp án: ghi vào sổ "câu chưa
   có đáp án" để người soạn tay. Đây là tư vấn tài chính.

Chạy nền một việc một lúc, nhường GPU cho cuộc gọi qua `_guarded` như mọi việc
nền khác của kho.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time

from backend.services import answer_bank_gaps as gaps
from backend.services import answer_bank_learning as learning
from backend.services import knowledge_qa_service as qa

logger = logging.getLogger(__name__)

# Góc hỏi gợi cho Qwen, để câu hỏi rải đều thay vì xoay quanh mỗi lãi suất.
GOC_HOI = (
    "điều kiện và đối tượng được tham gia", "hồ sơ, giấy tờ, thủ tục", "lãi suất, phí, chi phí",
    "hạn mức, số tiền, kỳ hạn", "thời gian xử lý, giải ngân, nhận kết quả",
    "cách trả nợ, tất toán, trả trước hạn", "rủi ro, chậm trả, phạt", "bảo mật và độ tin cậy",
    "ưu đãi, khuyến mãi", "tình huống riêng của khách (nghề tự do, nợ cũ, lương tiền mặt, ở tỉnh)",
    "đăng ký ở đâu, bằng cách nào", "băn khoăn, so sánh, ngại ngần trước khi quyết định",
)

_NE_TRANH = re.compile(
    r"(?i)xem (?:chi tiết|thêm|cụ thể)|tham khảo (?:thêm |chi tiết )?(?:trong |tại |ở )?tài liệu|"
    r"trong tài liệu sản phẩm|để biết (?:thêm )?chi tiết")

_trang_thai: dict = {"dang_chay": False, "nhat_ky": [], "them": 0, "thieu": 0,
                     "tai_lieu": "", "bat_dau": None, "ket_thuc": None, "loi": ""}
_viec: asyncio.Task | None = None


def trang_thai() -> dict:
    return {**_trang_thai, "nhat_ky": list(_trang_thai["nhat_ky"][-12:])}


def _ghi(message: str) -> None:
    logger.info("Qwen tự hỏi: %s", message)
    _trang_thai["nhat_ky"].append(time.strftime("%H:%M:%S ") + message)
    del _trang_thai["nhat_ky"][:-60]


def _prompt_dat_cau_hoi(doc: learning.Document, so_cau: int, da_co: list[str]) -> str:
    goc = "\n".join(f"- {g}" for g in GOC_HOI)
    tranh = "\n".join(f"- {q}" for q in da_co[-60:]) or "(chưa có)"
    return f"""Bạn đóng vai KHÁCH HÀNG đang nghe điện thoại tư vấn của ngân hàng.
Chủ đề cuộc gọi: {doc.stem.replace('_', ' ')} - {learning._doc_profile(doc)}
Hãy nghĩ ra {so_cau} câu mà khách thật hay hỏi về chủ đề này, rải đều các góc:
{goc}
Yêu cầu:
- Lời nói miệng, ngắn, tự nhiên, xưng anh/chị, gọi tư vấn viên là em. Mỗi câu MỘT ý.
- Không hỏi về hồ sơ, số dư hay kết quả duyệt của riêng một người.
- Không lặp ý các câu đã có dưới đây.
ĐÃ CÓ:
{tranh}
Viết mỗi câu trên một dòng có đánh số, câu nào cũng kết thúc bằng dấu hỏi "?".
Không giải thích, không thêm gì khác."""


def _tach_cau_hoi(text: str) -> list[str]:
    """Tách các câu hỏi khỏi lời Qwen. `_chat` đã gộp xuống dòng thành khoảng
    trắng, nên ranh giới duy nhất còn tin được là dấu hỏi cuối mỗi câu."""
    ra = []
    for part in re.split(r"\?+", text or "")[:-1]:
        q = re.sub(r"^[\s\"'“”*\-–•]*(?:\d{1,3}\s*[.)\]:]\s*)?[\s\"'“”*\-–•]*", "", part).strip(" \"'“”*")
        if 2 <= len(q.split()) <= 30:
            ra.append(q + "?")
    return ra


async def _dat_cau_hoi(doc: learning.Document, so_cau: int, known: dict) -> list[str]:
    ra: list[str] = []
    khoa_da_thay: set = set()
    da_co: list[str] = []
    for _ in range(max(1, (so_cau + 19) // 20) + 1):
        if len(ra) >= so_cau:
            break
        # Văn bản thường chứ KHÔNG phải JSON: đo 07-10-2026, mảng 20 chuỗi tiếng
        # Việt có ngoặc kép bên trong hỏng JSON cả hai lần gọi ở 2/2 tài liệu đầu.
        text = await learning._guarded(
            learning._chat(_prompt_dat_cau_hoi(doc, min(20, so_cau - len(ra) + 4), da_co), 1800),
            learning.settings.answer_bank_llm_timeout_s)
        moi = 0
        for q in _tach_cau_hoi(text):
            q = learning.sanitize_history(learning._normal(q))[:200]
            key = learning._question_key(q)
            if len(key) < 2 or key in khoa_da_thay or learning._META_INTENT.match(q):
                continue
            khoa_da_thay.add(key)
            da_co.append(q)
            if not known.get(key):
                ra.append(q)
                moi += 1
        if not moi:
            break
    return ra[:so_cau]


async def _mot_tai_lieu(doc: learning.Document, so_cau: int, cfg: dict) -> tuple[list[str], int]:
    async with learning.source_operation_lock(doc):
        if not learning._source_is_current(doc):
            _ghi(f"{doc.rel}: tài liệu vừa đổi, bỏ qua")
            return [], 0
        known = learning._known_question_keys(doc)
        for q in gaps.cau_hoi_cho_duyet():  # câu đang chờ duyệt thì đừng hỏi lại
            known[learning._question_key(q)] = 1
        cau_hoi = await _dat_cau_hoi(doc, so_cau, known)
        if not cau_hoi:
            _ghi(f"{doc.rel}: không nghĩ thêm được câu nào mới")
            return [], 0
        stage = "tuhoi:" + hashlib.sha1("\n".join(cau_hoi).encode()).hexdigest()[:12]
        items, reasons = await learning.generate_document(
            doc, len(cau_hoi), cfg["variants_per_answer"], cau_hoi, stage_key=stage)
        # Câu "mời xem tài liệu" không phải là đáp án.
        items = [item for item in items if not _NE_TRANH.search(item["tra_loi"])]
        co_dap_an = {qa._khong_dau(q) for item in items for q in item["cau_hoi"]}
        conn = learning._conn()
        # Trùng id với một đáp án ĐANG BẬT (cùng câu hỏi, cùng chữ) thì không lưu
        # lại: lưu là ghi đè rồi tắt mất một dòng đang chạy.
        items = [item for item in items if not conn.execute(
            "SELECT 1 FROM hoi_dap WHERE id=? AND bat=1",
            (learning._id_for(doc, item, "memory"),)).fetchone()]
        ids = learning._store_items(doc, items, "memory", replace=False) if items else []
        gaps.cho_duyet(ids)  # vào kho ở trạng thái TẮT, chờ người duyệt
        thieu = [q for q in cau_hoi if qa._khong_dau(q) not in co_dap_an]
        san_pham = doc.stem if doc.group == "products" else ""
        for q in thieu:
            gaps.ghi_thieu_tu_hoi(q, san_pham)
        _ghi(f"{doc.rel}: hỏi {len(cau_hoi)} câu mới, soạn được {len(ids)} đáp án có căn cứ (chờ duyệt), "
             f"{len(thieu)} câu tài liệu không trả lời được" + (f" ({reasons})" if reasons else ""))
        return ids, len(thieu)


async def _chay(so_cau: int, chi_tai_lieu: str) -> None:
    worker = learning.AnswerBankLearning()
    worker._state = learning.bo_hoc_tra_loi._state
    token = qa._manual_bank_worker.set(worker)
    try:
        docs, _logs = learning.prepare_sources()
        if chi_tai_lieu:
            docs = [d for d in docs if d.rel == chi_tai_lieu or f"{d.group}/{d.stem}" == chi_tai_lieu]
        cfg = learning._config()
        for doc in docs:
            _trang_thai["tai_lieu"] = doc.rel
            for lan in range(40):  # nhường cuộc gọi: chờ tối đa ~20 phút mỗi tài liệu
                try:
                    ids, thieu = await _mot_tai_lieu(doc, so_cau, cfg)
                    break
                except learning.PausedForCustomer:
                    if lan == 0:
                        _ghi(f"{doc.rel}: đang có cuộc gọi, tạm chờ")
                    await asyncio.sleep(30)
                except Exception as exc:
                    _ghi(f"{doc.rel}: lỗi {type(exc).__name__}: {exc}")
                    ids, thieu = [], 0
                    break
            else:
                _ghi(f"{doc.rel}: máy bận quá lâu, bỏ qua lần này")
                ids, thieu = [], 0
            _trang_thai["them"] += len(ids)
            _trang_thai["thieu"] += thieu
        _ghi(f"Xong: {_trang_thai['them']} đáp án chờ duyệt, {_trang_thai['thieu']} câu cần soạn tay")
    except Exception as exc:
        logger.exception("Qwen tự hỏi dừng vì lỗi")
        _trang_thai["loi"] = f"{type(exc).__name__}: {exc}"
    finally:
        qa._manual_bank_worker.reset(token)
        _trang_thai.update(dang_chay=False, tai_lieu="", ket_thuc=time.time())


def bat_dau(so_cau: int = 40, chi_tai_lieu: str = "") -> dict:
    """Chạy nền một lượt tự hỏi. `so_cau` là số câu MỚI mỗi tài liệu."""
    global _viec
    if _trang_thai["dang_chay"]:
        return {"ok": False, "error": "Đang chạy một lượt tự hỏi rồi", **trang_thai()}
    _trang_thai.update(dang_chay=True, nhat_ky=[], them=0, thieu=0, tai_lieu="",
                       bat_dau=time.time(), ket_thuc=None, loi="")
    _viec = asyncio.get_running_loop().create_task(
        _chay(max(5, min(int(so_cau), 200)), chi_tai_lieu), name="answer-bank-selfask")
    return {"ok": True, **trang_thai()}
