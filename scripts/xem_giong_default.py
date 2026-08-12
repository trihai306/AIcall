import sys; sys.path.insert(0, r"C:/duan/chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import asyncio
from backend.services.tts_service import F5TTSService
s = F5TTSService(); s.load()
print(f"  default_voice_name()      : {s.default_voice_name()}")
giai = asyncio.run(s.ensure_voice("default"))
print(f"  ensure_voice('default')   : {giai}")
for v in (s.default_voice_name(), giai):
    print(f"    toc_do_cua({v!r}) = {s.toc_do_cua(v)}")
import os
d = r"C:/duan/chat-ai/models/tts/ref_voices"
print(f"\n  tep trong {d}:")
for f in sorted(os.listdir(d)):
    print(f"    {f}")
