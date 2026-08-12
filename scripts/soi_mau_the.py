import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
F = Path("C:/duan/chat-ai/data/training/dataset_co_tai_lieu.jsonl")
mau = [json.loads(l) for l in F.read_text(encoding="utf-8").splitlines() if l.strip()]

for m in mau:
    hoi = next(t["content"] for t in m["messages"] if t["role"] == "user")
    if hoi not in ("thẻ platinum thế nào", "thẻ gold phí bao nhiêu"):
        continue
    sysp = next(t["content"] for t in m["messages"] if t["role"] == "system")
    dap = next(t["content"] for t in m["messages"] if t["role"] == "assistant")
    i = sysp.find("THÔNG TIN THAM KHẢO")
    ctx = sysp[i:] if i >= 0 else "(KHÔNG CÓ)"
    print("=" * 72)
    print(f"HỎI: {hoi}")
    print(f"ĐÁP: {dap}")
    print(f"\nNGỮ CẢNH RAG LẤY VỀ:\n{ctx[:900]}")
    print(f"\n-> ngữ cảnh có '800.000': {'800.000' in ctx}")
    print(f"-> ngữ cảnh có '400.000': {'400.000' in ctx}")
    print(f"-> ngữ cảnh có 'Platinum': {'Platinum' in ctx}")
    print(f"-> ngữ cảnh có 'Gold': {'Gold' in ctx}")
