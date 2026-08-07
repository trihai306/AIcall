"""Sửa .env AN TOÀN VỚI TIẾNG VIỆT, rồi đọc lại qua Settings để xác nhận.

Vì sao cần cả một script cho việc gán vài dòng: sửa .env bằng PowerShell trên máy
Windows đã HAI LẦN làm hỏng dấu tiếng Việt - `F5TTS_REF_TEXT` biến thành
`m?t ngu?i kh�c`, và F5 nhân bản giọng theo lời mẫu sai thì đọc ra sai hẳn mà
không có lỗi nào hiện ra. Console mặc định là cp1252, `Set-Content` không nêu
encoding là ghi ra mojibake.

Script ghi bằng Python với encoding="utf-8", rồi NẠP LẠI qua chính `Settings` mà
backend dùng và in ra giá trị đọc được. Không tin lệnh ghi - tin cái đọc lại.

    python scripts/sua_env.py OLLAMA_MODEL=tuvan-qwen
    python scripts/sua_env.py "F5TTS_REF_TEXT=dạo gần đây thì mình cũng rất là vui vì."
"""

import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ENV = PROJECT / ".env"


def main() -> int:
    cap = [a for a in sys.argv[1:] if "=" in a]
    if not cap:
        print(__doc__)
        return 1

    doc = ENV.read_text(encoding="utf-8").splitlines()
    moi = dict(a.split("=", 1) for a in cap)
    da_co = set()
    ra = []
    for dong in doc:
        ten = dong.split("=", 1)[0].strip()
        if ten in moi:
            ra.append(f"{ten}={moi[ten]}")
            da_co.add(ten)
        else:
            ra.append(dong)
    for ten, gt in moi.items():
        if ten not in da_co:
            ra.append(f"{ten}={gt}")

    # newline="\n" để khỏi lẫn CRLF vào giữa - pydantic đọc được cả hai nhưng
    # trộn lẫn thì diff sau này đọc không nổi.
    ENV.write_text("\n".join(ra) + "\n", encoding="utf-8", newline="\n")

    # XÁC NHẬN bằng chính đường mà backend đọc, không phải bằng cách mở lại file.
    for mod in [m for m in sys.modules if m.startswith("backend")]:
        del sys.modules[mod]
    from backend.config import Settings

    s = Settings()
    print(f"\n  Đã ghi {ENV}")
    for ten in moi:
        thuoc = ten.lower()
        gt = getattr(s, thuoc, "<Settings không có trường này>")
        khop = "OK " if str(gt) == moi[ten] else "!! "
        print(f"  {khop}{ten} = {gt!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
