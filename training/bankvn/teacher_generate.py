#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import json
import random
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.pipeline.cong_cu_llm import DINH_NGHIA  # noqa: E402
if __package__:
    from .common import (clean_text, foreign_latin_ratio, has_cjk_hangul, is_strict_vietnamese,
                         iter_input_files, read_documents, redact_pii, stable_hash,
                         vietnamese_score)  # noqa: E402
    from .mine_banking_corpus import keyword_hits  # noqa: E402
else:
    from common import (clean_text, foreign_latin_ratio, has_cjk_hangul, is_strict_vietnamese,
                        iter_input_files, read_documents, redact_pii, stable_hash,
                        vietnamese_score)  # noqa: E402
    from mine_banking_corpus import keyword_hits  # noqa: E402


SYSTEM = """Bạn là giáo viên dữ liệu cho BankVN, một LLM ngân hàng chỉ giao tiếp bằng tiếng Việt.
Tạo đúng MỘT mẫu huấn luyện từ đoạn nguồn. Không bịa số liệu. Với lãi suất, hạn mức,
phí, dư nợ hoặc dữ liệu có thể thay đổi, ưu tiên yêu cầu gọi công cụ thay vì nhét số
vào câu trả lời. Không dùng dấu ba chấm, chuỗi rỗng hoặc placeholder cho trường user.
User phải là một câu hỏi tự nhiên bằng tiếng Việt, dài ít nhất 8 ký tự.
Ví dụ tool-call hợp lệ:
{"user":"Tôi muốn kiểm tra dư nợ hiện tại.","answer":"","tool_call":{"name":"tra_ho_so_khach","arguments":{}}}
Nếu không cần tool_call, đặt tool_call=null và viết answer đầy đủ bằng tiếng Việt dựa đúng nguồn.
Nếu tool_call là null thì answer BẮT BUỘC là câu trả lời tiếng Việt không rỗng.
Nếu dùng tool_call thì name BẮT BUỘC là đúng một tên trong danh sách công cụ đã cho.
Không dùng tiếng Anh làm câu tự nhiên; chỉ giữ nguyên thuật ngữ chuẩn như OTP/KYC/CIC/API/JSON.
Không dùng tiếng Trung, Hàn, Nhật. Câu người dùng phải tự nhiên như khách Việt Nam."""

SPEECH_PROFILES = (
    ("neutral_spoken", "toan_quoc", "hoi_thoai_tu_nhien", "Văn nói phổ thông tự nhiên như hội thoại thật."),
    ("north_casual", "bac", "doi_thuong", "Cách diễn đạt đời thường miền Bắc vừa phải, dễ hiểu toàn quốc."),
    ("central_casual", "trung", "doi_thuong", "Cách diễn đạt đời thường miền Trung vừa phải, không bịa tiếng địa phương."),
    ("south_casual", "nam", "doi_thuong", "Cách diễn đạt đời thường miền Nam tự nhiên, không cường điệu phương ngữ."),
    ("chat_short", "toan_quoc", "chat_viet_tat", "Giống tin nhắn thật, có thể viết tắt tiếng Việt phổ biến nhưng ý phải rõ."),
    ("young_customer", "toan_quoc", "tre_than_mat", "Cách hỏi thân mật, gọn, tự nhiên của người trẻ Việt Nam."),
    ("older_customer", "toan_quoc", "lon_tuoi", "Cách nói của khách lớn tuổi, xưng hô tự nhiên, có thể vòng ý nhẹ."),
    ("formal_polite", "toan_quoc", "lich_su", "Cách hỏi lịch sự, đầy đủ khi trao đổi chính thức với ngân hàng."),
    ("upset_customer", "toan_quoc", "gap_buc", "Khách đang sốt ruột hoặc bực nhưng không xúc phạm; trả lời bình tĩnh, rõ ràng."),
)

CORE_BANKING_KEYWORDS = {
    "ngân hàng", "tài khoản", "chuyển khoản", "thẻ tín dụng", "thẻ ghi nợ",
    "khoản vay", "vay vốn", "lãi suất", "tiền gửi", "tiết kiệm", "tín dụng",
    "dư nợ", "nợ xấu", "hạn mức", "thế chấp", "bảo lãnh", "ngoại hối",
    "tỷ giá", "otp", "kyc", "cic",
}


def speech_source_id(source_id: str, profile_name: str) -> str:
    return f"{source_id}::speech:{profile_name}"


def trusted_banking_path(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    return "knowledge" in parts and bool(parts & {"faq", "products"})


def banking_chunk_hits(path: Path, text: str) -> list[str]:
    hits = sorted(set(keyword_hits(text)))
    if trusted_banking_path(path):
        return hits
    # Nguồn rộng (Wikipedia/corpus/nhóm knowledge khác) phải chứng minh domain
    # ngay trên chunk đang đưa vào teacher. Một core keyword hoặc >=2 tín hiệu
    # yếu đủ để giữ các cách diễn đạt tự nhiên mà chặn chunk lệch chủ đề.
    if any(hit in CORE_BANKING_KEYWORDS for hit in hits) or len(hits) >= 2:
        return hits
    return []


def tool_names() -> set[str]:
    return {t["function"]["name"] for t in DINH_NGHIA}


def chunk_source_id(source_id: str, chunk_index: int) -> str:
    return source_id if chunk_index == 0 else f"{source_id}::chunk{chunk_index}"


def split_source_chunks(source: str, source_chars: int = 1600, overlap_chars: int = 160, max_chunks: int = 8) -> list[tuple[int, str]]:
    source = clean_text(source)
    if not source:
        return []
    if source_chars <= 0 or len(source) <= source_chars:
        return [(0, source)]
    overlap = min(max(0, overlap_chars), max(0, source_chars // 3))
    chunks: list[tuple[int, str]] = []
    start = 0
    chunk_index = 0
    while start < len(source):
        hard_end = min(len(source), start + source_chars)
        end = hard_end
        if hard_end < len(source):
            floor = min(hard_end, start + max(40, int(source_chars * 0.6)))
            best = max(source.rfind(marker, floor, hard_end) for marker in (". ", "? ", "! ", "; ", ": "))
            if best >= floor:
                end = best + 1
        chunk = clean_text(source[start:end])
        if chunk:
            chunks.append((chunk_index, chunk))
        if end >= len(source):
            break
        start = max(start + 1, end - overlap)
        chunk_index += 1
    if max_chunks > 0 and len(chunks) > max_chunks:
        if max_chunks == 1:
            return [chunks[0]]
        positions = [round(i * (len(chunks) - 1) / (max_chunks - 1)) for i in range(max_chunks)]
        chunks = [chunks[i] for i in dict.fromkeys(positions)]
    return chunks


def call_ollama(host: str, model: str, source: str, timeout: int,
                source_chars: int = 1600, num_predict: int = 192,
                temperature: float = 0.0, num_ctx: int = 4096,
                speech_profile: tuple[str, str, str, str] | None = None) -> dict:
    tool_text = json.dumps(DINH_NGHIA, ensure_ascii=False)
    speech_text = ""
    if speech_profile:
        name, region, register, instruction = speech_profile
        speech_text = (
            "\n\nKIỂU VĂN NÓI CẦN TẠO:\n"
            f"- profile: {name}\n- vùng: {region}\n- phong cách: {register}\n"
            f"- yêu cầu: {instruction}\n"
            "Chỉ thay đổi cách diễn đạt. Không thay đổi sự thật nghiệp vụ trong nguồn."
        )
    prompt = (
        f"CÔNG CỤ HIỆN CÓ:\n{tool_text}{speech_text}"
        f"\n\nNGUỒN THAM KHẢO:\n{source[:source_chars]}"
    )
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": prompt}],
        "stream": False,
        "format": "json",
        "think": False,
        "options": {
            "temperature": temperature,
            "num_predict": num_predict,
            "num_ctx": num_ctx,
        },
        "keep_alive": "10m",
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(host.rstrip("/") + "/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        outer = json.loads(resp.read().decode("utf-8"))
    return json.loads((outer.get("message") or {}).get("content") or "{}")


def call_ollama_with_truncation_retry(
        host: str, model: str, source: str, timeout: int,
        source_chars: int = 1600, num_predict: int = 384,
        retry_num_predict: int = 768, temperature: float = 0.0,
        num_ctx: int = 4096,
        speech_profile: tuple[str, str, str, str] | None = None,
) -> tuple[dict, bool]:
    """Retry malformed/truncated JSON once with a larger output budget."""
    try:
        return call_ollama(
            host, model, source, timeout, source_chars, num_predict,
            temperature, num_ctx, speech_profile,
        ), False
    except json.JSONDecodeError:
        if retry_num_predict <= num_predict:
            raise
        return call_ollama(
            host, model, source, timeout, source_chars, retry_num_predict,
            temperature, num_ctx, speech_profile,
        ), True


def load_used_source_ids(paths: list[Path]) -> set[str]:
    used_ids: set[str] = set()
    for path in paths:
        if not path.exists():
            continue
        with path.open(encoding="utf-8", errors="ignore") as old:
            for line in old:
                try:
                    prev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                source_id = str(prev.get("source_id") or "").strip()
                if source_id:
                    used_ids.add(source_id)
    return used_ids


def to_messages_with_reason(obj: dict) -> tuple[list[dict] | None, str]:
    user = redact_pii(clean_text(str(obj.get("user") or "")))
    answer = redact_pii(clean_text(str(obj.get("answer") or "")))
    call = obj.get("tool_call")
    if len(user) < 8:
        return None, "user_too_short"
    if has_cjk_hangul(user):
        return None, "user_cjk_hangul"
    if vietnamese_score(user) < 0.24:
        return None, "user_low_vi_score"
    if foreign_latin_ratio(user) > 0.22:
        return None, "user_foreign_ratio"
    messages = [
        {"role": "system", "content": "Bạn là trợ lý ngân hàng Việt Nam. Chỉ trả lời bằng tiếng Việt."},
        {"role": "user", "content": user},
    ]
    if call:
        if not isinstance(call, dict):
            return None, "tool_call_not_object"
        name = str(call.get("name") or "")
        if name not in tool_names():
            return None, "tool_name_invalid"
        if not isinstance(call.get("arguments"), dict):
            return None, "tool_arguments_invalid"
        messages.append({
            "role": "assistant",
            "tool_calls": [{"type": "function", "function": {
                "name": name, "arguments": call.get("arguments") or {}}}],
        })
    else:
        if len(answer) < 8:
            return None, "answer_too_short"
        if has_cjk_hangul(answer):
            return None, "answer_cjk_hangul"
        if vietnamese_score(answer) < 0.24:
            return None, "answer_low_vi_score"
        if foreign_latin_ratio(answer) > 0.22:
            return None, "answer_foreign_ratio"
        messages.append({"role": "assistant", "content": answer})
    return messages, "ok"


def to_messages(obj: dict) -> list[dict] | None:
    return to_messages_with_reason(obj)[0]


def main() -> None:
    ap = argparse.ArgumentParser(description="Qwen teacher tạo dữ liệu SFT tiếng Việt cho BankVN")
    ap.add_argument("inputs", nargs="+", help="Nguồn .txt/.md/.jsonl/.json")
    ap.add_argument("--output", default="data/bankvn/sft/teacher.jsonl")
    ap.add_argument(
        "--dedupe-from", action="append", default=[],
        help="JSONL đã gộp trước đó; có thể truyền nhiều lần để tránh lặp source_id",
    )
    ap.add_argument("--model", default="qwen3.5:9b")
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--max-samples", type=int, default=500)
    ap.add_argument("--max-attempts", type=int, default=0,
                    help="0 = thử hết nguồn; >0 = giới hạn số request teacher")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--workers", type=int, default=2,
                    help="Số request Qwen chạy đồng thời; benchmark 1/2/4 trên máy thật")
    ap.add_argument("--source-chars", type=int, default=1600)
    ap.add_argument("--source-overlap-chars", type=int, default=160)
    ap.add_argument("--max-chunks-per-source", type=int, default=8)
    ap.add_argument("--num-predict", type=int, default=384)
    ap.add_argument(
        "--retry-num-predict", type=int, default=768,
        help="Retry một lần khi JSON bị cắt; <= num-predict để tắt retry",
    )
    ap.add_argument("--num-ctx", type=int, default=4096)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--source-min-score", type=float, default=0.24)
    ap.add_argument("--speech-profiles-per-source", type=int, default=3,
                    help="Số phong cách văn nói chưa học lấy từ mỗi chunk; 0 = tắt")
    ap.add_argument("--seed", type=int, default=42,
                    help="Seed xáo nguồn để mỗi chu kỳ lấy mẫu đa dạng nhưng vẫn tái lập được")
    args = ap.parse_args()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    dedupe_paths = [out, *(Path(path) for path in args.dedupe_from)]
    used_ids = load_used_source_ids(dedupe_paths)
    written = failed = rejected_source = rejected_output = rejected_domain = 0
    retried_truncated = 0
    reject_reasons: Counter[str] = Counter()
    started = time.perf_counter()

    candidates: list[tuple[
        Path, dict, str, str, int, tuple[str, str, str, str] | None, list[str]
    ]] = []
    source_documents = rejected_chunks = 0
    for path in iter_input_files(args.inputs):
        for doc in read_documents(path):
            source_documents += 1
            source = redact_pii(clean_text(doc["text"]))
            if not is_strict_vietnamese(source, min_score=args.source_min_score, min_chars=40):
                rejected_source += 1
                continue
            root_source_id = str(doc.get("id") or stable_hash(source))
            doc = dict(doc)
            doc["id"] = root_source_id
            for chunk_index, chunk in split_source_chunks(
                    source, args.source_chars, args.source_overlap_chars,
                    args.max_chunks_per_source):
                if not is_strict_vietnamese(
                        chunk, min_score=args.source_min_score, min_chars=40):
                    rejected_chunks += 1
                    continue
                domain_hits = banking_chunk_hits(path, chunk)
                if not trusted_banking_path(path) and not domain_hits:
                    rejected_domain += 1
                    continue
                chunk_id = chunk_source_id(root_source_id, chunk_index)
                if args.speech_profiles_per_source <= 0:
                    if chunk_id not in used_ids:
                        candidates.append((
                            path, doc, chunk, chunk_id, chunk_index, None, domain_hits
                        ))
                    continue
                available = [
                    profile for profile in SPEECH_PROFILES
                    if speech_source_id(chunk_id, profile[0]) not in used_ids
                ]
                random.Random(stable_hash(chunk_id)).shuffle(available)
                for profile in available[:args.speech_profiles_per_source]:
                    source_id = speech_source_id(chunk_id, profile[0])
                    candidates.append((
                        path, doc, chunk, source_id, chunk_index, profile, domain_hits
                    ))
    random.Random(args.seed).shuffle(candidates)
    if args.max_attempts > 0:
        candidates = candidates[:args.max_attempts]

    def generate(item: tuple[
        Path, dict, str, str, int, tuple[str, str, str, str] | None, list[str]
    ]):
        path, doc, source, source_id, chunk_index, speech_profile, domain_hits = item
        obj, retried = call_ollama_with_truncation_retry(
            args.host, args.model, source, args.timeout,
            args.source_chars, args.num_predict, args.retry_num_predict,
            args.temperature, args.num_ctx, speech_profile,
        )
        messages, reason = to_messages_with_reason(obj)
        return (path, doc, source_id, chunk_index, speech_profile, domain_hits,
                messages, reason, retried)

    with out.open("a", encoding="utf-8") as dst:
        retried_truncated = 0
        workers = max(1, args.workers)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            pending = set()
            iterator = iter(candidates)

            def submit_one() -> bool:
                try:
                    item = next(iterator)
                except StopIteration:
                    return False
                pending.add(pool.submit(generate, item))
                return True

            for _ in range(workers):
                if not submit_one():
                    break

            while pending and (not args.max_samples or written < args.max_samples):
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    if args.max_samples and written >= args.max_samples:
                        future.cancel()
                        continue
                    try:
                        (path, doc, source_id, chunk_index, speech_profile, domain_hits,
                         messages, reason, retried) = future.result()
                    except Exception as exc:
                        failed += 1
                        print(f"[WARN] teacher lỗi: {type(exc).__name__}: {exc}")
                        submit_one()
                        continue
                    retried_truncated += int(retried)
                    if not messages:
                        rejected_output += 1
                        reject_reasons[reason] += 1
                        submit_one()
                        continue
                    if source_id and source_id in used_ids:
                        submit_one()
                        continue
                    mode = "router" if any(m.get("tool_calls") for m in messages) else "assistant"
                    speech_name = speech_profile[0] if speech_profile else "neutral"
                    speech_region = speech_profile[1] if speech_profile else "toan_quoc"
                    speech_register = speech_profile[2] if speech_profile else "trung_tinh"
                    dst.write(json.dumps({"messages": messages, "mode": mode, "teacher": args.model,
                                          "source": doc.get("source", ""),
                                          "source_id": source_id,
                                          "source_root_id": str(doc.get("id") or ""),
                                          "source_chunk": chunk_index,
                                          "banking_keywords": domain_hits,
                                          "speech_profile": speech_name,
                                          "speech_region": speech_region,
                                          "speech_register": speech_register},
                                         ensure_ascii=False) + "\n")
                    dst.flush()
                    if source_id:
                        used_ids.add(source_id)
                    written += 1
                    if not args.max_samples or written < args.max_samples:
                        submit_one()

                if args.max_samples and written >= args.max_samples:
                    for future in pending:
                        future.cancel()
                    break

    elapsed = max(time.perf_counter() - started, 1e-9)
    print(json.dumps({
        "written": written,
        "failed": failed,
        "source_documents": source_documents,
        "rejected_chunks": rejected_chunks,
        "rejected_source": rejected_source,
        "rejected_domain": rejected_domain,
        "rejected_output": rejected_output,
        "reject_reasons": dict(reject_reasons),
        "retried_truncated": retried_truncated,
        "workers": max(1, args.workers),
        "attempted": written + failed + rejected_output,
        "eligible_sources": len(candidates),
        "eligible_chunks": len(candidates),
        "source_chars": args.source_chars,
        "elapsed_seconds": round(elapsed, 3),
        "samples_per_minute": round(written * 60.0 / elapsed, 2),
        "output": str(out),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
