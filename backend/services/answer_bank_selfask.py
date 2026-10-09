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
import dataclasses
import hashlib
import json
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


# Tài liệu dài hơn mức này thì KHÔNG nhét trọn vào prompt soạn đáp án.
_TRON_TAI_LIEU_TOI_DA = 6000


async def _soan_dap_an(doc: learning.Document, cau_hoi: list[str], variants: int,
                       stage: str) -> tuple[list[dict], dict]:
    """Soạn đáp án có căn cứ cho các câu đã đặt.

    `generate_document` đưa TRỌN tài liệu vào prompt cho mỗi nhóm 8 câu. Với tài
    liệu 21.000 ký tự (`nghiep_vu_co_ban_va_loi_thoai.md`) prompt vượt ngữ cảnh
    của Qwen và nó trả lời không ra JSON - hỏng cả tài liệu, 2/2 lần chạy
    07-10-2026. Tài liệu dài thì mỗi nhóm 8 câu chỉ nhận các mảnh gần nó nhất;
    trích dẫn vẫn phải có nguyên văn trong các mảnh đó, tức là trong tài liệu.
    Một nhóm hỏng không kéo theo các nhóm khác.
    """
    if len(doc.text) <= _TRON_TAI_LIEU_TOI_DA:
        return await learning.generate_document(doc, len(cau_hoi), variants, cau_hoi,
                                                stage_key=stage)
    manh = [c for c in learning.cat_manh(doc.text) if c.strip()]
    items: list[dict] = []
    reasons: dict = {}
    da_co: set[str] = set()
    for start in range(0, len(cau_hoi), 8):
        nhom = cau_hoi[start:start + 8]
        hep = dataclasses.replace(doc, text="\n\n".join(qa._chon_manh(nhom, manh, 8)))
        try:
            moi, ly_do = await learning.generate_document(
                hep, len(nhom), variants, nhom, stage_key=f"{stage}:{start}")
        except (learning.PausedForCustomer, learning.BuildCancelled):
            raise
        except Exception as exc:
            ly_do, moi = {f"nhóm câu hỏi lỗi {type(exc).__name__}": len(nhom)}, []
        for why, count in ly_do.items():
            reasons[why] = reasons.get(why, 0) + count
        for item in moi:
            key = qa._khong_dau(item["tra_loi"])
            if key not in da_co:
                da_co.add(key)
                items.append(item)
    return items, reasons


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
        items, reasons = await _soan_dap_an(doc, cau_hoi, cfg["variants_per_answer"], stage)
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
        with learning.db.write_lock, conn:  # bản lưu tạm của lượt này hết tác dụng
            conn.execute("DELETE FROM answer_bank_staging WHERE source_path=? AND stage_key LIKE 'tuhoi:%'",
                         (doc.rel,))
        thieu = [q for q in cau_hoi if qa._khong_dau(q) not in co_dap_an]
        san_pham = doc.stem if doc.group == "products" else ""
        for q in thieu:
            gaps.ghi_thieu_tu_hoi(q, san_pham)
        _ghi(f"{doc.rel}: hỏi {len(cau_hoi)} câu mới, soạn được {len(ids)} đáp án có căn cứ (chờ duyệt), "
             f"{len(thieu)} câu tài liệu không trả lời được" + (f" ({reasons})" if reasons else ""))
        return ids, len(thieu)


# ── Hai vai Qwen đối thoại với nhau ──────────────────────────────────────
#
# Cùng một mô hình, hai lời nhắc, hai bộ luật. KHÁCH hỏi theo vai và theo mạch
# cuộc nói chuyện (hỏi tiếp, vặn lại, kể hoàn cảnh) nên ra những câu mà cách
# "liệt kê 40 câu hỏi" không nghĩ tới. TƯ VẤN VIÊN chỉ được nói điều tài liệu
# có, và phải chép nguyên văn câu làm căn cứ. Trọng tài KHÔNG phải mô hình: là
# các luật bằng mã bên dưới - Qwen làm giám khảo hỏi-đáp không tin được.

VAI_KHACH = (
    ("người đi làm công ăn lương, hỏi kỹ từng khoản", "lãi suất, phí, số tiền trả mỗi tháng"),
    ("người làm nghề tự do, thu nhập không đều", "điều kiện, cách chứng minh thu nhập, hồ sơ"),
    ("người lớn tuổi, cẩn thận, sợ bị lừa", "độ tin cậy, bảo mật, thủ tục có phức tạp không"),
    ("người đang vội, muốn biết ngay có làm được không", "thời gian xử lý, cần chuẩn bị gì, đăng ký ở đâu"),
    ("người đã dùng sản phẩm tương tự ở ngân hàng khác", "so sánh, ưu đãi, điểm khác biệt, phí phạt"),
    ("người chưa từng vay hay dùng thẻ, cái gì cũng lạ", "khái niệm cơ bản, rủi ro, trả chậm thì sao"),
)

LUAT_KHACH = """LUẬT CỦA KHÁCH:
- Mỗi lượt nói ĐÚNG MỘT câu hỏi, lời nói miệng, dưới 25 từ, xưng anh/chị, gọi tư vấn viên là em.
- Câu hỏi phải TỰ ĐỦ NGHĨA: nêu rõ đang hỏi về cái gì, không dùng "cái đó", "thế còn", "vậy thì sao".
- Không hỏi lại ý đã hỏi. Không hỏi về hồ sơ, số dư hay kết quả duyệt của riêng mình.
- Không tự nêu con số, không kể tên, số điện thoại, địa chỉ.
- Chỉ viết câu hỏi, không viết gì khác."""

LUAT_TU_VAN = """LUẬT CỦA TƯ VẤN VIÊN:
- CHỈ dùng dữ kiện có trong TÀI LIỆU. Không thêm, không đổi, không ước lượng con số nào.
- Tài liệu không trả lời được câu hỏi thì viết đúng một chữ: KHONG_CO
- Trả lời THẲNG vào câu hỏi, 1-2 câu, tối đa 30 từ, mở đầu "Dạ", xưng em, gọi anh chị, kết thúc "ạ".
- Không nói "xem trong tài liệu", không hứa hẹn, không xin lỗi.
- Viết đúng một dòng theo mẫu:  <câu trả lời> ||| <một câu CHÉP NGUYÊN VĂN từ tài liệu chứng minh câu trả lời>"""


def _nguon_cho(doc: learning.Document, cau_hoi: str) -> str:
    if len(doc.text) <= _TRON_TAI_LIEU_TOI_DA:
        return doc.text
    manh = [c for c in learning.cat_manh(doc.text) if c.strip()]
    return "\n\n".join(qa._chon_manh([cau_hoi], manh, 8))


async def _noi(prompt: str, predict: int = 500) -> str:
    return await learning._guarded(learning._chat(prompt, predict),
                                   learning.settings.answer_bank_llm_timeout_s)


def _cham_luot(cau_hoi: str, tho: str, nguon: str) -> tuple[dict | None, str]:
    """Trọng tài bằng luật: trả (đáp án đạt, "") hoặc (None, lý do loại)."""
    from backend.services.answer_bank_selector import _is_follow_up
    if "KHONG_CO" in tho.upper().replace(" ", "_"):
        return None, "tài liệu không có"
    tra_loi, _, can_cu = tho.partition("|||")
    tra_loi = learning._normal(tra_loi).strip(" \"'“”")
    tra_loi = re.sub(r"\s*[.,]\s*ạ\.?$", " ạ.", tra_loi)
    can_cu = learning._normal(can_cu).strip(" \"'“”<>")
    if not tra_loi or not can_cu:
        return None, "sai mẫu trả lời"
    if _is_follow_up(cau_hoi) or len(learning._question_key(cau_hoi)) < 3:
        return None, "câu hỏi không tự đủ nghĩa"
    if not learning._evidence_in_source(can_cu, nguon):
        return None, "căn cứ không có nguyên văn trong tài liệu"
    if learning._qualitative_contradiction(tra_loi, can_cu):
        return None, "trả lời đảo nghĩa căn cứ"
    if learning._REFUSAL.search(tra_loi) or _NE_TRANH.search(tra_loi):
        return None, "trả lời né tránh"
    if learning._FILLER_THUC_HIEN.search(tra_loi):
        return None, "chèn cụm đệm"
    if len(tra_loi.split()) > 35:
        return None, "trả lời quá 35 từ"
    ok, why = qa.loc_cap(tra_loi, tra_loi, nguon)
    if not ok:
        return None, why
    item = {"cau_hoi": [cau_hoi], "tra_loi": tra_loi, "evidence": can_cu}
    if learning._lac_chu_de(item, cau_hoi):
        return None, "trả lời lệch chủ đề câu hỏi"
    return item, ""


async def _mot_cuoc(doc: learning.Document, vai: tuple[str, str], so_luot: int,
                    known: dict, ghi_lai: list) -> tuple[list[dict], list[str], dict]:
    """Một cuộc đối thoại khách - tư vấn viên. Trả (đáp án đạt, câu thiếu, lý do loại)."""
    chu_de = f"{doc.stem.replace('_', ' ')} - {learning._doc_profile(doc)}"
    lich_su: list[tuple[str, str]] = []
    dat, thieu, ly_do = [], [], {}
    for _ in range(so_luot):
        da_hoi = "\n".join(f"KHÁCH: {q}\nTƯ VẤN VIÊN: {a}" for q, a in lich_su[-6:]) or "(chưa nói gì)"
        cau_hoi = await _noi(
            f"Bạn đóng vai KHÁCH HÀNG trong cuộc gọi tư vấn của ngân hàng.\n"
            f"Bạn là: {vai[0]}. Bạn quan tâm nhất: {vai[1]}.\n"
            f"Chủ đề cuộc gọi: {chu_de}\n{LUAT_KHACH}\n\nCUỘC NÓI CHUYỆN ĐẾN GIỜ:\n{da_hoi}\n\n"
            f"Câu hỏi tiếp theo của khách:", 200)
        cau_hoi = learning.sanitize_history(learning._normal(cau_hoi)).strip(" \"'“”-")
        cau_hoi = re.sub(r"^(?:KHÁCH|Khách)\s*[:：]\s*", "", cau_hoi)[:200]
        if len(cau_hoi.split()) < 3:
            break
        nguon = _nguon_cho(doc, cau_hoi)
        tho = await _noi(
            f"Bạn là TƯ VẤN VIÊN ngân hàng đang nghe điện thoại.\n{LUAT_TU_VAN}\n\n"
            f"TÀI LIỆU:\n<<<\n{nguon}\n>>>\n\nKHÁCH HỎI: {cau_hoi}\nTƯ VẤN VIÊN:", 400)
        item, why = _cham_luot(cau_hoi, tho, nguon)
        key = learning._question_key(cau_hoi)
        if item is not None and known.get(key):
            item, why = None, "kho đã có câu hỏi này"
        ghi_lai.append({"tai_lieu": doc.rel, "vai": vai[0], "khach": cau_hoi, "tu_van": tho,
                        "dat": item is not None, "ly_do": why})
        if item is not None:
            known[key] = 1
            dat.append(item)
            lich_su.append((cau_hoi, item["tra_loi"]))
        else:
            ly_do[why] = ly_do.get(why, 0) + 1
            if why == "tài liệu không có":
                thieu.append(cau_hoi)
            # Khách vẫn cần nghe một câu để hỏi tiếp cho tự nhiên; câu này KHÔNG được lưu.
            lich_su.append((cau_hoi, "Dạ phần này em xin ghi nhận để bên em liên hệ hỗ trợ sau ạ."))
        await asyncio.sleep(0)
    return dat, thieu, ly_do


async def _doi_thoai_mot_tai_lieu(doc: learning.Document, so_luot: int) -> tuple[list[str], int]:
    async with learning.source_operation_lock(doc):
        if not learning._source_is_current(doc):
            _ghi(f"{doc.rel}: tài liệu vừa đổi, bỏ qua")
            return [], 0
        known = learning._known_question_keys(doc)
        for q in gaps.cau_hoi_cho_duyet():
            known[learning._question_key(q)] = 1
        ghi_lai: list[dict] = []
        dat, thieu, ly_do = [], [], {}
        for vai in VAI_KHACH:
            d, t, l = await _mot_cuoc(doc, vai, so_luot, known, ghi_lai)
            dat += d
            thieu += t
            for why, n in l.items():
                ly_do[why] = ly_do.get(why, 0) + n
        da_co: set[str] = set()
        items = []
        for item in dat:  # hai vai khác nhau có thể dẫn tới cùng một câu trả lời
            k = qa._khong_dau(item["tra_loi"])
            prior = next((x for x in items if qa._khong_dau(x["tra_loi"]) == k), None)
            if prior is not None:
                prior["cau_hoi"] += [q for q in item["cau_hoi"] if q not in prior["cau_hoi"]]
            elif k not in da_co:
                da_co.add(k)
                items.append(item)
        conn = learning._conn()
        items = [item for item in items if not conn.execute(
            "SELECT 1 FROM hoi_dap WHERE id=? AND bat=1",
            (learning._id_for(doc, item, "memory"),)).fetchone()]
        ids = learning._store_items(doc, items, "memory", replace=False) if items else []
        gaps.cho_duyet(ids)
        san_pham = doc.stem if doc.group == "products" else ""
        for q in thieu:
            gaps.ghi_thieu_tu_hoi(q, san_pham)
        _luu_doi_thoai(doc, ghi_lai)
        _ghi(f"{doc.rel}: {len(VAI_KHACH)} cuộc đối thoại, {len(ghi_lai)} lượt hỏi, "
             f"{len(ids)} đáp án đạt (chờ duyệt), {len(thieu)} câu tài liệu không có"
             + (f" ({ly_do})" if ly_do else ""))
        return ids, len(thieu)


def _luu_doi_thoai(doc: learning.Document, ghi_lai: list[dict]) -> None:
    """Giữ nguyên bản mọi lượt (cả lượt bị loại và lý do) để soát và làm dữ liệu."""
    import json
    from pathlib import Path
    try:
        thu_muc = Path("data") / "tu_thoai"
        thu_muc.mkdir(parents=True, exist_ok=True)
        ten = time.strftime("%Y%m%d_%H%M%S_") + doc.stem + ".jsonl"
        with open(thu_muc / ten, "w", encoding="utf-8") as f:
            for dong in ghi_lai:
                f.write(json.dumps(dong, ensure_ascii=False) + "\n")
    except Exception:
        logger.exception("Không lưu được bản ghi đối thoại")


# ── Hai vai Qwen nói chuyện ĐỜI THƯỜNG (không thuộc tài liệu sản phẩm nào) ──
#
# Khách thật không chỉ hỏi sản phẩm: họ kể chuyện, than thở, đùa, bực chuyện
# khác, hỏi thăm. Những câu đó không có tài liệu nào để trích, nên luật khác hẳn
# chế độ trên: tư vấn viên KHÔNG được nói dữ kiện nào cả - không con số, không
# điều kiện, không lời hứa - chỉ đáp như một người lịch sự rồi đưa câu chuyện về
# việc hỗ trợ. Trọng tài vẫn là luật bằng mã.

TAI_LIEU_GIAO_TIEP_AI = "faq/giao_tiep_ai_soan"

# (nhóm tình huống, cảnh cụ thể để vai khách nhập vai)
CANH_DOI_THUONG = (
    ("Xã giao", "khách hỏi thăm lại tư vấn viên: sức khoẻ, công việc, ăn uống, thời tiết"),
    ("Xã giao", "khách vui tính, hay đùa, trêu tư vấn viên"),
    ("Xã giao", "khách khen giọng nói, khen cách tư vấn, hoặc cảm ơn nhiều lần"),
    ("Xã giao", "khách chúc tụng, nói chuyện ngày lễ, cuối tuần, cuối năm"),
    ("Khách kể chuyện", "khách kể chuyện gia đình: con cái, vợ chồng, cha mẹ già"),
    ("Khách kể chuyện", "khách than công việc vất vả, thu nhập bấp bênh, làm ăn khó"),
    ("Khách kể chuyện", "khách kể đang ốm, mệt, vừa đi viện về, đang có tang hoặc việc buồn"),
    ("Khách kể chuyện", "khách kể dự định: sửa nhà, cưới hỏi, cho con đi học, mua xe"),
    ("Khách kể chuyện", "khách kể chuyện từng bị lừa, từng vay nóng, từng khổ vì nợ"),
    ("Khách bận", "khách đang dở tay việc nhà, đang nấu cơm, đang trông cháu, đang ngoài đồng"),
    ("Khách bận", "khách đang ở chỗ đông người: đám cưới, bệnh viện, quán ăn, trên xe khách"),
    ("Khách bận", "khách sắp có việc, chỉ nghe được một lúc, hẹn khi khác"),
    ("Khách khó chịu", "khách đang bực chuyện khác rồi trút lên cuộc gọi"),
    ("Khách khó chịu", "khách cộc lốc, trả lời nhát gừng, tỏ ra không muốn nghe"),
    ("Khách khó chịu", "khách mỉa mai, nói kháy về ngân hàng và các cuộc gọi quảng cáo"),
    ("Khách phân vân", "khách lưỡng lự, nói vòng vo, chưa nói rõ có cần hay không"),
    ("Khách phân vân", "khách muốn nhưng sợ người nhà phản đối, sợ điều tiếng vay mượn"),
    ("Khách phân vân", "khách nói để tính, để xem, bao giờ cần sẽ hỏi"),
    ("Khách nghi ngờ", "khách dò hỏi tư vấn viên là ai, gọi từ đâu, có thật không"),
    ("Khách nghi ngờ", "khách nghe người quen dặn đừng tin cuộc gọi lạ nên đề phòng"),
    ("Trục trặc nghe nói", "khách nặng tai, nghe câu được câu mất, hỏi lại nhiều lần"),
    ("Trục trặc nghe nói", "khách nói giọng địa phương, nói nhanh, hay chen ngang"),
    ("Trục trặc nghe nói", "khách đang nói dở thì quay sang nói chuyện với người bên cạnh"),
    ("Khách muốn nghe tiếp", "khách tò mò, hỏi han chung chung, muốn nghe thêm nhưng chưa biết hỏi gì"),
    ("Khách muốn nghe tiếp", "khách nhờ nói lại cho người nhà nghe, hoặc đưa máy cho người khác"),
    ("Hỏi về cuộc gọi", "khách hỏi về chính tư vấn viên: tên, làm ở đâu, làm lâu chưa, làm tới mấy giờ"),
    ("Hỏi về cuộc gọi", "khách hỏi sao biết số, sao gọi đúng mình, gọi nhiều người không"),
    ("Kết thúc cuộc gọi", "khách muốn dừng cuộc gọi một cách lịch sự, chào, hẹn dịp khác"),
    ("Kết thúc cuộc gọi", "khách cúp ngang ý: bảo thôi, bảo bận, bảo không nghe nữa"),
    ("Mở đầu cuộc gọi", "khách vừa bắt máy: hỏi ai gọi, gọi có việc gì, đang ngái ngủ hoặc đang vội"),
)

LUAT_KHACH_DOI_THUONG = """LUẬT CỦA KHÁCH:
- Nói ĐÚNG MỘT câu như người thật nói qua điện thoại, lời nói miệng, dưới 20 từ.
- Xưng anh/chị/cô/chú/bác tuỳ vai, gọi tư vấn viên là em hoặc cháu.
- Mỗi lượt một ý KHÁC các lượt trước; có thể là câu kể, câu than, câu hỏi, câu đùa.
- Không hỏi lãi suất, phí, hạn mức, điều kiện hay thủ tục. Không nêu con số, tên riêng, số điện thoại.
- KHÔNG mở đầu bằng "Chào em". Vào thẳng điều muốn nói, mỗi lượt mở đầu một kiểu khác nhau.
- Khách là người LỚN TUỔI HƠN tư vấn viên: không bao giờ tự xưng "em" hay "cháu".
- Không nhắc tới điều tư vấn viên chưa hề nói ("gói em vừa nhắc", "như em nói").
- Chỉ viết đúng câu của khách, không viết gì khác."""

LUAT_TU_VAN_DOI_THUONG = """LUẬT CỦA TƯ VẤN VIÊN:
- Đáp như một người lịch sự, ấm áp, nói với người lớn hơn mình; 1-2 câu, tối đa 28 từ.
- Mở đầu "Dạ", xưng em, gọi "anh chị", kết thúc "ạ".
- TUYỆT ĐỐI không nêu con số, lãi suất, phí, hạn mức, điều kiện, thời hạn.
- Không hứa việc gì cụ thể (gọi lại đúng giờ, gửi tin nhắn, giảm lãi, duyệt hồ sơ). Cần thì chỉ nói "em xin ghi nhận".
- Không khuyên khách nên hay không nên vay. Không nói về bản thân ngoài việc là tư vấn viên của ngân hàng.
- Đáp đúng điều khách vừa nói trước, rồi nhẹ nhàng đưa về việc hỗ trợ hoặc chào nếu khách muốn dừng.
- Luôn gọi người nghe là "anh chị" (không gọi "khách hàng", "bác", "cháu"), luôn tự xưng "em".
- Không nói sẽ gọi lại, sẽ liên hệ lại, sẽ chờ máy bao lâu; không nói "cung cấp thông tin chi tiết".
- Chỉ viết đúng câu trả lời, không viết gì khác."""

# Lời khách lạc vai hoặc lạc đề: hỏi sản phẩm, tự xưng nhỏ tuổi, nhắc điều chưa ai nói.
_KHACH_LAC = re.compile(
    r"(?i)^chào em|gói vay|khoản vay|vay tiêu dùng|vay tín chấp|thẻ tín dụng|tiết kiệm|lãi|"
    r"em vừa (?:nhắc|nói)|như em nói|cháu (?:gọi|sẽ|xin|đang)|cho cháu|gọi (?:lại )?cho em")

_CAM_DOI_THUONG = re.compile(
    r"(?i)\d|%|phần trăm|lãi suất|hạn mức|kỳ hạn|giải ngân|phí |miễn phí|ưu đãi|khuyến mãi|"
    r"được duyệt|duyệt hồ sơ|đủ điều kiện|chắc chắn|cam kết|đảm bảo|em sẽ gọi|em sẽ gửi|"
    r"gửi tin nhắn|gửi zalo|gửi email|triệu|nghìn|tỷ|tháng nữa|ngày mai em|"
    r"anh chị nên vay|nên đăng ký ngay|"
    # sai vai, sai cách xưng hô, hoặc hứa việc hệ thống không tự làm
    r"khách hàng|anh chị cảm ơn|\bbác\b|\bcháu\b|\bcô\b|\bchú\b|em sẽ (?:liên hệ|gọi|chờ)|"
    r"liên hệ lại khi|gọi lại cho em|thông tin chi tiết|giải pháp|nhu cầu tài chính|"
    r"tài liệu|không có thông tin")


def _cham_doi_thuong(khach: str, tra_loi: str) -> tuple[dict | None, str]:
    tra_loi = learning._normal(tra_loi).strip(" \"'“”")
    tra_loi = re.sub(r"^(?:TƯ VẤN VIÊN|Tư vấn viên)\s*[:：]\s*", "", tra_loi)
    tra_loi = re.sub(r"\s*[.,]\s*ạ\.?$", " ạ.", tra_loi)
    if len(khach.split()) < 3 or re.search(r"\d", khach):
        return None, "lời khách quá ngắn hoặc có số"
    if _KHACH_LAC.search(khach):
        return None, "lời khách lạc vai hoặc hỏi sản phẩm"
    if not tra_loi.lower().startswith("dạ"):
        return None, "không mở đầu bằng Dạ"
    if not re.search(r"ạ[.!?]?$", tra_loi):
        return None, "không kết bằng ạ"
    if len(tra_loi.split()) > 32:
        return None, "trả lời quá dài"
    cam = _CAM_DOI_THUONG.search(tra_loi)
    if cam:
        return None, f"nêu dữ kiện hoặc lời hứa ({cam.group(0).strip()})"
    # KHÔNG dùng `_REFUSAL` ở đây: nó bắt cả "em xin lỗi", mà xin lỗi là câu đáp
    # đúng khi khách khó chịu (lượt thử đầu loại oan 15/108 lượt vì thế).
    if learning._FILLER_THUC_HIEN.search(tra_loi):
        return None, "chèn cụm đệm"
    return {"cau_hoi": [khach], "tra_loi": tra_loi, "evidence": ""}, ""


async def _doi_thuong(doc: learning.Document, so_luot: int) -> tuple[list[str], int]:
    """Chạy mọi cảnh đời thường; đáp án đạt vào hàng chờ duyệt, gắn nhóm tình huống."""
    async with learning.source_operation_lock(doc):
        from backend.services.answer_bank_selector import khoa_cau_hoi
        conn = learning._conn()
        da_co_cau = {khoa_cau_hoi(q) for q in gaps.cau_hoi_cho_duyet()}
        da_co_dap: set[str] = set()
        ghi_lai: list[dict] = []
        ids_tat_ca: list[str] = []
        ly_do: dict = {}
        for nhom, canh in CANH_DOI_THUONG:
            _trang_thai["tai_lieu"] = f"đời thường · {nhom}"
            lich_su: list[tuple[str, str]] = []
            items: list[dict] = []
            for _ in range(so_luot):
                da_noi = "\n".join(f"KHÁCH: {q}\nTƯ VẤN VIÊN: {a}" for q, a in lich_su[-5:]) or "(chưa nói gì)"
                khach = await _noi(
                    f"Bạn đóng vai KHÁCH HÀNG vừa nhận cuộc gọi tư vấn của ngân hàng.\n"
                    f"Cảnh: {canh}.\n{LUAT_KHACH_DOI_THUONG}\n\nĐÃ NÓI:\n{da_noi}\n\nCâu tiếp theo của khách:", 150)
                khach = learning._normal(khach).strip(" \"'“”-")
                khach = re.sub(r"^(?:KHÁCH|Khách)\s*[:：]\s*", "", khach)[:160]
                if learning.sanitize_history(khach) != khach or len(khach.split()) < 3:
                    continue
                tho = await _noi(
                    f"Bạn là TƯ VẤN VIÊN ngân hàng đang nói chuyện điện thoại với khách.\n"
                    f"{LUAT_TU_VAN_DOI_THUONG}\n\nĐÃ NÓI:\n{da_noi}\n\nKHÁCH: {khach}\nTƯ VẤN VIÊN:", 200)
                item, why = _cham_doi_thuong(khach, tho)
                key = khoa_cau_hoi(khach)
                if item is not None and (key in da_co_cau or qa._khong_dau(item["tra_loi"]) in da_co_dap):
                    item, why = None, "trùng câu đã có"
                ghi_lai.append({"nhom": nhom, "canh": canh, "khach": khach, "tu_van": tho,
                                "dat": item is not None, "ly_do": why})
                lich_su.append((khach, learning._normal(tho)[:200]))
                if item is None:
                    ly_do[why.split(" (")[0]] = ly_do.get(why.split(" (")[0], 0) + 1
                    continue
                da_co_cau.add(key)
                da_co_dap.add(qa._khong_dau(item["tra_loi"]))
                items.append(item)
                await asyncio.sleep(0)
            items = [i for i in items if not conn.execute(
                "SELECT 1 FROM hoi_dap WHERE id=?", (learning._id_for(doc, i, "memory"),)).fetchone()]
            if items:
                ids = learning._store_items(doc, items, "memory", replace=False)
                gaps.cho_duyet(ids)
                for answer_id in ids:
                    gaps.dat_nhom(answer_id, nhom)
                ids_tat_ca += ids
                _trang_thai["them"] += len(ids)
        _luu_doi_thoai(doc, ghi_lai)
        _ghi(f"Đời thường: {len(CANH_DOI_THUONG)} cảnh, {len(ghi_lai)} lượt, {len(ids_tat_ca)} đáp án đạt "
             f"(chờ duyệt)" + (f" ({ly_do})" if ly_do else ""))
        return ids_tat_ca, 0


async def nhap_doi_thuong(dong: list[dict]) -> dict:
    """Nhập hàng loạt câu giao tiếp đời thường soạn BÊN NGOÀI (người hoặc mô hình
    khác viết), qua đúng trọng tài của chế độ đời thường. Câu đạt vào hàng chờ
    duyệt, gắn nhóm tình huống. Mỗi dòng: {"nhom", "khach": [..], "tra_loi"}.
    """
    from backend.services.answer_bank_selector import khoa_cau_hoi
    docs, _logs = learning.prepare_sources()
    doc = next((d for d in docs if f"{d.group}/{d.stem}" == TAI_LIEU_GIAO_TIEP_AI), None)
    if doc is None:
        return {"ok": False, "error": "Chưa có tài liệu giữ chỗ " + TAI_LIEU_GIAO_TIEP_AI}
    async with learning.source_operation_lock(doc):
        conn = learning._conn()
        da_co_cau: set = set()
        da_co_dap: set[str] = set()
        for cau_hoi, tra_loi in conn.execute(
                "SELECT h.cau_hoi,h.tra_loi FROM hoi_dap h JOIN answer_bank_entries e "
                "ON e.hoi_dap_id=h.id WHERE e.source_path LIKE 'faq/giao_tiep%'").fetchall():
            da_co_dap.add(qa._khong_dau(tra_loi or ""))
            try:
                da_co_cau.update(khoa_cau_hoi(q) for q in json.loads(cau_hoi or "[]"))
            except ValueError:
                pass
        theo_nhom: dict[str, list[dict]] = {}
        ly_do: dict[str, int] = {}
        for d in dong:
            nhom = learning._normal(str(d.get("nhom") or ""))[:80]
            khach = [learning._normal(str(q)) for q in (d.get("khach") or []) if str(q).strip()]
            # Trọng tài chấm theo câu khách đầu tiên; các cách nói còn lại chỉ cần
            # qua luật về lời khách và không trùng câu đã có.
            item, why = _cham_doi_thuong(khach[0] if khach else "", str(d.get("tra_loi") or ""))
            if item is not None and qa._khong_dau(item["tra_loi"]) in da_co_dap:
                item, why = None, "trùng câu trả lời đã có"
            if item is not None:
                giu = []
                for q in khach:
                    key = khoa_cau_hoi(q)
                    if (len(q.split()) >= 3 and not re.search(r"\d", q) and not _KHACH_LAC.search(q)
                            and learning.sanitize_history(q) == q and key not in da_co_cau):
                        da_co_cau.add(key)
                        giu.append(q[:160])
                if not giu:
                    item, why = None, "trùng câu khách đã có"
                else:
                    item["cau_hoi"] = giu
            if item is None:
                ly_do[why.split(" (")[0]] = ly_do.get(why.split(" (")[0], 0) + 1
                continue
            da_co_dap.add(qa._khong_dau(item["tra_loi"]))
            theo_nhom.setdefault(nhom, []).append(item)
        ids_tat_ca: list[str] = []
        for nhom, items in theo_nhom.items():
            for start in range(0, len(items), 400):
                ids = learning._store_items(doc, items[start:start + 400], "memory", replace=False)
                gaps.cho_duyet(ids)
                for answer_id in ids:
                    gaps.dat_nhom(answer_id, nhom)
                ids_tat_ca += ids
                await asyncio.sleep(0)
        return {"ok": True, "nhan": len(dong), "dat": len(ids_tat_ca), "loai": ly_do, "ids": ids_tat_ca}


async def _chay(so_cau: int, chi_tai_lieu: str, kieu: str = "tu_hoi") -> None:
    worker = learning.AnswerBankLearning()
    worker._state = learning.bo_hoc_tra_loi._state
    token = qa._manual_bank_worker.set(worker)
    try:
        docs, _logs = learning.prepare_sources()
        if kieu == "doi_thuong":
            chi_tai_lieu = TAI_LIEU_GIAO_TIEP_AI
        if chi_tai_lieu:
            docs = [d for d in docs if d.rel == chi_tai_lieu or f"{d.group}/{d.stem}" == chi_tai_lieu]
        elif kieu != "doi_thuong":
            # Tài liệu giữ chỗ cho đáp án đời thường không có nội dung để hỏi.
            docs = [d for d in docs if f"{d.group}/{d.stem}" != TAI_LIEU_GIAO_TIEP_AI]
        cfg = learning._config()
        for doc in docs:
            _trang_thai["tai_lieu"] = doc.rel
            for lan in range(40):  # nhường cuộc gọi: chờ tối đa ~20 phút mỗi tài liệu
                try:
                    if kieu == "doi_thuong":
                        da_them = _trang_thai["them"]
                        ids, thieu = await _doi_thuong(doc, so_cau)
                        _trang_thai["them"] = da_them  # vòng ngoài sẽ cộng lại
                    elif kieu == "doi_thoai":
                        ids, thieu = await _doi_thoai_mot_tai_lieu(doc, so_cau)
                    else:
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


def bat_dau(so_cau: int = 40, chi_tai_lieu: str = "", kieu: str = "tu_hoi") -> dict:
    """Chạy nền một lượt. `kieu="tu_hoi"`: `so_cau` câu hỏi mới mỗi tài liệu.
    `kieu="doi_thoai"`: hai vai Qwen nói chuyện, `so_cau` lượt hỏi cho MỖI vai
    khách (có 6 vai) trên mỗi tài liệu."""
    global _viec
    if _trang_thai["dang_chay"]:
        return {"ok": False, "error": "Đang chạy một lượt tự hỏi rồi", **trang_thai()}
    _trang_thai.update(dang_chay=True, nhat_ky=[], them=0, thieu=0, tai_lieu="",
                       bat_dau=time.time(), ket_thuc=None, loi="")
    _viec = asyncio.get_running_loop().create_task(
        _chay(max(3, min(int(so_cau), 200)), chi_tai_lieu,
              kieu if kieu in ("doi_thoai", "doi_thuong") else "tu_hoi"), name="answer-bank-selfask")
    return {"ok": True, **trang_thai()}
