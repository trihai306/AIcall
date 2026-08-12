import sys; sys.path.insert(0, r"C:/duan/chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from backend.config import settings
from backend.services.tts_service import F5TTSService
s = F5TTSService(); ten = s.default_voice_name()
print(f"  giong mac dinh : {ten}")
print(f"  toc cua giong  : {s.toc_do_cua(ten)}")
print(f"  nfe thuong     : {settings.f5tts_nfe_step}")
print(f"  nfe manh dau   : {settings.f5tts_nfe_step_first}   (manh dau dung fast=True)")
