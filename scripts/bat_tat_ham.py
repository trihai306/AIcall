import sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
p = Path(r"C:/duan/chat-ai/backend/core/startup.py")
s = p.read_text(encoding="utf-8")
bat = "--bat" in sys.argv
if bat:
    s = s.replace("# asyncio.create_task(_ham_hinh_dang_tts(state))",
                  "asyncio.create_task(_ham_hinh_dang_tts(state))")
else:
    s = s.replace("        asyncio.create_task(_ham_hinh_dang_tts(state))",
                  "        # asyncio.create_task(_ham_hinh_dang_tts(state))")
p.write_text(s, encoding="utf-8")
print(f"  ham nong: {'BAT' if bat else 'TAT'}")
for l in s.splitlines():
    if "_ham_hinh_dang_tts(state)" in l and "async def" not in l:
        print(f"    {l.strip()}")
