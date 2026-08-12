"""Sinh vai cau thu bang giong vua train, luu ra file WAV de nghe.

Cau thu chon co chu dich:
  1. Mo dau bang "Da" - cho nay da tung doc sai ~70% khi giong mau khong co no
  2. Co con so (lai suat, so tien) - LLM va TTS deu hay vap o so
  3. Cau dai binh thuong - nghe ngu dieu tu nhien hay khong
"""
import base64
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API = "http://127.0.0.1:8100/api/voices/test-tts"
RA = Path(r"C:\duan\chat-ai\logs\thu_giong")
RA.mkdir(parents=True, exist_ok=True)

CAU = [
    ("01_da",   "Dạ em chào anh, em gọi từ ngân hàng ạ."),
    ("02_so",   "Dạ lãi suất hiện tại là sáu phẩy năm phần trăm một năm, vay tối đa năm trăm triệu ạ."),
    ("03_dai",  "Dạ bên em đang có gói vay tín chấp dành cho khách hàng có thu nhập ổn định, "
                "thủ tục đơn giản, giải ngân trong vòng hai mươi bốn giờ ạ."),
]

for ten, text in CAU:
    du_lieu = urllib.parse.urlencode({
        "text": text, "voice_name": "giong_nam", "fast": "false",
    }).encode()
    req = urllib.request.Request(API, data=du_lieu)
    with urllib.request.urlopen(req, timeout=120) as r:
        kq = json.loads(r.read())

    if "error" in kq:
        print(f"[{ten}] LOI: {kq['error']}")
        continue

    f = RA / f"{ten}.wav"
    f.write_bytes(base64.b64decode(kq["audio"]))
    print(f"[{ten}] {kq['duration_ms']}ms tieng / {kq['elapsed_ms']}ms sinh "
          f"(rtf {kq['rtf']}) -> {f.name}")
    print(f"         \"{text}\"")
