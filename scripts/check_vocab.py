"""Đối chiếu ký tự trong transcript với vocab của model gốc.

F5-TTS không báo lỗi khi gặp ký tự lạ - nó lặng lẽ bỏ qua, nên câu train bị
thiếu chữ mà không ai biết. Kiểm tra trước cho chắc.

Trước đây đoạn này được nhúng thẳng vào here-string của PowerShell trong
train.ps1; PowerShell nuốt mất dấu xuống dòng và Python báo
"SyntaxError: unexpected character after line continuation character".
Tách ra file riêng thì hết.
"""

import sys
from collections import Counter
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT = Path(__file__).resolve().parent.parent
F5DIR = PROJECT / "tools" / "F5-TTS-Vietnamese"
META = F5DIR / "data" / "your_training_dataset" / "metadata.csv"
VOCAB = F5DIR / "data" / "your_training_dataset" / "vocab.txt"


def main() -> int:
    if not META.exists():
        print(f"[!] Chưa có {META} - bỏ qua bước kiểm tra vocab")
        return 0
    if not VOCAB.exists():
        print(f"[!] Chưa có {VOCAB} - bỏ qua bước kiểm tra vocab")
        return 0

    # vocab.txt: mỗi dòng một token. Dòng trống chính là ký tự khoảng trắng,
    # nên đọc thô, không strip cả dòng.
    voc = set()
    for line in VOCAB.read_text(encoding="utf-8").split("\n"):
        if line == "":
            continue
        voc.add(line)
    voc.add(" ")

    thieu = Counter()
    so_cau = 0
    for line in META.read_text(encoding="utf-8").splitlines():
        if "|" not in line:
            continue
        so_cau += 1
        text = line.split("|", 1)[1]
        for ch in text:
            if ch not in voc:
                thieu[ch] += 1

    print(f"  vocab: {len(voc)} token | transcript: {so_cau} câu")
    if not thieu:
        print("  OK - mọi ký tự đều nằm trong vocab")
        return 0

    print(f"  [!] {len(thieu)} ký tự KHÔNG có trong vocab (sẽ bị bỏ khi train):")
    for ch, n in thieu.most_common(20):
        print(f"      {ch!r}  U+{ord(ch):04X}  xuất hiện {n} lần")
    print("  -> Sửa transcript cho sạch, hoặc chấp nhận mất các ký tự này.")
    return 0  # cảnh báo thôi, không chặn train


if __name__ == "__main__":
    raise SystemExit(main())
