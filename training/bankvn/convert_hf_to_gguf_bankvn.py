#!/usr/bin/env python3
from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

from sentencepiece import sentencepiece_model_pb2 as model_pb2


ROOT = Path(__file__).resolve().parents[2]
LLAMA_CPP = ROOT / "tools" / "llama.cpp"
CONVERTER = LLAMA_CPP / "convert_hf_to_gguf.py"

sys.path.insert(0, str(LLAMA_CPP))

from conversion.base import ModelBase, SentencePieceTokenTypes, TextModel  # noqa: E402


BANKVN_END = "<|bankvn_end|>"


def _load_added_tokens(model_dir: Path) -> dict[int, str]:
    """Đọc added token của HF để GGUF giữ đúng vocab mở rộng sau SFT."""
    tokenizer_json = model_dir / "tokenizer.json"
    if not tokenizer_json.is_file():
        return {}
    payload = json.loads(tokenizer_json.read_text(encoding="utf-8"))
    added: dict[int, str] = {}
    for item in payload.get("added_tokens") or []:
        if not isinstance(item, dict):
            continue
        token_id = item.get("id")
        content = item.get("content")
        if isinstance(token_id, int) and isinstance(content, str) and content:
            added[token_id] = content
    return added


def _create_bankvn_sentencepiece(self: ModelBase):
    """Giữ SentencePiece gốc và ghép added tokens HF theo đúng token ID."""
    tokenizer_path = self.dir_model / "tokenizer.model"
    if not tokenizer_path.is_file():
        raise FileNotFoundError(f"File not found: {tokenizer_path}")

    proto = model_pb2.ModelProto()
    proto.ParseFromString(tokenizer_path.read_bytes())
    vocab_size = int(self.hparams.get("vocab_size") or len(proto.pieces))
    tokens: list[bytes] = [f"[PAD{i}]".encode("utf-8") for i in range(vocab_size)]
    scores: list[float] = [-10000.0] * vocab_size
    toktypes: list[int] = [SentencePieceTokenTypes.UNUSED] * vocab_size
    type_map = {
        model_pb2.ModelProto.SentencePiece.NORMAL: SentencePieceTokenTypes.NORMAL,
        model_pb2.ModelProto.SentencePiece.UNKNOWN: SentencePieceTokenTypes.UNKNOWN,
        model_pb2.ModelProto.SentencePiece.CONTROL: SentencePieceTokenTypes.CONTROL,
        model_pb2.ModelProto.SentencePiece.USER_DEFINED: SentencePieceTokenTypes.USER_DEFINED,
        model_pb2.ModelProto.SentencePiece.UNUSED: SentencePieceTokenTypes.UNUSED,
        model_pb2.ModelProto.SentencePiece.BYTE: SentencePieceTokenTypes.BYTE,
    }

    for token_id, piece in enumerate(proto.pieces[:vocab_size]):
        tokens[token_id] = piece.piece.encode("utf-8")
        scores[token_id] = float(piece.score)
        toktype = type_map[piece.type]
        if piece.piece == BANKVN_END:
            toktype = SentencePieceTokenTypes.USER_DEFINED
        toktypes[token_id] = toktype

    base_vocab_size = len(proto.pieces)
    for token_id, content in _load_added_tokens(self.dir_model).items():
        if base_vocab_size <= token_id < vocab_size:
            tokens[token_id] = content.encode("utf-8")
            scores[token_id] = 0.0
            toktypes[token_id] = SentencePieceTokenTypes.USER_DEFINED

    return tokens, scores, toktypes


# llama.cpp hiện định nghĩa implementation này ở TextModel, vì vậy patch
# ModelBase riêng lẻ sẽ bị TextModel._create_vocab_sentencepiece che mất.
ModelBase._create_vocab_sentencepiece = _create_bankvn_sentencepiece
TextModel._create_vocab_sentencepiece = _create_bankvn_sentencepiece

if not CONVERTER.is_file():
    raise SystemExit(f"[ERROR] Không thấy llama.cpp converter: {CONVERTER}")

runpy.run_path(str(CONVERTER), run_name="__main__")
