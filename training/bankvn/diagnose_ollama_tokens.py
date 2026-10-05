#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tokenizers import Tokenizer


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from backend.pipeline import cong_cu_llm  # noqa: E402


def first_mismatches(expected: list[int], actual: list[int], limit: int = 24) -> list[dict]:
    rows = []
    for i in range(max(len(expected), len(actual))):
        left = expected[i] if i < len(expected) else None
        right = actual[i] if i < len(actual) else None
        if left != right:
            rows.append({"index": i, "hf": left, "ollama": right})
            if len(rows) >= limit:
                break
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="So token ID prompt HF và Ollama cho BankVN")
    ap.add_argument("--model", required=True)
    ap.add_argument(
        "--hf",
        default="models/bankvn/sft/bankvn-smoke6-router-refine1/final",
    )
    args = ap.parse_args()

    tokenizer = Tokenizer.from_file(str(ROOT / args.hf / "tokenizer.json"))
    system_prompt = cong_cu_llm.prompt_tool_bankvn(
        cong_cu_llm.PROMPT_QUYET_DINH,
        cong_cu_llm.DINH_NGHIA,
    )
    for question in (
        "Dư nợ của tôi còn bao nhiêu?",
        "Lãi suất vay tín chấp hiện bao nhiêu?",
    ):
        prompt = (
            "<|bankvn_system|>" + system_prompt + "<|bankvn_end|>"
            "<|bankvn_user|>" + question + "<|bankvn_end|>"
            "<|bankvn_assistant|>"
        )
        payload = json.dumps({
            "model": args.model,
            "prompt": prompt,
            "raw": True,
            "stream": False,
            "options": {"temperature": 0},
        }).encode("utf-8")
        request = Request(
            "http://127.0.0.1:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=120) as http_response:
                response = json.loads(http_response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            print(json.dumps({
                "question": question,
                "http_status": exc.code,
                "http_error": body,
            }, ensure_ascii=False))
            continue
        prompt_count = int(response.get("prompt_eval_count") or 0)
        context = list(response.get("context") or [])
        ollama_prompt = context[:prompt_count] if context else []
        hf_raw = list(tokenizer.encode(prompt, add_special_tokens=False).ids)
        hf_bos = [2] + hf_raw
        print(json.dumps({
            "question": question,
            "prompt_eval_count": prompt_count,
            "context_available": bool(context),
            "context_len": len(context),
            "hf_raw_len": len(hf_raw),
            "hf_bos_len": len(hf_bos),
            "mismatch_vs_raw": first_mismatches(hf_raw, ollama_prompt),
            "mismatch_vs_bos": first_mismatches(hf_bos, ollama_prompt),
            "ollama_prompt_head": ollama_prompt[:32],
            "hf_raw_head": hf_raw[:32],
            "response": response.get("response", ""),
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
