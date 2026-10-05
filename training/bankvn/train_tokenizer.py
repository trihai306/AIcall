#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import sentencepiece as spm
from transformers import TokenizersBackend

from common import SPECIAL_TOKENS, ensure_bankvn_tokenizer_config


def write_sentencepiece_input(path: Path, output: Path) -> int:
    count = 0
    with path.open(encoding="utf-8") as f:
        with output.open("w", encoding="utf-8", newline="\n") as dst:
            for line in f:
                if not line.strip():
                    continue
                obj = json.loads(line)
                text = str(obj.get("text") or "").replace("\n", " ").strip()
                if text:
                    dst.write(text + "\n")
                    count += 1
    return count


def main() -> None:
    ap = argparse.ArgumentParser(description="Train tokenizer riêng cho BankVN")
    ap.add_argument("--corpus", default="data/bankvn/clean/corpus.jsonl")
    ap.add_argument("--output", default="models/bankvn/tokenizer")
    ap.add_argument("--vocab-size", type=int, default=32000)
    args = ap.parse_args()

    corpus = Path(args.corpus)
    if not corpus.exists():
        raise SystemExit(f"[ERROR] Không thấy corpus: {corpus}")
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    sp_input = out / "_sentencepiece_input.txt"
    docs = write_sentencepiece_input(corpus, sp_input)
    if docs == 0:
        raise SystemExit("[ERROR] Corpus không có text để train tokenizer")

    model_prefix = out / "tokenizer"
    spm.SentencePieceTrainer.train(
        input=str(sp_input),
        model_prefix=str(model_prefix),
        vocab_size=args.vocab_size,
        model_type="bpe",
        character_coverage=1.0,
        byte_fallback=True,
        normalization_rule_name="identity",
        add_dummy_prefix=False,
        split_digits=True,
        max_sentence_length=16384,
        num_threads=max(1, os.cpu_count() or 1),
        shuffle_input_sentence=True,
        hard_vocab_limit=False,
        pad_id=0,
        unk_id=1,
        bos_id=2,
        eos_id=3,
        pad_piece="<pad>",
        unk_piece="<unk>",
        bos_piece="<s>",
        eos_piece="<|bankvn_end|>",
        user_defined_symbols=SPECIAL_TOKENS[4:],
    )
    sp_input.unlink(missing_ok=True)

    hf = TokenizersBackend.from_pretrained(
        out,
        bos_token="<s>", eos_token="<|bankvn_end|>",
        unk_token="<unk>", pad_token="<pad>",
        extra_special_tokens=SPECIAL_TOKENS[4:],
        model_max_length=4096,
    )
    hf.save_pretrained(out)
    ensure_bankvn_tokenizer_config(out)
    print(json.dumps({"output": str(out), "vocab_size": len(hf), "documents": docs,
                      "format": "sentencepiece_bpe",
                      "special_tokens": SPECIAL_TOKENS}, ensure_ascii=False))


if __name__ == "__main__":
    main()
