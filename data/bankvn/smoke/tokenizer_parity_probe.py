from __future__ import annotations

import json
from pathlib import Path
import sys

import sentencepiece as spm
from transformers import AutoTokenizer


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from backend.pipeline import cong_cu_llm  # noqa: E402


MODEL = ROOT / "models/bankvn/sft/bankvn-smoke6-router-refine1/final"


def main() -> None:
    tok = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
    sp = spm.SentencePieceProcessor(model_file=str(MODEL / "tokenizer.model"))
    system = cong_cu_llm.prompt_tool_bankvn(
        cong_cu_llm.PROMPT_QUYET_DINH,
        cong_cu_llm.DINH_NGHIA,
    )
    for question in (
        "Dư nợ của tôi còn bao nhiêu?",
        "Lãi suất vay tín chấp hiện bao nhiêu?",
    ):
        prompt = (
            "<|bankvn_system|>" + system + "<|bankvn_end|>"
            "<|bankvn_user|>" + question + "<|bankvn_end|>"
            "<|bankvn_assistant|>"
        )
        hf_ids = tok.encode(prompt, add_special_tokens=False)
        sp_ids = sp.encode(prompt, out_type=int)
        first = next(
            (i for i, (a, b) in enumerate(zip(hf_ids, sp_ids)) if a != b),
            min(len(hf_ids), len(sp_ids)),
        )
        print(json.dumps({
            "question": question,
            "hf_len": len(hf_ids),
            "sp_len": len(sp_ids),
            "delta": len(sp_ids) - len(hf_ids),
            "first_mismatch": first,
            "hf_slice": hf_ids[max(0, first - 5):first + 15],
            "sp_slice": sp_ids[max(0, first - 5):first + 15],
            "sp_add_dummy_prefix": sp.serialized_model_proto() is not None,
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
