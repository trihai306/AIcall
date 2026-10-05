from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

import torch
import sentencepiece as spm
from sentencepiece import sentencepiece_model_pb2 as sp_pb2
from transformers import AutoModelForCausalLM, AutoTokenizer


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from backend.pipeline import cong_cu_llm  # noqa: E402


def build_ids(tokenizer, system_prompt: str, user: str, newline: bool) -> list[int]:
    end_id = tokenizer.convert_tokens_to_ids("<|bankvn_end|>")
    ids = [tokenizer.bos_token_id]
    chunks = [
        ("<|bankvn_system|>", system_prompt),
        ("<|bankvn_user|>", user),
    ]
    for marker, content in chunks:
        ids.append(tokenizer.convert_tokens_to_ids(marker))
        ids.extend(tokenizer.encode(content, add_special_tokens=False))
        ids.append(end_id)
        if newline:
            ids.extend(tokenizer.encode("\n", add_special_tokens=False))
    ids.append(tokenizer.convert_tokens_to_ids("<|bankvn_assistant|>"))
    return ids


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--patch-end-copy", default="")
    args = ap.parse_args()

    model_path = Path(args.model)
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    if args.patch_end_copy:
        target = Path(args.patch_end_copy)
        if target.exists():
            raise SystemExit(f"target already exists: {target}")
        shutil.copytree(model_path, target)
        patched = sp_pb2.ModelProto()
        patched.ParseFromString((target / "tokenizer.model").read_bytes())
        if patched.pieces[3].piece != tokenizer.eos_token:
            raise SystemExit("unexpected eos token at id 3")
        patched.pieces[3].type = sp_pb2.ModelProto.SentencePiece.USER_DEFINED
        (target / "tokenizer.model").write_bytes(patched.SerializeToString())
        print(json.dumps({"patched_copy": str(target)}, ensure_ascii=False))
        return
    sp = spm.SentencePieceProcessor(model_file=str(model_path / "tokenizer.model"))
    proto = sp_pb2.ModelProto()
    proto.ParseFromString((model_path / "tokenizer.model").read_bytes())
    print(json.dumps({
        "special_piece_types": [
            {"id": i, "piece": proto.pieces[i].piece, "type": int(proto.pieces[i].type)}
            for i in range(min(9, len(proto.pieces)))
        ]
    }, ensure_ascii=False))
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        local_files_only=True,
        torch_dtype=torch.float16,
        device_map="cuda",
    )
    model.eval()
    system_prompt = cong_cu_llm.prompt_tool_bankvn(
        cong_cu_llm.PROMPT_QUYET_DINH,
        cong_cu_llm.DINH_NGHIA,
    )
    questions = [
        "Dư nợ của tôi còn bao nhiêu?",
        "Lãi suất vay tín chấp hiện bao nhiêu?",
    ]
    for question in questions:
        raw_prompt = (
            "<|bankvn_system|>" + system_prompt + "<|bankvn_end|>"
            "<|bankvn_user|>" + question + "<|bankvn_end|>"
            "<|bankvn_assistant|>"
        )
        hf_ids = tokenizer.encode(raw_prompt, add_special_tokens=False)
        sp_ids = sp.encode(raw_prompt, out_type=int)
        first = next(
            (i for i, (a, b) in enumerate(zip(hf_ids, sp_ids)) if a != b),
            min(len(hf_ids), len(sp_ids)),
        )
        print(json.dumps({
            "parity_question": question,
            "hf_len": len(hf_ids),
            "sp_len": len(sp_ids),
            "delta": len(sp_ids) - len(hf_ids),
            "first_mismatch": first,
            "hf_slice": hf_ids[max(0, first - 5):first + 15],
            "sp_slice": sp_ids[max(0, first - 5):first + 15],
        }, ensure_ascii=False))
    for newline in (False, True):
        framing = "ollama_newline" if newline else "train_exact"
        for question in questions:
            ids = build_ids(tokenizer, system_prompt, question, newline)
            input_ids = torch.tensor([ids], dtype=torch.long, device="cuda")
            with torch.inference_mode():
                out = model.generate(
                    input_ids=input_ids,
                    max_new_tokens=96,
                    do_sample=False,
                    eos_token_id=tokenizer.convert_tokens_to_ids("<|bankvn_end|>"),
                    pad_token_id=tokenizer.pad_token_id,
                )
            generated = out[0, input_ids.shape[1]:].tolist()
            text = tokenizer.decode(generated, skip_special_tokens=False)
            print(json.dumps({
                "framing": framing,
                "question": question,
                "prompt_tokens": len(ids),
                "generated_ids": generated,
                "text": text,
            }, ensure_ascii=False))


if __name__ == "__main__":
    main()
