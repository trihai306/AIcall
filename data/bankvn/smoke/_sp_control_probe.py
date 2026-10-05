import argparse
import shutil
from pathlib import Path

from sentencepiece import sentencepiece_model_pb2 as model_pb2


MARKERS = [
    "<|bankvn_system|>",
    "<|bankvn_user|>",
    "<|bankvn_assistant|>",
    "<|bankvn_tool_result|>",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--restore", action="store_true")
    args = ap.parse_args()

    path = Path(args.model)
    backup = path.with_name(path.name + ".before-control-probe")
    if args.restore:
        if not backup.exists():
            raise SystemExit(f"backup not found: {backup}")
        shutil.copy2(backup, path)
        backup.unlink()
        print(f"restored {path}")
        return

    if not backup.exists():
        shutil.copy2(path, backup)

    proto = model_pb2.ModelProto()
    proto.ParseFromString(path.read_bytes())
    by_piece = {piece.piece: i for i, piece in enumerate(proto.pieces)}
    for marker in MARKERS:
        idx = by_piece[marker]
        proto.pieces[idx].type = model_pb2.ModelProto.SentencePiece.CONTROL
        print(idx, marker, int(proto.pieces[idx].type))
    path.write_bytes(proto.SerializeToString())


if __name__ == "__main__":
    main()
