"""Con số sai có nằm trong DỮ LIỆU TRAIN không?

Nếu có thì mô hình không hề "đọc nhầm" - nó đang nhớ đúng thứ đã được dạy, và
thứ đó mâu thuẫn với tài liệu RAG. Đó là lỗi thiết kế dữ liệu, không phải lỗi
suy luận, và cách chữa hoàn toàn khác.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
F = Path("C:/duan/chat-ai/data/training/merged_dataset.jsonl")

dong = [json.loads(l) for l in F.read_text(encoding="utf-8").splitlines() if l.strip()]
print(f"  {F.name}: {len(dong)} mẫu\n")
print(f"  khoá của mẫu đầu: {list(dong[0].keys())}")

def chu(m):
    """Gom toàn bộ chữ trong một mẫu, bất kể định dạng."""
    if "messages" in m:
        return " ".join(x.get("content", "") for x in m["messages"])
    return " ".join(str(v) for v in m.values() if isinstance(v, str))

toan = [chu(m) for m in dong]

# --- mọi con số PHẦN TRĂM xuất hiện trong dữ liệu train ---
PT = re.compile(r"(\d+[.,]\d+)\s*%|(\d+[.,]\d+)\s*(?:phần trăm|%/năm)|"
                r"((?:một|hai|ba|bốn|năm|sáu|bảy|tám|chín)\s+phẩy\s+"
                r"(?:một|hai|ba|bốn|năm|sáu|bảy|tám|chín))", re.I)
dem = Counter()
for t in toan:
    for m in PT.finditer(t):
        dem[(m.group(1) or m.group(2) or m.group(3)).strip().lower()] += 1

print(f"\n  === CÁC CON SỐ PHẦN TRĂM TRONG DỮ LIỆU TRAIN ===")
if not dem:
    print("    (không có con số phần trăm nào)")
for so, n in dem.most_common(12):
    print(f"    {n:>4} lần   {so}")

# --- so với tài liệu RAG ---
kho = Path("C:/duan/chat-ai/knowledge")
tl = " ".join(p.read_text(encoding="utf-8") for p in kho.rglob("*.md"))
dem_tl = Counter(m.group(0) for m in re.finditer(r"\d+[.,]\d+\s*%", tl))
print(f"\n  === TRONG TÀI LIỆU RAG ===")
for so, n in dem_tl.most_common(12):
    print(f"    {n:>4} lần   {so}")

# --- mẫu nào nhắc tới lãi suất ---
print(f"\n  === VÀI MẪU TRAIN CÓ CHỮ 'lãi suất' ===")
k = 0
for t in toan:
    if "lãi suất" in t.lower() and k < 5:
        s = re.sub(r"\s+", " ", t)
        i = s.lower().find("lãi suất")
        print(f"    ...{s[max(0,i-60):i+110]}...")
        k += 1
