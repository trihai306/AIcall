"""Đổi F5TTS_NFE_STEP_FIRST tại chỗ trên máy Win, giữ nguyên phần còn lại."""
import argparse
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ap = argparse.ArgumentParser()
ap.add_argument("value", type=int, nargs="?", default=16)
args = ap.parse_args()
if args.value < 4:
    raise SystemExit("NFE phải >= 4")

p = Path(r"C:\duan\chat-ai\.env")
t = p.read_text(encoding="utf-8")
cu = re.search(r"^F5TTS_NFE_STEP_FIRST=(\S+)", t, re.M)
print("trước:", cu.group(0) if cu else "(không có dòng nào)")
if cu and cu.group(1) == str(args.value):
    print(f"đã là {args.value}, không đổi")
    raise SystemExit

dong = (
    f"F5TTS_NFE_STEP_FIRST={args.value}   # 11-09: ưu tiên chất lượng; "
    "heu_a6_35 nfe16 sạch 3/3, nfe12 vượt đỉnh 1/3"
)
t2 = re.sub(r"^F5TTS_NFE_STEP_FIRST=.*$", dong, t, count=1, flags=re.M)
if t2 == t:
    t2 = t.rstrip("\n") + "\n" + dong + "\n"
p.write_text(t2, encoding="utf-8")
print("sau  :", re.search(r"^F5TTS_NFE_STEP_FIRST=.*", p.read_text(encoding="utf-8"), re.M).group(0))
