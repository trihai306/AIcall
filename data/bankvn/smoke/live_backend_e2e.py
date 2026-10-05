"""Live BankVN/Qwen tool-calling probe for Windows Ollama."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import ollama
from transformers import AutoTokenizer


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from backend.pipeline import cong_cu_llm  # noqa: E402
from backend.pipeline.session_manager import CallSession  # noqa: E402
from backend.services.llm_service import LLMService  # noqa: E402
from backend.services.rag_service import RAGService  # noqa: E402


BANKVN_MODEL = "bankvn-smoke6-router-v2"
QWEN_MODEL = "qwen3.5:9b"
HF_ROUTER_MODEL = ROOT / "models" / "bankvn" / "sft" / "bankvn-smoke6-router-refine1" / "final"


class SpyClient:
    def __init__(self, inner):
        self.inner = inner
        self.calls: list[dict] = []

    async def chat(self, *args, **kwargs):
        self.calls.append({"args": args, "kwargs": kwargs})
        return await self.inner.chat(*args, **kwargs)


def diagnose_ollama_tokenization(model: str) -> None:
    tokenizer = AutoTokenizer.from_pretrained(HF_ROUTER_MODEL, local_files_only=True)
    client = ollama.Client()
    system_prompt = cong_cu_llm.prompt_tool_bankvn(
        cong_cu_llm.PROMPT_QUYET_DINH,
        cong_cu_llm.DINH_NGHIA,
    )
    cases = [
        (
            "tiny",
            [{"role": "system", "content": "X"}, {"role": "user", "content": "Y"}],
            "<|bankvn_system|>X<|bankvn_end|><|bankvn_user|>Y<|bankvn_end|><|bankvn_assistant|>",
        ),
        (
            "prod_debt",
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Dư nợ của tôi còn bao nhiêu?"},
            ],
            (
                "<|bankvn_system|>" + system_prompt + "<|bankvn_end|>"
                "<|bankvn_user|>Dư nợ của tôi còn bao nhiêu?<|bankvn_end|>"
                "<|bankvn_assistant|>"
            ),
        ),
    ]
    for label, messages, raw_prompt in cases:
        hf_count = 1 + len(tokenizer.encode(raw_prompt, add_special_tokens=False))
        response = client.chat(
            model=model,
            messages=messages,
            stream=False,
            options={"num_predict": 1, "temperature": 0, "num_ctx": 4096},
        )
        prompt_count = int(response.get("prompt_eval_count") or 0)
        print("TOKEN_DIAG=" + json.dumps({
            "model": model,
            "case": label,
            "hf_with_bos": hf_count,
            "ollama_prompt": prompt_count,
            "delta": prompt_count - hf_count,
        }, ensure_ascii=False), flush=True)


async def route_once(model: str, question: str, system_prompt: str) -> dict:
    llm = LLMService()
    llm.model = model
    spy = SpyClient(llm.client)
    llm.client = spy

    prompt_counts: list[int] = []
    original_window_check = llm._soat_cua_so

    def capture_prompt_count(value: int) -> None:
        prompt_counts.append(value)
        original_window_check(value)

    llm._soat_cua_so = capture_prompt_count
    tool_calls: list[dict] = []
    visible: list[str] = []
    started = time.perf_counter()
    async for token in llm.stream_response(
        [{"role": "user", "content": question}],
        system_prompt,
        tools=cong_cu_llm.DINH_NGHIA,
        on_tool_calls=tool_calls.extend,
    ):
        visible.append(token)
    elapsed_ms = (time.perf_counter() - started) * 1000.0

    sent = spy.calls[-1]["kwargs"]
    messages = sent.get("messages") or []
    sent_system = messages[0].get("content", "") if messages else ""
    visible_text = "".join(visible)
    return {
        "model": model,
        "question": question,
        "tool_calls": tool_calls,
        "visible_text": visible_text,
        "elapsed_ms": round(elapsed_ms, 2),
        "native_tools_sent": bool(sent.get("tools")),
        "system_has_tool_schema": "CÔNG CỤ CÓ THỂ GỌI:" in sent_system,
        "marker_visible": "<|bankvn_tool_call|>" in visible_text,
        "prompt_eval_counts": prompt_counts,
    }


async def main() -> None:
    diagnose_ollama_tokenization(BANKVN_MODEL)
    bankvn_cases = [
        (
            "Dư nợ của tôi còn bao nhiêu?",
            {"name": "tra_ho_so_khach", "arguments": {}},
        ),
        (
            "Lãi suất vay tín chấp hiện bao nhiêu?",
            {
                "name": "tra_thong_tin_san_pham",
                "arguments": {"san_pham": "vay tín chấp", "can_biet": "lãi suất"},
            },
        ),
    ]
    bankvn_results = []
    for question, expected in bankvn_cases:
        result = await route_once(BANKVN_MODEL, question, cong_cu_llm.PROMPT_QUYET_DINH)
        result["expected"] = expected
        result["exact"] = result["tool_calls"] == [expected]
        bankvn_results.append(result)
        print("BANKVN_ROUTE=" + json.dumps(result, ensure_ascii=False), flush=True)

    session = CallSession(phone="0900000000", product="vay tín chấp")
    session.ngu_canh_khach = "Dư nợ hiện tại: 142.500.000 đồng."
    rag = RAGService()
    rag.load()

    executed = []
    for result in bankvn_results:
        if not result["tool_calls"]:
            executed.append(
                {
                    "name": "",
                    "arguments": {},
                    "elapsed_ms": 0.0,
                    "output": "SKIP: model không tạo tool call",
                }
            )
            continue
        call = result["tool_calls"][0]
        started = time.perf_counter()
        output = await cong_cu_llm.chay(call["name"], call["arguments"], session, rag=rag)
        executed.append(
            {
                "name": call["name"],
                "arguments": call["arguments"],
                "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 2),
                "output": output,
            }
        )

    qwen = await route_once(
        QWEN_MODEL,
        "Dư nợ của tôi còn bao nhiêu?",
        cong_cu_llm.PROMPT_QUYET_DINH,
    )
    checks = {
        "bankvn_exact_2_of_2": all(item["exact"] for item in bankvn_results),
        "bankvn_schema_in_system": all(item["system_has_tool_schema"] for item in bankvn_results),
        "bankvn_no_native_tools": all(not item["native_tools_sent"] for item in bankvn_results),
        "bankvn_marker_hidden": all(not item["marker_visible"] for item in bankvn_results),
        "bankvn_prompt_tokens_accounted": all(bool(item["prompt_eval_counts"]) for item in bankvn_results),
        "customer_tool_executed": bool(executed) and "142.500.000" in executed[0]["output"],
        "product_tool_executed": (
            len(executed) == 2
            and bool(executed[1]["output"].strip())
            and not executed[1]["output"].startswith("SKIP:")
        ),
        "qwen_native_tools_sent": qwen["native_tools_sent"],
        "qwen_customer_tool_call": qwen["tool_calls"] == [{"name": "tra_ho_so_khach", "arguments": {}}],
    }
    report = {
        "bankvn": bankvn_results,
        "tool_execution": executed,
        "qwen": qwen,
        "rag_loaded": rag._is_loaded,
        "checks": checks,
        "passed": all(checks.values()),
    }
    print("BANKVN_LIVE_E2E=" + json.dumps(report, ensure_ascii=False))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
