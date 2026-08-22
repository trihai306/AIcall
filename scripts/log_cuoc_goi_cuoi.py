import re, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
t=Path(r"C:\duan\chat-ai\logs\backend.log").read_text(encoding="utf-8",errors="replace").splitlines()
# lay tu lan "ADB dialled" cuoi cung tro di
vt=[i for i,l in enumerate(t) if "ADB dialled" in l]
i0=vt[-2] if len(vt)>=2 else (vt[-1] if vt else 0)
bo=("WifiPermissions","canAccessScanResults")
for l in t[i0:]:
    if any(k in l for k in bo): continue
    print(l[-155:])
