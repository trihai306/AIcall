#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import json
import math
import random
import sys
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from training.bankvn.common import (  # noqa: E402
    clean_text,
    foreign_latin_ratio,
    has_cjk_hangul,
    is_strict_vietnamese,
    redact_pii,
    stable_hash,
)
from backend.pipeline import cong_cu_llm  # noqa: E402


SYSTEM = """Bạn tạo dữ liệu huấn luyện router cho BankVN.
Chỉ dùng tiếng Việt tự nhiên. Không dùng tiếng Trung, Nhật, Hàn. Không chép ví dụ mẫu.
Trả về JSON đúng dạng {"samples":[...]}, không markdown và không giải thích ngoài JSON.
Mỗi sample có user, answer, tool_call. Câu user phải đa dạng, tự nhiên như khách Việt Nam.
Không bịa số dư, lãi suất, phí hay dữ liệu tài khoản cụ thể."""


TARGET_PROMPTS = {
    "profile": """Tạo {count} câu khác nhau về dữ liệu CỦA CHÍNH KHÁCH HÀNG đang tồn tại:
dư nợ hiện tại, ngày đến hạn, số kỳ/tháng còn lại, trạng thái đã trả xong hay chưa,
tình trạng hợp đồng/khoản vay. Mỗi sample bắt buộc tool_call là
{"name":"tra_ho_so_khach","arguments":{}} và answer="".""",
    "product": """Tạo {count} câu khác nhau hỏi THÔNG TIN CHUNG về sản phẩm ngân hàng:
lãi suất, hạn mức, thời hạn vay, điều kiện, hồ sơ, phí, thẻ tín dụng, trả nợ trước hạn.
Mỗi sample bắt buộc tool_call.name="tra_thong_tin_san_pham", arguments là object ngắn
với san_pham/can_biet phù hợp, answer="". Không hỏi dữ liệu riêng của tài khoản hiện có.""",
    "assistant": """Tạo {count} câu khác nhau KHÔNG CẦN công cụ ngân hàng, gồm luân phiên:
chào hỏi, cảm ơn, nghe rõ không, đang bận/hẹn gọi lại, chưa muốn vay/từ chối lịch sự,
muốn suy nghĩ thêm, câu xã giao hoặc câu ngoài nghiệp vụ ngân hàng. tool_call=null.
answer phải là một câu trả lời tiếng Việt ngắn, tự nhiên, lịch sự và không bịa dữ liệu.""",
}


def call_ollama(host: str, model: str, target: str, batch_size: int, timeout: int,
                num_predict: int, num_ctx: int, temperature: float, seed: int) -> dict:
    prompt = TARGET_PROMPTS[target].replace("{count}", str(batch_size)) + (
        f"\nMã biến thể {seed}. Ưu tiên cách diễn đạt mới, bối cảnh đời thường khác nhau, "
        "tránh lặp các câu quá ngắn hoặc mẫu câu phổ biến."
    )
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "format": "json",
        "think": False,
        "options": {
            "temperature": temperature,
            "num_predict": num_predict,
            "num_ctx": num_ctx,
            "seed": seed,
        },
        "keep_alive": "10m",
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        host.rstrip("/") + "/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        outer = json.loads(resp.read().decode("utf-8"))
    return json.loads((outer.get("message") or {}).get("content") or "{}")


def normalize_sample(obj: dict, target: str) -> tuple[dict | None, str]:
    if not isinstance(obj, dict):
        return None, "sample_not_object"
    user = redact_pii(clean_text(str(obj.get("user") or "")))
    answer = redact_pii(clean_text(str(obj.get("answer") or "")))
    call = obj.get("tool_call")
    if not is_strict_vietnamese(user, min_score=0.24, min_chars=8):
        return None, "user_not_strict_vi"
    if has_cjk_hangul(user) or foreign_latin_ratio(user) > 0.22:
        return None, "user_foreign"

    # Qwen đôi khi tuân thủ schema nhưng nội dung câu lại thuộc lớp khác
    # (ví dụ sinh "hỏi gói vay tiêu dùng" trong batch assistant). Không cho
    # sample mâu thuẫn rõ ràng đi vào train/eval; câu mơ hồ vẫn được giữ.
    fast = cong_cu_llm.quyet_dinh_nhanh(user)
    if fast == cong_cu_llm.KHONG_CONG_CU:
        fast_target = "assistant"
    elif fast == "tra_ho_so_khach":
        fast_target = "profile"
    elif fast == "tra_thong_tin_san_pham":
        fast_target = "product"
    else:
        fast_target = ""
    if fast_target and fast_target != target:
        return None, f"semantic_conflict_{fast_target}"

    messages = [
        {"role": "system", "content": "Bạn là trợ lý ngân hàng Việt Nam. Chỉ trả lời bằng tiếng Việt."},
        {"role": "user", "content": user},
    ]
    if target == "assistant":
        if call is not None:
            return None, "assistant_has_tool"
        if not is_strict_vietnamese(answer, min_score=0.24, min_chars=8):
            return None, "answer_not_strict_vi"
        if has_cjk_hangul(answer) or foreign_latin_ratio(answer) > 0.22:
            return None, "answer_foreign"
        messages.append({"role": "assistant", "content": answer})
        mode = "assistant"
    else:
        if not isinstance(call, dict):
            return None, "tool_missing"
        expected_name = "tra_ho_so_khach" if target == "profile" else "tra_thong_tin_san_pham"
        if call.get("name") != expected_name:
            return None, "wrong_tool"
        arguments = call.get("arguments")
        if not isinstance(arguments, dict):
            return None, "arguments_not_object"
        if target == "profile" and arguments:
            return None, "profile_arguments_not_empty"
        cleaned_args: dict[str, object] = {}
        for key, value in arguments.items():
            if isinstance(value, str):
                value = redact_pii(clean_text(value))
                if has_cjk_hangul(value) or foreign_latin_ratio(value) > 0.22:
                    return None, "argument_foreign"
            cleaned_args[str(key)] = value
        messages.append({
            "role": "assistant",
            "tool_calls": [{
                "type": "function",
                "function": {"name": expected_name, "arguments": cleaned_args},
            }],
        })
        mode = "router"

    fingerprint = stable_hash(user.lower())
    return {
        "messages": messages,
        "mode": mode,
        "target": target,
        "source": "qwen_router_synthetic",
        "source_id": f"qwen-router:{fingerprint}",
    }, "ok"


def main() -> None:
    ap = argparse.ArgumentParser(description="Qwen 9B sinh dữ liệu router BankVN cân bằng")
    ap.add_argument("--output", default="data/bankvn/sft/router_teacher.jsonl")
    ap.add_argument("--model", default="qwen3.5:9b")
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--samples-per-class", type=int, default=30)
    ap.add_argument("--batch-size", type=int, default=3)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--max-requests", type=int, default=0,
                    help="0 = tự tính dư 3 lần số request tối thiểu")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--num-predict", type=int, default=512)
    ap.add_argument("--num-ctx", type=int, default=4096)
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--seed", type=int, default=4200)
    args = ap.parse_args()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    used_ids: set[str] = set()
    if out.exists():
        with out.open(encoding="utf-8", errors="ignore") as old:
            for line in old:
                try:
                    prev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if prev.get("source_id"):
                    used_ids.add(str(prev["source_id"]))

    targets = ("profile", "product", "assistant")
    wanted = {target: max(0, args.samples_per_class) for target in targets}
    accepted = Counter()
    rejected = Counter()
    batch_size = max(1, args.batch_size)
    minimum_requests = sum(math.ceil(value / batch_size) for value in wanted.values())
    max_requests = args.max_requests or max(3, minimum_requests * 6)
    started = time.perf_counter()
    requests_by_class = Counter()

    def generate(task_index: int, target: str):
        return target, call_ollama(
            args.host,
            args.model,
            target,
            batch_size,
            args.timeout,
            args.num_predict,
            args.num_ctx,
            args.temperature,
            args.seed + task_index,
        )

    request_index = 0
    with out.open("a", encoding="utf-8") as dst:
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            pending = set()

            def submit_one() -> bool:
                nonlocal request_index
                if request_index >= max_requests:
                    return False
                remaining = [
                    target for target in targets
                    if accepted[target] < wanted[target]
                ]
                if not remaining:
                    return False
                target = max(
                    remaining,
                    key=lambda name: (
                        wanted[name] - accepted[name],
                        -requests_by_class[name],
                    ),
                )
                pending.add(pool.submit(generate, request_index, target))
                requests_by_class[target] += 1
                request_index += 1
                return True

            for _ in range(max(1, args.workers)):
                if not submit_one():
                    break

            while pending and any(accepted[target] < wanted[target] for target in targets):
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    try:
                        target, payload = future.result()
                    except Exception as exc:
                        rejected[type(exc).__name__] += 1
                        submit_one()
                        continue
                    samples = payload.get("samples") if isinstance(payload, dict) else None
                    if not isinstance(samples, list):
                        rejected["samples_not_list"] += 1
                        submit_one()
                        continue
                    for raw in samples:
                        if accepted[target] >= wanted[target]:
                            break
                        row, reason = normalize_sample(raw, target)
                        if not row:
                            rejected[reason] += 1
                            continue
                        source_id = str(row["source_id"])
                        if source_id in used_ids:
                            rejected["duplicate"] += 1
                            continue
                        row["teacher"] = args.model
                        dst.write(json.dumps(row, ensure_ascii=False) + "\n")
                        dst.flush()
                        used_ids.add(source_id)
                        accepted[target] += 1
                    if any(accepted[name] < wanted[name] for name in targets):
                        submit_one()

    elapsed = max(time.perf_counter() - started, 1e-9)
    total = sum(accepted.values())
    metrics = {
        "written": total,
        "accepted_by_class": dict(accepted),
        "requested_by_class": wanted,
        "rejected": dict(rejected),
        "workers": max(1, args.workers),
        "batch_size": batch_size,
        "requests_started": request_index,
        "requests_by_class": dict(requests_by_class),
        "elapsed_seconds": round(elapsed, 3),
        "samples_per_minute": round(total * 60.0 / elapsed, 2),
        "output": str(out),
    }
    print(json.dumps(metrics, ensure_ascii=False))
    if any(accepted[target] < wanted[target] for target in targets):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
