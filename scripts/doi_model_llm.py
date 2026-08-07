"""Đổi `OLLAMA_MODEL` trong .env, an toàn mã hoá.

Cùng lý do với `doi_toc_do_noi.py`: `.env` chứa tiếng Việt có dấu ở
`F5TTS_REF_TEXT`, sửa bằng PowerShell là hỏng. Và viết Python một dòng qua SSH
thì dấu nháy bị nuốt ở nhiều tầng - đã mắc.

    python scripts\\doi_model_llm.py vistral-7b-chat
"""

import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

KHOA = "OLLAMA_MODEL"


def main() -> int:
    if len(sys.argv) < 2:
        print("  dùng: python scripts/doi_model_llm.py <tên model>")
        return 1
    moi = sys.argv[1].strip()

    f = Path(__file__).resolve().parent.parent / ".env"
    goc = f.read_text(encoding="utf-8")
    m = re.search(rf"^{KHOA}=(.*)$", goc, re.M)
    cu = m.group(1).strip() if m else None
    if m:
        ra = re.sub(rf"^{KHOA}=.*$", f"{KHOA}={moi}", goc, count=1, flags=re.M)
    else:
        ra = goc.rstrip("\n") + f"\n{KHOA}={moi}\n"
    f.write_text(ra, encoding="utf-8")

    print(f"  {KHOA}: {cu} -> {moi}")
    print("  PHẢI khởi động lại backend, và nhớ `ollama stop` model cũ:")
    print("  VRAM chỉ còn ~5GB sau khi F5-TTS và Whisper nạp xong, giữ hai model")
    print("  cùng lúc là Ollama đẩy ra vào liên tục - đo được sinh chậm gấp 100 lần.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
