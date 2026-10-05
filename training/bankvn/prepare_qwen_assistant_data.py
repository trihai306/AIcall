#!/usr/bin/env python3
"""Build a conservative assistant-only SFT dataset for Qwen2.5-3B.

The historical teacher file also contains router/tool examples and volatile
product facts.  This cleaner deliberately keeps less data so a 24/7 job cannot
teach a customer-facing model to invent balances, rates, limits, or secrets.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
import re
import sys
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from training.bankvn.common import has_cjk_hangul, is_strict_vietnamese  # noqa: E402


SAFE_SYSTEM = (
    "Bạn là trợ lý ngân hàng Việt Nam. Trả lời ngắn gọn, rõ ràng bằng tiếng Việt. "
    "Không tự bịa lãi suất, hạn mức, phí, số dư, dư nợ, trạng thái hồ sơ hoặc dữ "
    "liệu cá nhân. Khi thiếu dữ liệu cập nhật, hãy hướng dẫn khách kiểm tra trên "
    "ứng dụng, tổng đài, chi nhánh hoặc kênh chính thức. Không bao giờ yêu cầu mật "
    "khẩu, mã OTP, mã CVV hoặc toàn bộ số thẻ."
)

VOLATILE_TERMS = (
    "lãi suất", "hạn mức", "phí", "dư nợ", "số dư", "tỷ giá",
    "phê duyệt", "giải ngân", "thời gian xử lý", "thời gian duyệt",
)
SAFETY_CUES = (
    "tùy", "phụ thuộc", "cập nhật", "kiểm tra", "liên hệ", "tham khảo",
    "chính thức", "tổng đài", "chi nhánh", "ứng dụng", "không thể truy cập",
    "không có quyền truy cập", "chưa có thông tin", "cần thẩm định",
)
SECRET_TERMS = r"(?:mật khẩu|mã\s*otp|otp|mã\s*cvv|cvv|toàn bộ số thẻ|mã pin|pin)"
SECRET_REQUEST = re.compile(
    rf"(?:vui lòng|hãy|cần|phải|bạn có thể)[^.!?\n]{{0,80}}"
    rf"(?:cung cấp|cho biết|đọc|nhập|gửi|chụp)[^.!?\n]{{0,80}}{SECRET_TERMS}",
    re.IGNORECASE,
)
PERSONAL_CLAIM = re.compile(
    r"(?:dư nợ|số dư|hạn mức|hồ sơ|khoản vay|thẻ)\s+(?:hiện tại\s+)?của bạn\s+"
    r"(?:là|đang|đã)",
    re.IGNORECASE,
)


def _fold(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def validate_record(obj: dict) -> tuple[dict | None, str]:
    if obj.get("mode") != "assistant":
        return None, "not_assistant_mode"
    messages = obj.get("messages")
    if not isinstance(messages, list) or len(messages) < 2:
        return None, "messages_invalid"
    if any(isinstance(item, dict) and item.get("tool_calls") for item in messages):
        return None, "contains_tool_call"

    user = next((
        str(item.get("content") or "").strip()
        for item in reversed(messages)
        if isinstance(item, dict) and item.get("role") == "user"
    ), "")
    answer = next((
        str(item.get("content") or "").strip()
        for item in reversed(messages)
        if isinstance(item, dict) and item.get("role") == "assistant"
    ), "")
    if not 8 <= len(user) <= 600:
        return None, "user_length"
    if not 8 <= len(answer) <= 800:
        return None, "answer_length"
    if has_cjk_hangul(user) or has_cjk_hangul(answer):
        return None, "foreign_script"
    if not is_strict_vietnamese(user, min_score=0.20, min_chars=8):
        return None, "user_not_vietnamese"
    if not is_strict_vietnamese(answer, min_score=0.24, min_chars=8):
        return None, "answer_not_vietnamese"

    # Exact numbers in an answer are the largest source of fabricated product
    # facts found in the old teacher set.  Questions may still contain numbers.
    if re.search(r"\d", answer):
        return None, "answer_has_digits"
    if SECRET_REQUEST.search(_fold(answer)):
        return None, "requests_secret"
    if PERSONAL_CLAIM.search(_fold(answer)):
        return None, "claims_personal_data"

    folded_answer = _fold(answer)
    if any(term in folded_answer for term in VOLATILE_TERMS):
        if not any(cue in folded_answer for cue in SAFETY_CUES):
            return None, "volatile_fact_without_safety_cue"

    cleaned = {
        "messages": [
            {"role": "system", "content": SAFE_SYSTEM},
            {"role": "user", "content": user},
            {"role": "assistant", "content": answer},
        ],
        "mode": "assistant",
        "teacher": obj.get("teacher"),
        "source": obj.get("source"),
        "source_id": obj.get("source_id"),
        "safety_filter": "qwen-assistant-v1",
    }
    return cleaned, "ok"


def build_dataset(inputs: list[Path], output: Path) -> dict:
    reasons: Counter[str] = Counter()
    kept: list[dict] = []
    seen: set[tuple[str, str]] = set()
    total = invalid_json = 0
    for path in inputs:
        if not path.exists():
            continue
        with path.open(encoding="utf-8", errors="ignore") as src:
            for line in src:
                if not line.strip():
                    continue
                total += 1
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    invalid_json += 1
                    continue
                cleaned, reason = validate_record(obj)
                if cleaned is None:
                    reasons[reason] += 1
                    continue
                key = (
                    _fold(cleaned["messages"][-2]["content"]),
                    _fold(cleaned["messages"][-1]["content"]),
                )
                if key in seen:
                    reasons["duplicate"] += 1
                    continue
                seen.add(key)
                kept.append(cleaned)

    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(output.name + f".{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as dst:
        for row in kept:
            dst.write(json.dumps(row, ensure_ascii=False) + "\n")
        dst.flush()
        os.fsync(dst.fileno())
    os.replace(tmp, output)
    return {
        "inputs": [str(path) for path in inputs],
        "output": str(output),
        "total": total,
        "kept": len(kept),
        "rejected": total - len(kept),
        "invalid_json": invalid_json,
        "reasons": dict(reasons),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Lọc dữ liệu assistant an toàn cho Qwen2.5-3B")
    parser.add_argument("inputs", nargs="+")
    parser.add_argument("--output", required=True)
    parser.add_argument("--stats", default="")
    args = parser.parse_args()
    result = build_dataset(
        [Path(value) if Path(value).is_absolute() else ROOT / value for value in args.inputs],
        Path(args.output) if Path(args.output).is_absolute() else ROOT / args.output,
    )
    if args.stats:
        stats = Path(args.stats) if Path(args.stats).is_absolute() else ROOT / args.stats
        stats.parent.mkdir(parents=True, exist_ok=True)
        stats.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
