"""Đo RAG + Qwen 9B trên máy Windows production, dùng câu hỏi Shinhan thật.

Chạy từ C:\\duan\\chat-ai với backend :8100 và Ollama đã mở. Script chỉ đọc
knowledge rồi hỏi model; không gọi điện, không sửa dữ liệu hoặc bật training.
"""

import asyncio
import json
import statistics
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.services.llm_service import LLMService


QUESTIONS = [
    "Thẻ tín dụng Shinhan mới nhận thì kích hoạt như thế nào?",
    "Nếu mất thẻ tín dụng Shinhan, tôi cần khóa thẻ ra sao?",
    "Đăng ký chức năng thẻ điện tử Shinhan trên SOL như thế nào?",
]


def retrieve(question: str) -> dict:
    data = urllib.parse.urlencode({
        "cau_hoi": question,
        "san_pham": "thẻ tín dụng Shinhan",
        "top_k": 2,
    }).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:8100/api/knowledge/hoi-thu", data=data, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


async def main():
    llm = LLMService()
    rows = []
    for question in QUESTIONS:
        rag = retrieve(question)
        chunks = [m for m in rag.get("manh", []) if not m.get("bi_loc")]
        sources = [m.get("nguon", "") for m in chunks]
        if not chunks or not all(s.startswith("shinhan_") for s in sources):
            raise RuntimeError(f"RAG trả nguồn ngoài Shinhan: {sources}")
        context = "\n---\n".join(m["doan"] for m in chunks)
        system = llm.build_system_prompt(
            product="thẻ tín dụng Shinhan",
            rag_context=context,
            scenario={"org_name": "Ngân hàng Shinhan", "agent_name": "Em"},
        )
        t0 = time.perf_counter()
        first = None
        tokens = []
        async for token in llm.stream_response([{"role": "user", "content": question}], system):
            if first is None:
                first = time.perf_counter()
            tokens.append(token)
        end = time.perf_counter()
        rows.append({
            "question": question,
            "rag_ms": rag["ms"],
            "context_chars": len(context),
            "sources": sources,
            "llm_ttft_ms": round((first - t0) * 1000) if first else None,
            "llm_full_ms": round((end - t0) * 1000),
            "rag_plus_llm_ms": round(rag["ms"] + (end - t0) * 1000),
            "answer": "".join(tokens),
        })
    print(json.dumps({
        "model": llm.model,
        "samples": rows,
        "median_rag_ms": statistics.median(row["rag_ms"] for row in rows),
        "median_llm_ttft_ms": statistics.median(row["llm_ttft_ms"] for row in rows),
        "median_llm_full_ms": statistics.median(row["llm_full_ms"] for row in rows),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
