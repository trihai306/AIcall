"""Đặt lại bộ đếm bước của checkpoint gốc về 0 để fine-tune thật sự chạy.

trainer.py coi checkpoint nạp vào là "đang train dở": start_update lấy từ
checkpoint (540000 của bản ViVoice), rồi skipped_epoch = start_update // steps
vượt xa số epoch nên vòng lặp train không chạy lần nào - nó lưu lại y nguyên
model gốc rồi báo "train xong" sau hai phút.

CHỈ đổi trường 'update'. Đã thử gỡ optimizer_state_dict/scheduler_state_dict thì
load_checkpoint() ném KeyError vì nó đọc thẳng hai khoá đó, không kiểm tra.

    python scripts/reset_update.py
    python scripts/reset_update.py --src <ckpt goc> --dst <ckpt xuat>
"""

import argparse
import os
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = PROJECT / "models" / "tts" / "F5-TTS-Vietnamese-ViVoice"


def main() -> int:
    import torch

    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(DEFAULT_DIR / "model_last.pt"))
    ap.add_argument("--dst", default=str(DEFAULT_DIR / "model_finetune_start.pt"))
    args = ap.parse_args()

    src, dst = Path(args.src), Path(args.dst)
    if not src.exists():
        print(f"[!] Không thấy checkpoint gốc: {src}")
        return 1
    if dst.exists():
        print(f"  đã có {dst.name}, bỏ qua")
        return 0

    ck = torch.load(str(src), map_location="cpu", weights_only=False)
    print("  khoá:", list(ck.keys()))
    print("  update: %s -> 0" % ck.get("update"))
    ck["update"] = 0
    torch.save(ck, str(dst))
    print("  đã ghi: %s  %.0f MB" % (dst, os.path.getsize(dst) / 1024 / 1024))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
