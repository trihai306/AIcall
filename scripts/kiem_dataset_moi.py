"""Kiểm bộ dữ liệu mới TRƯỚC KHI train - train xong mới phát hiện sai thì mất vài giờ."""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
F = Path("C:/duan/chat-ai/data/training/dataset_co_tai_lieu.jsonl")
mau = [json.loads(l) for l in F.read_text(encoding="utf-8").splitlines() if l.strip()]

def lay(m, vai):
    return next((t["content"] for t in m["messages"] if t["role"] == vai), "")

print(f"  {len(mau)} mẫu\n")

# 1. có tài liệu không
co_tl = sum("THÔNG TIN THAM KHẢO" in lay(m, "system") for m in mau)
print(f"  1) mẫu có TÀI LIỆU trong prompt : {co_tl}/{len(mau)}"
      f"   {'ĐẠT' if co_tl == len(mau) else 'THIẾU!'}")

# 2. mọi con số trong câu trả lời phải có trong tài liệu của CHÍNH mẫu đó
SO = re.compile(r"\d+(?:[.,]\d+)?")
xau = []
for m in mau:
    tl, dap = lay(m, "system"), lay(m, "assistant")
    tl_so = set(SO.findall(tl))
    for s in SO.findall(dap):
        # bỏ qua số nhỏ hay dùng trong lời nói thường (1, 2, 3 câu...)
        if s in tl_so or float(s.replace(",", ".")) <= 3:
            continue
        xau.append((s, lay(m, "user")[:40], dap[:60]))
print(f"  2) số trong câu đáp KHÔNG có trong tài liệu: {len(xau)}"
      f"   {'ĐẠT' if not xau else 'CÓ VẤN ĐỀ'}")
for s, h, d in xau[:8]:
    print(f"       {s:>8}  hỏi={h!r}  đáp={d!r}")

# 3. mẫu đối chiếu: cùng câu hỏi mà đáp phải KHÁC nhau
theo_hoi = {}
for m in mau:
    theo_hoi.setdefault(lay(m, "user"), set()).add(lay(m, "assistant"))
nhieu = {h: v for h, v in theo_hoi.items() if len(v) > 1}
print(f"\n  3) câu hỏi có NHIỀU đáp án khác nhau (mẫu đối chiếu): {len(nhieu)}")
for h, v in list(nhieu.items())[:4]:
    print(f"       {h!r}")
    for d in list(v)[:3]:
        print(f"          -> {d[:72]}")

# 4. sản phẩm phân bố ra sao
sp = Counter()
for m in mau:
    t = lay(m, "system")
    mm = re.search(r"Sản phẩm quan tâm: (.+)", t)
    if mm:
        sp[mm.group(1).strip()] += 1
print(f"\n  4) phân bố sản phẩm")
for k, v in sp.most_common():
    print(f"       {v:>4}  {k}")

# 5. độ dài prompt (ngân sách ngữ cảnh khi train)
dai = [len(lay(m, "system")) for m in mau]
print(f"\n  5) độ dài system prompt: trung vị {sorted(dai)[len(dai)//2]}, "
      f"dài nhất {max(dai)} ký tự")
print(f"       (num_ctx của model = 2048 token ~ 6000 ký tự tiếng Việt)")
