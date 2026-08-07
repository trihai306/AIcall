"""In số `update` của một checkpoint F5. Dùng trong train.ps1 để cảnh báo sớm.

Vì sao cần: thư mục checkpoint dùng chung cho mọi giọng, nên buổi train sau tiếp
tục từ checkpoint của buổi trước. Nếu số update đã có lớn hơn số bước mà `-Epochs`
lần này sinh ra, vòng lặp sẽ KHÔNG chạy bước nào mà vẫn báo thành công.
Biết số update trước khi train thì thấy ngay chuyện đó.

    python scripts/doc_update_ckpt.py <đường dẫn .pt>
"""

import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print("?")
        return 1
    p = Path(sys.argv[1])
    if not p.exists():
        print("?")
        return 1
    try:
        import torch
        ck = torch.load(str(p), map_location="cpu", weights_only=False)
        print(ck.get("update", ck.get("step", "?")))
    except Exception as e:
        print(f"? ({e})")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
