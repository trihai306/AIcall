"""Doi F5TTS_NFE_STEP_FIRST tren .env cua may Win. Sua TAI CHO, giu nguyen phan con lai."""
import re, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
p=Path(r"C:\duan\chat-ai\.env")
t=p.read_text(encoding="utf-8")
cu=re.search(r"^F5TTS_NFE_STEP_FIRST=(\S+)", t, re.M)
print("trước:", cu.group(0) if cu else "(không có dòng nào)")
if cu and cu.group(1)=="12":
    print("đã là 12, không đổi"); sys.exit()
t2=re.sub(r"^F5TTS_NFE_STEP_FIRST=\S+",
          "F5TTS_NFE_STEP_FIRST=12   # 14-08: 16->12, do 16 cau: chu dau 13/16->14/16, 451->244ms",
          t, count=1, flags=re.M)
if t2==t:
    t2=t.rstrip("\n")+"\nF5TTS_NFE_STEP_FIRST=12\n"
p.write_text(t2, encoding="utf-8")
print("sau  :", re.search(r"^F5TTS_NFE_STEP_FIRST=.*", p.read_text(encoding="utf-8"), re.M).group(0))
