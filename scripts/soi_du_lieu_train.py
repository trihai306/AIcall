"""Vì sao bản LoRA lại TỆ HƠN model gốc? Soi thẳng bộ dữ liệu train.

Đo được: `tuvan-qwen` (LoRA) bịa lãi suất 6.9%, còn `qwen2.5:3b` (chính model gốc
của nó) đọc đúng 7.9% cả 10/10 lần. Fine-tune đã LÀM MẤT khả năng bám tài liệu.

Ba nguyên nhân thường gặp, và cách phân biệt bằng chính bộ dữ liệu:

  A. SỐ CỨNG TRONG DỮ LIỆU - nếu mẫu train chứa "6.9%" thì model học thuộc con
     số đó, và sau này đọc lại bất kể tài liệu nói gì. Đây là giả thuyết số một
     vì model bịa ĐÚNG một con số cụ thể, lặp lại.

  B. TRAIN KHÔNG CÓ NGỮ CẢNH - nếu mẫu train chỉ có (câu khách -> câu trả lời)
     mà KHÔNG có mục "THÔNG TIN THAM KHẢO", thì model chưa bao giờ học việc đọc
     tài liệu. Nó học cách nói, không học cách tra.

  C. QUÁ ÍT MẪU / LẶP - vài chục mẫu là model chỉ thuộc lòng vài câu.

Script đếm và trích dẫn để chỉ ra nguyên nhân nào đúng.

    python scripts\\soi_du_lieu_train.py
    python scripts\\soi_du_lieu_train.py --thu-muc <đường dẫn>
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT = Path(__file__).resolve().parent.parent
# Con số phần trăm dạng 7.9 / 7,9 / "bảy phẩy chín"
_PCT = re.compile(r"\b(\d{1,2})[.,](\d)\s*%|\b(\d{1,2})\s*%")
_NGU_CANH = ("THÔNG TIN THAM KHẢO", "tham khảo", "context", "tài liệu")


def doc_mau(f: Path):
    """Trả list các bản ghi, chấp nhận cả .json (list) lẫn .jsonl."""
    t = f.read_text(encoding="utf-8", errors="replace").strip()
    if not t:
        return []
    if f.suffix == ".jsonl":
        ra = []
        for d in t.splitlines():
            d = d.strip()
            if d:
                try:
                    ra.append(json.loads(d))
                except Exception:
                    pass
        return ra
    try:
        o = json.loads(t)
    except Exception:
        return []
    return o if isinstance(o, list) else [o]


def van_ban(rec) -> str:
    """Gom mọi chuỗi trong một bản ghi, bất kể lược đồ."""
    ra = []
    def di(x):
        if isinstance(x, str):
            ra.append(x)
        elif isinstance(x, dict):
            for v in x.values():
                di(v)
        elif isinstance(x, list):
            for v in x:
                di(v)
    di(rec)
    return "\n".join(ra)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--thu-muc", nargs="+",
                    default=["data", "training", "models/llm"])
    a = ap.parse_args()

    tep = []
    for d in a.thu_muc:
        p = PROJECT / d
        if not p.exists():
            continue
        for x in list(p.rglob("*.jsonl")) + list(p.rglob("*.json")):
            # bỏ tệp của thư viện, chỉ giữ tệp dữ liệu
            if x.name in ("tokenizer.json", "config.json", "tokenizer_config.json",
                          "special_tokens_map.json", "generation_config.json",
                          "adapter_config.json", "trainer_state.json",
                          "vocab.json", "merges.json", "added_tokens.json",
                          "scheduler.json", "optimizer.json"):
                continue
            if x.stat().st_size > 20_000_000:
                continue
            tep.append(x)

    if not tep:
        print("  không thấy tệp dữ liệu nào")
        return 1

    print()
    for f in sorted(set(tep)):
        mau = doc_mau(f)
        if not mau or len(mau) < 3:
            continue
        toan = [van_ban(m) for m in mau]
        gop = "\n".join(toan)

        pct = Counter()
        for m in _PCT.finditer(gop):
            if m.group(1):
                pct[f"{m.group(1)}.{m.group(2)}%"] += 1
            else:
                pct[f"{m.group(3)}%"] += 1
        co_nc = sum(1 for t in toan if any(k in t for k in _NGU_CANH))

        print(f"  {f.relative_to(PROJECT)}")
        print(f"    {len(mau)} mẫu | có mục ngữ cảnh: {co_nc}/{len(mau)}"
              f" ({co_nc/len(mau)*100:.0f}%)")
        if pct:
            top = ", ".join(f"{k}×{v}" for k, v in pct.most_common(8))
            print(f"    phần trăm xuất hiện: {top}")
        else:
            print(f"    KHÔNG có con số phần trăm nào")
        # trích một mẫu để nhìn lược đồ
        print(f"    mẫu đầu: {toan[0][:150]!r}")
        print()

    print("  ĐỌC KẾT QUẢ:")
    print("   - thấy 6.9% trong dữ liệu  -> model HỌC THUỘC số đó (nguyên nhân A)")
    print("   - 'có mục ngữ cảnh' thấp   -> chưa bao giờ học đọc tài liệu (B)")
    print("   - số mẫu vài chục          -> quá ít, chỉ thuộc lòng câu mẫu (C)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
