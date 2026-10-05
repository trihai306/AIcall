"""Trả lời tức thì các câu Shinhan đã đối chiếu và có đáp án cố định.

Matcher chỉ nhận ý đơn rõ ràng. Tài liệu Markdown là bản gốc; nếu người dùng
sửa file, SHA-256 không còn khớp chỉ mục JSON thì ngừng trả lời nhanh và nhường
cho đường RAG. Không đọc dữ liệu train khi đang phục vụ khách.
"""

import hashlib
import json
import re
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2] / "knowledge" / "shinhan"
INDEX = ROOT / "fast_answers.json"


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", (text or "").casefold())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text)).strip()


def _intents(query: str) -> list[str]:
    q = _normalize(query)
    if not q or len(q.split()) > 24:
        return []
    both_digital_steps = ("dang ky" in q and "kich hoat" in q
                          and ("the dien tu" in q or "the ao" in q))
    if " va " in f" {q} " and not both_digital_steps:
        return []

    # Trạng thái thẻ/cá nhân, câu ghép và yêu cầu số liệu cần tra thêm nguồn.
    if any(re.search(pattern, q) for pattern in (
        r"\b(da|dang) (kich hoat|khoa|dang ky)\b",
        r"\b(trang thai|cua toi da|tai khoan cua toi|sao ke|lai suat|phi|bao nhieu tien)\b",
        r"\b(dong thoi|ngoai ra|ngan hang khac|the khac|khong phai shinhan)\b",
        r"\b(the ghi no|debit)\b",
    )):
        return []

    found = []
    if ("the" in q.split() and "kich hoat" in q
            and "the dien tu" not in q and "the ao" not in q):
        found.append("activate_card")
    if re.search(r"\b(mat the|roi the|that lac the)\b", q):
        found.append("lost_card")
    if (re.search(r"\b(dang ky|mo)\b", q)
            and ("the dien tu" in q or "the ao" in q)
            and "kich hoat" not in q):
        found.append("register_digital_card")
    if ("kich hoat" in q and ("the dien tu" in q or "the ao" in q)
            and ("dang ky" not in q or "sau khi dang ky" in q)):
        found.append("activate_digital_card")
    if both_digital_steps and " va " in f" {q} ":
        found.append("register_and_activate_digital_card")
    return found


def dap_an_da_xac_minh() -> dict[str, str]:
    """Chỉ lấy đáp án có tài liệu nguồn vẫn trùng vân tay của chỉ mục."""
    valid = {}
    try:
        data = json.loads(INDEX.read_text(encoding="utf-8"))
        if data.get("version") != 1:
            return {}
        for row in data["entries"]:
            source = ROOT / row["source_file"]
            if source.parent != ROOT:
                continue
            if hashlib.sha256(source.read_bytes()).hexdigest() == row["source_file_sha256"]:
                valid[row["id"]] = row["answer"]
    except (OSError, ValueError, KeyError, TypeError):
        return {}
    return valid


def tra_loi_nhanh(text: str, *, bank: str = "") -> tuple[str, str] | None:
    """Trả (fact_id, đáp án) khi một ý chắc chắn khớp nguồn còn nguyên vẹn."""
    q = _normalize(text)
    org = _normalize(bank)
    if "shinhan" not in q and "shinhan" not in org:
        return None
    if re.search(r"\b(khong phai|khong la) shinhan\b", q):
        return None

    # Trạng thái thẻ RIÊNG không nằm trong tài liệu chung. Qwen từng trả
    # "Chưa ạ" cho câu này dù không có dữ liệu cá nhân; chặn trước khi gọi LLM.
    is_status = bool(
        len(q.split()) <= 24
        and re.search(r"\bthe\b", q)
        and re.search(r"\b(kich hoat (hay )?chua|da kich hoat.{0,24}chua|trang thai kich hoat)\b", q)
        and not re.search(r"\b(dong thoi|ngoai ra|sao ke|lai suat|muc phi|dang ky the dien tu)\b", q)
        and " va " not in f" {q} "
    )
    is_digital = "the dien tu" in q or "the ao" in q
    asks_fee = bool(re.search(r"\bphi\b", q))
    asks_comparison = bool(re.search(r"\b(the vat ly|the that|so sanh)\b", q))
    if (asks_fee or asks_comparison) and "kich hoat" in q and "chua" in q:
        return None
    mixed_other_scope = bool(re.search(
        r"\b(ngan hang khac|the ghi no|dong thoi|ngoai ra|sao ke)\b", q))
    if is_digital and (asks_fee or asks_comparison) and not (is_status or mixed_other_scope):
        # Hai mục thẻ điện tử đã duyệt chỉ nói cách đăng ký/kích hoạt. Không
        # để Qwen tự suy ra phí hoặc tính năng tương đương thẻ vật lý.
        suffix = ("fee_comparison_unknown" if asks_fee and asks_comparison else
                  "fee_unknown" if asks_fee else "comparison_unknown")
        ids = [f"digital_card_{suffix}"]
    else:
        ids = ["activation_status_unknown"] if is_status else _intents(q)
    if len(ids) != 1:
        return None
    answer = dap_an_da_xac_minh().get(ids[0])
    return (ids[0], answer) if answer else None
