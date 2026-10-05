#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

try:
    from .common import require_bankvn_tokenizer_files
except ImportError:
    from common import require_bankvn_tokenizer_files


ROOT = Path(__file__).resolve().parents[2]

GGUF_USER_DEFINED_MARKERS = ("<|bankvn_end|>",)
DEFAULT_GGUF_CONVERTER = "training/bankvn/convert_hf_to_gguf_bankvn.py"
BANKVN_GGUF_SPECIALS = {
    3: "<|bankvn_end|>",
    4: "<|bankvn_system|>",
    5: "<|bankvn_user|>",
    6: "<|bankvn_assistant|>",
    7: "<|bankvn_tool_call|>",
    8: "<|bankvn_tool_result|>",
}
GGUF_TOKEN_TYPE_USER_DEFINED = 4


def modelfile_text(gguf_path: Path, num_ctx: int, temperature: float) -> str:
    return f'''FROM "{gguf_path.resolve()}"

TEMPLATE """{{{{- if .Messages }}}}{{{{- range .Messages }}}}{{{{- if eq .Role "system" }}}}<|bankvn_system|>{{{{ .Content }}}}<|bankvn_end|>{{{{- else if eq .Role "user" }}}}<|bankvn_user|>{{{{ .Content }}}}<|bankvn_end|>{{{{- else if eq .Role "assistant" }}}}<|bankvn_assistant|>{{{{ .Content }}}}<|bankvn_end|>{{{{- else if eq .Role "tool" }}}}<|bankvn_tool_result|>{{{{ .Content }}}}<|bankvn_end|>{{{{- end }}}}{{{{- end }}}}<|bankvn_assistant|>{{{{- else }}}}<|bankvn_system|>{{{{ .System }}}}<|bankvn_end|><|bankvn_user|>{{{{ .Prompt }}}}<|bankvn_end|><|bankvn_assistant|>{{{{- end }}}}"""

PARAMETER stop "<|bankvn_end|>"
PARAMETER num_ctx {num_ctx}
PARAMETER temperature {temperature}
'''


def resolve_from_root(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else ROOT / path


def _patched_sentencepiece_for_gguf(model_path: Path) -> bytes:
    """Đổi metadata token cho llama.cpp mà không đụng ID/tokenizer train.

    Giữ nguyên loại token của các marker role/tool từ checkpoint. Chỉ đổi
    bankvn_end sang USER_DEFINED để literal trong template Ollama được
    SentencePiece encode đúng thành token ID 3.
    """
    try:
        from sentencepiece import sentencepiece_model_pb2 as model_pb2
    except ImportError as exc:
        raise RuntimeError("Export GGUF BankVN cần package sentencepiece") from exc

    proto = model_pb2.ModelProto()
    proto.ParseFromString(model_path.read_bytes())
    by_piece = {piece.piece: i for i, piece in enumerate(proto.pieces)}

    for marker in GGUF_USER_DEFINED_MARKERS:
        if marker not in by_piece:
            raise RuntimeError(f"tokenizer.model thiếu marker BankVN: {marker}")
        proto.pieces[by_piece[marker]].type = model_pb2.ModelProto.SentencePiece.USER_DEFINED

    return proto.SerializeToString()


def _hf_appended_tokens(model_dir: Path) -> dict[int, str]:
    """Lấy các token HF được append ngoài vocab SentencePiece gốc."""
    tokenizer_model = model_dir / "tokenizer.model"
    tokenizer_json = model_dir / "tokenizer.json"
    if not tokenizer_model.is_file() or not tokenizer_json.is_file():
        return {}
    try:
        from sentencepiece import sentencepiece_model_pb2 as model_pb2
    except ImportError as exc:
        raise RuntimeError("Export GGUF BankVN cần package sentencepiece") from exc

    proto = model_pb2.ModelProto()
    proto.ParseFromString(tokenizer_model.read_bytes())
    base_vocab_size = len(proto.pieces)
    payload = json.loads(tokenizer_json.read_text(encoding="utf-8"))
    expected: dict[int, str] = {}
    for item in payload.get("added_tokens") or []:
        if not isinstance(item, dict):
            continue
        token_id = item.get("id")
        content = item.get("content")
        if isinstance(token_id, int) and token_id >= base_vocab_size and isinstance(content, str):
            expected[token_id] = content
    return expected


def _hardlink_or_copy(src: str, dst: str) -> None:
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


@contextmanager
def staged_model_for_gguf(model_dir: Path) -> Iterator[Path]:
    """Stage checkpoint bằng hardlink rồi chỉ sửa tokenizer.model của bản stage."""
    with tempfile.TemporaryDirectory(prefix=".bankvn-gguf-", dir=model_dir.parent) as tmp:
        staged = Path(tmp) / "model"
        shutil.copytree(model_dir, staged, copy_function=_hardlink_or_copy)
        staged_sp = staged / "tokenizer.model"
        patched = _patched_sentencepiece_for_gguf(staged_sp)
        # tokenizer.model đang là hardlink: unlink trước khi ghi để không sửa
        # checkpoint nguồn.
        staged_sp.unlink()
        staged_sp.write_bytes(patched)
        yield staged


def convert_to_gguf(model_dir: Path, converter: Path, gguf_path: Path,
                    outtype: str) -> None:
    if not converter.exists():
        raise SystemExit(f"[ERROR] Không thấy llama.cpp converter: {converter}")
    gguf_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(converter),
        str(model_dir),
        "--outfile", str(gguf_path),
        "--outtype", outtype,
    ]
    print("[RUN]", " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=str(ROOT))
    if proc.returncode != 0:
        raise SystemExit(f"[ERROR] convert_hf_to_gguf thất bại: {proc.returncode}")
    if not gguf_path.exists() or gguf_path.stat().st_size == 0:
        raise SystemExit(f"[ERROR] Converter không tạo GGUF hợp lệ: {gguf_path}")


def validate_bankvn_gguf(gguf_path: Path,
                         appended_tokens: dict[int, str] | None = None) -> None:
    """Chặn GGUF làm mất semantics USER_DEFINED của marker BankVN."""
    gguf_py = ROOT / "tools" / "llama.cpp" / "gguf-py"
    if gguf_py.is_dir() and str(gguf_py) not in sys.path:
        sys.path.insert(0, str(gguf_py))
    try:
        import gguf
    except ImportError as exc:
        raise RuntimeError(
            "Không import được gguf để kiểm tra tokenizer metadata"
        ) from exc

    reader = gguf.GGUFReader(str(gguf_path))
    fields = {field.name: field for field in reader.fields.values()}
    tokens = fields["tokenizer.ggml.tokens"].contents()
    token_types = fields["tokenizer.ggml.token_type"].contents()
    errors = []
    for token_id, marker in BANKVN_GGUF_SPECIALS.items():
        actual_marker = tokens[token_id] if token_id < len(tokens) else None
        actual_type = token_types[token_id] if token_id < len(token_types) else None
        if actual_marker != marker or actual_type != GGUF_TOKEN_TYPE_USER_DEFINED:
            errors.append(
                f"id={token_id}: token={actual_marker!r}, type={actual_type}; "
                f"cần token={marker!r}, type={GGUF_TOKEN_TYPE_USER_DEFINED}"
            )
    for token_id, marker in sorted((appended_tokens or {}).items()):
        actual_marker = tokens[token_id] if token_id < len(tokens) else None
        actual_type = token_types[token_id] if token_id < len(token_types) else None
        if actual_marker != marker or actual_type != GGUF_TOKEN_TYPE_USER_DEFINED:
            errors.append(
                f"added id={token_id}: token={actual_marker!r}, type={actual_type}; "
                f"cần token={marker!r}, type={GGUF_TOKEN_TYPE_USER_DEFINED}"
            )
    if errors:
        raise SystemExit("[ERROR] GGUF BankVN sai special-token metadata: " + "; ".join(errors))


def set_env(model_name: str) -> None:
    env = ROOT / ".env"
    if not env.exists():
        raise SystemExit(f"[ERROR] Không thấy {env}")
    text = env.read_text(encoding="utf-8-sig")
    lines, found = [], False
    for line in text.splitlines():
        if re.match(r"^\s*OLLAMA_MODEL\s*=", line):
            lines.append(f"OLLAMA_MODEL={model_name}")
            found = True
        else:
            lines.append(line)
    if not found:
        lines.append(f"OLLAMA_MODEL={model_name}")
    env.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")


def main() -> None:
    ap = argparse.ArgumentParser(description="Đổi checkpoint BankVN sang GGUF rồi nạp vào Ollama")
    ap.add_argument("--model-dir", required=True)
    ap.add_argument("--name", default="bankvn-candidate")
    ap.add_argument("--num-ctx", type=int, default=4096)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--converter", default=DEFAULT_GGUF_CONVERTER)
    ap.add_argument("--gguf", default="",
                    help="Đường dẫn GGUF đầu ra; mặc định models/bankvn/gguf/<name>-<outtype>.gguf")
    ap.add_argument("--outtype", default="f16",
                    help="Kiểu GGUF do llama.cpp converter hỗ trợ, mặc định f16")
    ap.add_argument("--skip-convert", action="store_true",
                    help="Dùng GGUF đã có, không chạy converter")
    ap.add_argument("--convert-only", action="store_true",
                    help="Chỉ tạo GGUF để smoke/kiểm tra, chưa tạo model Ollama")
    ap.add_argument("--set-env", action="store_true",
                    help="Chỉ dùng sau khi candidate đã qua benchmark gate")
    ap.add_argument(
        "--ollama-host",
        default="",
        help=(
            "Ollama đích, ví dụ 127.0.0.1:11435 cho runtime test CPU. "
            "Để trống thì dùng OLLAMA_HOST hiện tại."
        ),
    )
    args = ap.parse_args()

    model_dir = resolve_from_root(args.model_dir)
    if not (model_dir / "config.json").exists():
        raise SystemExit(f"[ERROR] Không phải checkpoint HF hợp lệ: {model_dir}")
    require_bankvn_tokenizer_files(model_dir)
    appended_tokens = _hf_appended_tokens(model_dir)
    converter = resolve_from_root(args.converter)
    gguf_path = (resolve_from_root(args.gguf) if args.gguf else
                 ROOT / "models" / "bankvn" / "gguf" / f"{args.name}-{args.outtype}.gguf")
    if args.skip_convert:
        if not gguf_path.exists() or gguf_path.stat().st_size == 0:
            raise SystemExit(f"[ERROR] --skip-convert nhưng không thấy GGUF: {gguf_path}")
    else:
        with staged_model_for_gguf(model_dir) as staged_model:
            convert_to_gguf(staged_model, converter, gguf_path, args.outtype)

    validate_bankvn_gguf(gguf_path, appended_tokens)

    print(f"[OK] GGUF: {gguf_path}")
    if args.convert_only:
        if args.set_env:
            raise SystemExit("[ERROR] --set-env không dùng cùng --convert-only")
        return

    out_dir = ROOT / "models" / "bankvn" / "ollama"
    out_dir.mkdir(parents=True, exist_ok=True)
    modelfile = out_dir / f"Modelfile.{args.name}"
    modelfile.write_text(modelfile_text(gguf_path, args.num_ctx, args.temperature),
                         encoding="utf-8")
    ollama_env = os.environ.copy()
    if args.ollama_host:
        ollama_env["OLLAMA_HOST"] = args.ollama_host
    proc = subprocess.run(
        ["ollama", "create", args.name, "-f", str(modelfile)],
        cwd=str(ROOT),
        env=ollama_env,
    )
    if proc.returncode != 0:
        raise SystemExit(f"[ERROR] ollama create thất bại: {proc.returncode}")
    if args.set_env:
        set_env(args.name)
        print(f"[OK] .env -> OLLAMA_MODEL={args.name}")
    print(f"[OK] Ollama model: {args.name}")


if __name__ == "__main__":
    main()
