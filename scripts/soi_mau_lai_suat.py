"""Bộ dữ liệu train DẠY model trả lời câu lãi suất như thế nào?

Đếm số liệu thôi chưa đủ - phải đọc chính câu trả lời mẫu. Nếu mẫu dạy nó nói
một con số CỐ ĐỊNH, hoặc dạy nó né bằng câu chung chung, thì đó là thứ nó học,
và sau này gặp tài liệu nói khác nó vẫn nói theo mẫu.

    python scripts\\soi_mau_lai_suat.py data\\training\\merged_dataset.jsonl
"""

import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main() -> int:
    if len(sys.argv) < 2:
        print("  dùng: python scripts/soi_mau_lai_suat.py <tệp .jsonl>")
        return 1
    f = Path(sys.argv[1])
    tu_khoa = sys.argv[2] if len(sys.argv) > 2 else "lãi"

    n = 0
    print()
    for dong in f.read_text(encoding="utf-8", errors="replace").splitlines():
        dong = dong.strip()
        if not dong:
            continue
        try:
            o = json.loads(dong)
        except Exception:
            continue

        msgs = o.get("messages") or o.get("conversations") or []
        if not isinstance(msgs, list):
            continue
        for i, m in enumerate(msgs):
            if not isinstance(m, dict):
                continue
            vai = m.get("role") or m.get("from") or ""
            noi = m.get("content") or m.get("value") or ""
            if vai in ("user", "human") and tu_khoa in noi.lower():
                dap = ""
                if i + 1 < len(msgs) and isinstance(msgs[i + 1], dict):
                    dap = (msgs[i + 1].get("content")
                           or msgs[i + 1].get("value") or "")
                n += 1
                print(f"  {n:>3}. KHÁCH: {noi.strip()[:80]}")
                print(f"       ĐÁP  : {dap.strip()[:150]}")
                if n >= 15:
                    print(f"\n  (dừng ở 15 mẫu đầu)")
                    return 0
    print(f"\n  tổng {n} mẫu có từ khoá {tu_khoa!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
