"""Quarantined 9B fact proposals from official Shinhan PDF text.

Exact source quotes are checked mechanically. Proposed facts are NEVER added
to verified fact cards or SFT without a separate source/currentness review.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXTERNAL = ROOT / "data/external/shinhan"
PRIORITY = {"card_user_guide_vi": 0, "digital_card_guide": 1,
            "consumer_credit_terms_2025": 2, "general_terms_v18": 3,
            "remittance_terms_2025": 4, "loan_household_terms": 5}


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def chunks_from_text(text: str, limit: int = 1800) -> list[str]:
    pieces = []
    for paragraph in re.split(r"\n\s*\n|\f", text):
        paragraph = compact(paragraph)
        if len(paragraph) < 80:
            continue
        pieces.extend(paragraph[i:i + limit] for i in range(0, len(paragraph), limit))
    chunks, current = [], ""
    for piece in pieces:
        if current and len(current) + len(piece) + 1 > limit:
            chunks.append(current)
            current = ""
        current = (current + " " + piece).strip()
    if len(current) >= 80:
        chunks.append(current)
    return chunks


def load_chunks() -> list[tuple[str, str, str, str]]:
    manifest = json.loads((EXTERNAL / "manifest.json").read_text(encoding="utf-8"))
    eligible = [x for x in manifest if x.get("status") == "downloaded"
                and x.get("use") == "review"
                and x.get("category") in {"account", "card", "loan", "transfer"}]
    eligible.sort(key=lambda x: (PRIORITY.get(x["name"], 10), x["name"]))
    result = []
    for source in eligible:
        path = EXTERNAL / "text" / (source["name"] + ".txt")
        if not path.exists():
            continue
        for chunk in chunks_from_text(path.read_text(encoding="utf-8", errors="replace")):
            key = hashlib.sha256((source["sha256"] + chunk).encode()).hexdigest()
            result.append((key, source["name"], source["sha256"], chunk))
    return result


def ensure_tables(db: sqlite3.Connection) -> None:
    db.execute("CREATE TABLE IF NOT EXISTS mining_chunks ("
               "chunk_id TEXT PRIMARY KEY, source TEXT NOT NULL, attempts INTEGER NOT NULL, "
               "status TEXT NOT NULL, updated_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    db.execute("CREATE TABLE IF NOT EXISTS fact_candidates ("
               "id INTEGER PRIMARY KEY, chunk_id TEXT NOT NULL, source TEXT NOT NULL, "
               "source_sha256 TEXT NOT NULL, quote TEXT NOT NULL, fact TEXT NOT NULL, "
               "answer TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending_source_review', "
               "UNIQUE(source_sha256,quote))")
    db.commit()


def next_chunk(db: sqlite3.Connection, chunks: list[tuple[str, str, str, str]]):
    state = {row[0]: (row[1], row[2]) for row in db.execute(
        "SELECT chunk_id,attempts,status FROM mining_chunks")}
    for row in chunks:
        attempts, status = state.get(row[0], (0, "new"))
        if status != "done" and attempts < 3:
            return row
    return None


def valid_proposal(item: dict, chunk: str) -> bool:
    if not isinstance(item, dict):
        return False
    quote, fact, answer = (compact(str(item.get(k, ""))) for k in
                           ("quote", "fact", "answer"))
    if not 35 <= len(quote) <= 320 or quote not in chunk:
        return False
    if not 20 <= len(fact) <= 280 or not 20 <= len(answer) <= 300:
        return False
    if re.search(r"\d|%|VNĐ|VND|lãi suất|biểu phí|khuyến mãi|ưu đãi|"
                 r"chắc chắn được duyệt|cam kết duyệt", fact + " " + answer, re.I):
        return False
    return True


def mine_one(db: sqlite3.Connection, chunks: list[tuple[str, str, str, str]],
             ollama_url: str, allowed, busy_exception) -> int | None:
    """Return accepted proposal count, or None when all safe chunks are exhausted."""
    row = next_chunk(db, chunks)
    if row is None:
        return None
    chunk_id, source, source_sha, chunk = row
    prompt = (
        "Đọc một đoạn trích điều khoản/hướng dẫn của Shinhan Bank Việt Nam. "
        "Đề xuất tối đa 2 ý nghiệp vụ ổn định, hữu ích khi khách hỏi; "
        "không lấy lãi suất, biểu phí, hạn mức, ngày tháng, khuyến mãi hay "
        "điều kiện duyệt vay. Mỗi ý phải có quote là TRÍCH DẪN NGUYÊN VĂN "
        "LIỀN MẠCH trong đoạn, fact tiếng Việt ngắn và answer tư vấn viên "
        "trả lời tự nhiên chỉ theo quote. Nếu không có ý an toàn, trả mảng rỗng. "
        'Trả JSON {"facts":[{"quote":"...","fact":"...","answer":"..."}]}.\n'
        "ĐOẠN NGUỒN:\n" + chunk
    )
    body = {"model": "qwen3.5:9b", "messages": [
        {"role": "system", "content": "Chỉ trích xuất ý có bằng chứng nguyên văn; không suy đoán."},
        {"role": "user", "content": prompt}], "stream": True, "think": False,
        "format": "json", "keep_alive": -1,
        "options": {"temperature": 0.2, "num_ctx": 4096, "num_predict": 850}}
    request = urllib.request.Request(ollama_url.rstrip("/") + "/api/chat",
                                     data=json.dumps(body, ensure_ascii=False).encode(),
                                     headers={"Content-Type": "application/json"})
    db.execute("INSERT INTO mining_chunks(chunk_id,source,attempts,status) "
               "VALUES (?,?,1,'retry') ON CONFLICT(chunk_id) DO UPDATE SET "
               "attempts=attempts+1, updated_utc=CURRENT_TIMESTAMP", (chunk_id, source))
    db.commit()
    fragments = []
    try:
        next_check = time.monotonic()
        with urllib.request.urlopen(request, timeout=120) as response:
            for line in response:
                if time.monotonic() >= next_check:
                    if not allowed():
                        raise busy_exception("backend or GPU busy; mining cancelled")
                    next_check = time.monotonic() + 0.3
                if line.strip():
                    fragments.append((json.loads(line).get("message") or {}).get("content") or "")
        proposals = json.loads("".join(fragments) or "{}").get("facts", [])
        if not isinstance(proposals, list):
            raise ValueError("mining output is not a list")
    except Exception:
        db.commit()
        raise
    count = 0
    for item in proposals[:2]:
        if not valid_proposal(item, chunk):
            continue
        try:
            db.execute("INSERT INTO fact_candidates(chunk_id,source,source_sha256,quote,fact,answer) "
                       "VALUES (?,?,?,?,?,?)",
                       (chunk_id, source, source_sha, compact(item["quote"]),
                        compact(item["fact"]), compact(item["answer"])))
            count += 1
        except sqlite3.IntegrityError:
            pass
    db.execute("UPDATE mining_chunks SET status='done',updated_utc=CURRENT_TIMESTAMP "
               "WHERE chunk_id=?", (chunk_id,))
    db.commit()
    print(f"mine {source}: {count}/{len(proposals[:2])} source-quoted candidates", flush=True)
    return count
