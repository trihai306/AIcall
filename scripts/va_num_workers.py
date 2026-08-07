"""Hạ num_workers của F5-TTS trainer xuống mức Windows chịu được.

LỖI ĐƯỢC VÁ:

    RuntimeError: DataLoader worker (pid(s) ...) exited unexpectedly

F5-TTS đặt mặc định num_workers=16 trong model/trainer.py, và finetune_cli.py
gọi trainer.train() mà không truyền tham số này nên không có cách nào đổi từ
dòng lệnh.

PyTorch sinh LẠI toàn bộ tiến trình nạp dữ liệu ở ĐẦU MỖI EPOCH. Trên Linux
việc này rẻ vì dùng fork; trên Windows mỗi worker là một tiến trình mới hoàn
chỉnh phải nạp lại Python và toàn bộ thư viện. 16 tiến trình sinh lại mỗi epoch
là quá sức - đo thực tế: chạy trót lọt 2 epoch rồi chết ở lần sinh thứ ba.

Không phải do thiếu RAM: lúc chết máy còn trống 41.5 GB.

Vá bằng cách sửa thẳng lời gọi trong finetune_cli.py. Idempotent - chạy nhiều
lần không hỏng, và tự vá lại nếu ai đó clone mới F5-TTS.

    python scripts/va_num_workers.py [--workers 2]
"""
import argparse
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

PROJECT_DIR = Path(__file__).resolve().parent.parent
CLI = PROJECT_DIR / "tools" / "F5-TTS-Vietnamese" / "src" / "f5_tts" / "train" / "finetune_cli.py"

# trainer.train(train_dataset, resumable_with_seed=666,)  ->  thêm num_workers
_GOI = re.compile(r"(trainer\.train\(\s*\n\s*train_dataset,)", re.MULTILINE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=2,
                    help="Số tiến trình nạp dữ liệu. 0 = nạp trong tiến trình chính, "
                         "chậm hơn nhưng chắc chắn nhất.")
    args = ap.parse_args()

    if not CLI.exists():
        print(f"[BO QUA] Khong thay {CLI}")
        return

    src = CLI.read_text(encoding="utf-8")

    if "num_workers=" in src:
        hien = re.search(r"num_workers=(\d+)", src)
        print(f"  da va roi (num_workers={hien.group(1) if hien else '?'}) - bo qua")
        return

    moi, n = _GOI.subn(rf"\1\n        num_workers={args.workers},", src)
    if n == 0:
        print("[CANH BAO] Khong tim thay loi goi trainer.train() de va.")
        print("           Neu train chet vi 'DataLoader worker exited', sua tay:")
        print(f"           {CLI} -> them num_workers={args.workers} vao trainer.train()")
        return

    CLI.write_text(moi, encoding="utf-8")
    print(f"  da va: trainer.train(..., num_workers={args.workers})")


if __name__ == "__main__":
    main()
