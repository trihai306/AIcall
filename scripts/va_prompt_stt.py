"""Thêm `initial_prompt` cho máy chủ PhoWhisper.

Whisper cho phép mồi từ vựng: đưa trước một đoạn văn bản chứa các từ hay gặp
trong lĩnh vực, bộ giải mã sẽ nghiêng về chúng. Đây là cách sửa TẠI GỐC, khác
với việc chữa hậu quả bằng cách đoán lại chuỗi đã sai.

Vá bằng Python để giữ nguyên UTF-8 của chú thích tiếng Việt trong file.
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
P = Path("C:/duan/chat-ai/whisper_server/pho_server.py")
s = P.read_text(encoding="utf-8")
goc = s

VA = [
    # 1. nhận tham số từ HTTP
    ('    temperature: str = Form("0"),\n):',
     '    temperature: str = Form("0"),\n'
     '    prompt: str = Form(""),\n'
     '):'),
    # 2. truyền xuống hàm chạy nền
    ('        _transcribe_sync, audio_bytes, language, float(temperature or 0)\n    )',
     '        _transcribe_sync, audio_bytes, language, float(temperature or 0),\n'
     '        prompt or None,\n    )'),
    # 3. chữ ký hàm
    ('def _transcribe_sync(audio_bytes: bytes, language: str,\n'
     '                     temperature: float) -> tuple[str, list[dict]]:',
     'def _transcribe_sync(audio_bytes: bytes, language: str,\n'
     '                     temperature: float,\n'
     '                     initial_prompt: str | None = None,\n'
     '                     ) -> tuple[str, list[dict]]:'),
    # 4. đưa vào model
    ('        beam_size=BEAM_SIZE,',
     '        beam_size=BEAM_SIZE,\n'
     '        # Mồi từ vựng: đoạn văn bản chứa từ hay gặp của lĩnh vực, bộ giải\n'
     '        # mã sẽ nghiêng về chúng. Cần vì kênh thoại 8kHz làm mất phụ âm:\n'
     '        # đo trên cuộc gọi thật, "lãi suất" bị nghe thành "lãnh xuất" -\n'
     '        # đúng từ khoá quan trọng nhất của kịch bản bán hàng.\n'
     '        initial_prompt=initial_prompt,'),
]

for cu, moi in VA:
    if moi.split("\n")[0] in s and cu not in s:
        print("  (đã vá rồi, bỏ qua một mục)")
        continue
    if cu not in s:
        print(f"  [!] KHÔNG tìm thấy mẫu: {cu[:60]!r}")
        sys.exit(1)
    s = s.replace(cu, moi, 1)

if s == goc:
    print("  không có gì thay đổi")
else:
    P.write_text(s, encoding="utf-8")
    print("  đã vá xong")

# đọc lại kiểm chứng
lai = P.read_text(encoding="utf-8")
for can in ('prompt: str = Form("")', "initial_prompt=initial_prompt",
            "initial_prompt: str | None = None"):
    print(f"  {'OK ' if can in lai else '!! '}{can}")
print(f"  chú thích tiếng Việt còn nguyên: "
      f"{'OK' if 'Whisper BỊA CHỮ' in lai or 'nhiễu' in lai else 'KIỂM LẠI'}")
