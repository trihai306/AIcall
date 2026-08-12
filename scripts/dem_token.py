"""Mẫu có vượt MAX_SEQ_LEN không? Vượt thì phần bị cắt là CÂU TRẢ LỜI."""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
MAX = 2048
F = Path("C:/duan/chat-ai/data/training/dataset_co_tai_lieu.jsonl")

from transformers import AutoTokenizer
tok = AutoTokenizer.from_pretrained("C:/duan/chat-ai/models/llm/tuvan-lora")

mau = [json.loads(l) for l in F.read_text(encoding="utf-8").splitlines() if l.strip()]

# apply_chat_template(tokenize=True) trả kiểu khác nhau tuỳ phiên bản; lấy CHUỖI
# rồi tự mã hoá cho chắc - lần trước tin thẳng vào nó thì ra 2 token cho mọi mẫu.
chuoi = tok.apply_chat_template(mau[0]["messages"], tokenize=False)
print(f"  kiểm nhanh: mẫu đầu dài {len(chuoi)} ký tự -> "
      f"{len(tok.encode(chuoi))} token\n")

dai = sorted(len(tok.encode(tok.apply_chat_template(m["messages"], tokenize=False)))
             for m in mau)
n = len(dai)
print(f"  {n} mẫu | MAX_SEQ_LEN = {MAX}")
print(f"    ngắn nhất  {dai[0]}")
print(f"    trung vị   {dai[n // 2]}")
print(f"    p90        {dai[int(n * 0.9)]}")
print(f"    dài nhất   {dai[-1]}")
vuot = sum(1 for d in dai if d > MAX)
print(f"\n    vượt {MAX}: {vuot}/{n}  "
      f"{'-> AN TOÀN' if vuot == 0 else '-> BỊ CẮT, PHẢI SỬA'}")
if vuot:
    print(f"    cần MAX_SEQ_LEN >= {dai[-1]}")
