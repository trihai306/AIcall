"""Mẫu train có kèm TÀI LIỆU không, hay bắt mô hình trả lời từ trí nhớ?

Đây là câu hỏi quyết định. Nếu prompt lúc train KHÔNG có tài liệu, mô hình học
được rằng "câu trả lời nằm trong đầu mình" - và khi chạy thật ta đưa tài liệu
vào thì nó vẫn bỏ qua, vì chưa bao giờ được dạy cách đọc.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
F = Path("C:/duan/chat-ai/data/training/merged_dataset.jsonl")
mau = [json.loads(l) for l in F.read_text(encoding="utf-8").splitlines() if l.strip()]

print(f"  {len(mau)} mẫu\n")
print("  === MẪU ĐẦU TIÊN, NGUYÊN VĂN ===")
for tn in mau[0]["messages"]:
    print(f"    [{tn['role']}] {tn['content'][:200]}")

# system prompt có bao nhiêu dạng khác nhau?
sysp = Counter(t["content"] for m in mau for t in m["messages"] if t["role"] == "system")
print(f"\n  === CÓ {len(sysp)} DẠNG SYSTEM PROMPT ===")
for s, n in sysp.most_common(3):
    print(f"    {n:>4} mẫu: {s[:150]!r}")

# có mẫu nào chứa tài liệu tham khảo không?
dau_hieu = ("THÔNG TIN THAM KHẢO", "TÀI LIỆU", "Lãi suất:", "## Thông tin sản phẩm",
            "Hạn mức:")
co_tl = sum(any(d in t["content"] for d in dau_hieu)
            for m in mau for t in m["messages"] if t["role"] == "system")
print(f"\n  === MẪU CÓ KÈM TÀI LIỆU TRONG PROMPT ===")
print(f"    {co_tl} / {len(mau)}")
if co_tl == 0:
    print("    -> KHÔNG mẫu nào. Mô hình được dạy trả lời TỪ TRÍ NHỚ,")
    print("       chưa bao giờ được dạy ĐỌC TÀI LIỆU rồi mới trả lời.")

# mẫu nói về sản phẩm nào
sp = Counter()
for m in mau:
    t = " ".join(x["content"] for x in m["messages"]).lower()
    for ten in ("vay tín chấp", "vay mua nhà", "thẻ tín dụng", "tiết kiệm"):
        if ten in t:
            sp[ten] += 1
print(f"\n  === MẪU NHẮC TỚI TỪNG SẢN PHẨM ===")
for ten, n in sp.most_common():
    print(f"    {n:>4}  {ten}")
