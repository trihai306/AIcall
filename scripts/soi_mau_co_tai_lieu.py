"""Bộ `dataset_co_tai_lieu.jsonl` đã đủ tốt để train chưa?

Đây là bộ ĐANG BỊ ĐỂ RIÊNG (thư mục `_de_rieng`) trong khi buổi train lấy
`merged_dataset.jsonl` - bộ không có tài liệu tham khảo nào. Trước khi đề nghị
dùng nó, phải kiểm ba thứ mà tài liệu về Finetune-RAG chỉ ra là quyết định:

  1. Mẫu có KÈM tài liệu không, và câu trả lời có bám tài liệu đó không
  2. Có TÀI LIỆU NHIỄU (sản phẩm khác) để model học cách CHỌN đúng phần không.
     Không có nhiễu thì model học "cứ có tài liệu là chép", gặp tài liệu sai
     vẫn chép.
  3. Con số có ĐA DẠNG giữa các mẫu không. Nếu mọi mẫu đều 7.9% thì model học
     thuộc 7.9% chứ không học cách tra - đúng lỗi đang mắc.

    python scripts\\soi_mau_co_tai_lieu.py
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TEP = PROJECT / "data" / "training" / "_de_rieng" / "dataset_co_tai_lieu.jsonl"
_PCT = re.compile(r"(\d{1,2}[.,]\d)\s*%")


def main() -> int:
    f = Path(sys.argv[1]) if len(sys.argv) > 1 else TEP
    if not f.exists():
        print(f"  không thấy {f}")
        return 1

    n = 0
    pct_tl = Counter()      # phần trăm trong TÀI LIỆU
    pct_dap = Counter()     # phần trăm trong CÂU ĐÁP
    khop = lech = 0
    n_sanpham = Counter()
    vi_du = None

    for dong in f.read_text(encoding="utf-8", errors="replace").splitlines():
        dong = dong.strip()
        if not dong:
            continue
        try:
            o = json.loads(dong)
        except Exception:
            continue
        msgs = o.get("messages") or []
        sys_txt = "".join(m.get("content", "") for m in msgs if m.get("role") == "system")
        dap = "".join(m.get("content", "") for m in msgs if m.get("role") == "assistant")
        n += 1
        if vi_du is None:
            vi_du = (sys_txt, dap)

        tl = _PCT.findall(sys_txt)
        dp = _PCT.findall(dap)
        pct_tl.update(tl)
        pct_dap.update(dp)
        if dp:
            if all(d in tl for d in dp):
                khop += 1
            else:
                lech += 1
        for sp in ("tín chấp", "mua nhà", "thẻ tín dụng", "tiết kiệm", "mua xe"):
            if sp in sys_txt.lower():
                n_sanpham[sp] += 1

    print(f"\n  {f.name}: {n} mẫu\n")
    print(f"  phần trăm trong TÀI LIỆU: {dict(pct_tl.most_common(8))}")
    print(f"  phần trăm trong CÂU ĐÁP : {dict(pct_dap.most_common(8))}")
    print(f"  câu đáp KHỚP tài liệu   : {khop}")
    print(f"  câu đáp LỆCH tài liệu   : {lech}   <- phải bằng 0")
    print(f"  sản phẩm nhắc trong tài liệu: {dict(n_sanpham)}")
    print(f"\n  Đa dạng số: {len(pct_tl)} mức lãi suất khác nhau trong tài liệu.")
    if len(pct_tl) <= 1:
        print("    -> CHỈ MỘT mức. Model sẽ học thuộc đúng số đó, không học cách tra.")
        print("       Phải thêm mẫu với mức lãi khác nhau (kể cả số bịa đặt) để nó")
        print("       buộc phải ĐỌC tài liệu mới trả lời đúng.")
    else:
        print("    -> Có nhiều mức, tốt: model buộc phải đọc tài liệu mới đúng.")
    if vi_du:
        print(f"\n  Mẫu đầu (tài liệu, 260 ký tự cuối):\n    ...{vi_du[0][-260:]!r}")
        print(f"  Câu đáp:\n    {vi_du[1][:160]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
