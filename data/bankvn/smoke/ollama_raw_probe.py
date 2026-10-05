from __future__ import annotations

import json
from pathlib import Path
import sys

import ollama


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from backend.pipeline import cong_cu_llm  # noqa: E402


MODEL = "bankvn-smoke6-router-v3"


def main() -> None:
    system_prompt = cong_cu_llm.prompt_tool_bankvn(
        cong_cu_llm.PROMPT_QUYET_DINH,
        cong_cu_llm.DINH_NGHIA,
    )
    client = ollama.Client()
    for question in (
        "Dư nợ của tôi còn bao nhiêu?",
        "Lãi suất vay tín chấp hiện bao nhiêu?",
    ):
        prompt = (
            "<|bankvn_system|>" + system_prompt + "<|bankvn_end|>"
            "<|bankvn_user|>" + question + "<|bankvn_end|>"
            "<|bankvn_assistant|>"
        )
        response = client.generate(
            model=MODEL,
            prompt=prompt,
            raw=True,
            stream=False,
            options={"temperature": 0},
        )
        eval_count = int(response.get("eval_count") or 0)
        eval_ns = int(response.get("eval_duration") or 0)
        print(json.dumps({
            "question": question,
            "response": response.get("response", ""),
            "prompt_eval_count": response.get("prompt_eval_count"),
            "eval_count": eval_count,
            "total_ms": round(int(response.get("total_duration") or 0) / 1e6, 2),
            "tok_s": round(eval_count / (eval_ns / 1e9), 2) if eval_count and eval_ns else 0,
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
