"""Ghi F5TTS_REF_TEXT vào .env bằng Python, KHÔNG qua PowerShell.

Vì sao: truyền chuỗi tiếng Việt qua ssh -> PowerShell -> Set-Content làm hỏng
dấu ("một người" thành "m?t ngu?i"). Lời đoạn mẫu sai dấu thì F5 học lệch ở
MỌI câu nó đọc sau này, nên phải ghi bằng đường giữ nguyên UTF-8.
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
P = Path("C:/duan/chat-ai")

loi = (P / "models/tts/ref_voices/giong_heu.txt").read_text(encoding="utf-8").strip()
env = P / ".env"
dong = env.read_text(encoding="utf-8").splitlines()

ra, thay = [], False
for d in dong:
    if d.startswith("F5TTS_REF_TEXT="):
        ra.append(f"F5TTS_REF_TEXT={loi}")
        thay = True
    else:
        ra.append(d)
if not thay:
    ra.append(f"F5TTS_REF_TEXT={loi}")

env.write_text("\n".join(ra) + "\n", encoding="utf-8")

# đọc lại bằng chính đường mà ứng dụng dùng
sys.path.insert(0, str(P))
from backend.config import Settings
s = Settings()
print(f"  file .txt   : {loi!r}")
print(f"  đọc từ .env : {s.f5tts_ref_text!r}")
print(f"  khớp nhau   : {'ĐÚNG' if s.f5tts_ref_text.strip() == loi else 'SAI - còn hỏng'}")
print(f"  ref audio   : {s.f5tts_ref_audio}")
