import sys; sys.path.insert(0, r"C:/duan/chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from backend.config import settings
from backend.services.tts_service import F5TTSService
s = F5TTSService()
print(f"  settings.f5tts_speed  = {settings.f5tts_speed}   (mac dinh config.py, .env da bo)")
print(f"  toc_do_cua('default') = {s.toc_do_cua('default')}")
print(f"  toc_do_cua(None)      = {s.toc_do_cua(None)}")
