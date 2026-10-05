#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import unicodedata
from pathlib import Path

import sentencepiece as spm
from transformers import TokenizersBackend

from common import SPECIAL_TOKENS


REQUIRED_FILES = (
    "tokenizer.model",
    "tokenizer.vocab",
    "tokenizer.json",
    "tokenizer_config.json",
)

SAMPLES = (
    "Khách hàng cần kiểm tra hạn mức thẻ tín dụng và lịch thanh toán.",
    "ATM OTP KYC CIC Visa API JSON",
    "Lãi suất khoản vay được tính theo dư nợ thực tế của khách hàng.",
)


def normalized(text: str) -> str:
    return unicodedata.normalize("NFC", text).strip()


def main() -> None:
    ap = argparse.ArgumentParser(description="Smoke test tokenizer SentencePiece của BankVN")
    ap.add_argument("--tokenizer", default="models/bankvn/tokenizer")
    args = ap.parse_args()

    root = Path(args.tokenizer)
    missing = [name for name in REQUIRED_FILES if not (root / name).exists()]
    if missing:
        raise SystemExit(f"[ERROR] Tokenizer thiếu file: {missing}")

    config = json.loads((root / "tokenizer_config.json").read_text(encoding="utf-8"))
    if config.get("add_prefix_space") is not False:
        raise SystemExit(
            "[ERROR] tokenizer_config.json phải có add_prefix_space=false để "
            "llama.cpp/GGUF giữ đúng add_dummy_prefix=False"
        )

    tokenizer = TokenizersBackend.from_pretrained(root)
    sentencepiece = spm.SentencePieceProcessor(model_file=str(root / "tokenizer.model"))
    ids = {token: tokenizer.convert_tokens_to_ids(token) for token in SPECIAL_TOKENS}
    expected = {token: i for i, token in enumerate(SPECIAL_TOKENS)}
    if ids != expected:
        raise SystemExit(f"[ERROR] Special token ID sai: expected={expected}, actual={ids}")

    if sentencepiece.get_piece_size() != len(tokenizer):
        raise SystemExit(
            "[ERROR] Vocab HF/SentencePiece khác kích thước: "
            f"hf={len(tokenizer)}, sp={sentencepiece.get_piece_size()}"
        )
    vocab_mismatch = [
        (i, tokenizer.convert_ids_to_tokens(i), sentencepiece.id_to_piece(i))
        for i in range(len(tokenizer))
        if tokenizer.convert_ids_to_tokens(i) != sentencepiece.id_to_piece(i)
    ]
    if vocab_mismatch:
        raise SystemExit(f"[ERROR] Vocab HF/SentencePiece lệch ID: {vocab_mismatch[:10]}")

    marker_checks = {}
    for marker in SPECIAL_TOKENS[3:]:
        encoded = tokenizer.encode(marker, add_special_tokens=False)
        marker_checks[marker] = encoded
        if encoded != [ids[marker]]:
            raise SystemExit(f"[ERROR] Marker không còn là 1 token: {marker} -> {encoded}")

    roundtrips = []
    for sample in SAMPLES:
        encoded = tokenizer.encode(sample, add_special_tokens=False)
        sp_encoded = sentencepiece.encode(sample, out_type=int)
        if encoded != sp_encoded:
            raise SystemExit(
                "[ERROR] HF/SentencePiece encode khác nhau: "
                f"text={sample!r}, hf={encoded}, sp={sp_encoded}"
            )
        decoded = tokenizer.decode(encoded, skip_special_tokens=False)
        if "�" in decoded:
            raise SystemExit(f"[ERROR] Decode có ký tự lỗi: {decoded!r}")
        if normalized(decoded) != normalized(sample):
            raise SystemExit(
                f"[ERROR] Round-trip sai: input={sample!r}, decoded={decoded!r}"
            )
        roundtrips.append({"text": sample, "tokens": len(encoded)})

    print(json.dumps({
        "status": "ok",
        "tokenizer": str(root),
        "vocab_size": len(tokenizer),
        "special_token_ids": ids,
        "add_prefix_space": config["add_prefix_space"],
        "markers": marker_checks,
        "roundtrips": roundtrips,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
