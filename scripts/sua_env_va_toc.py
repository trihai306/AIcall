"""Ha toc giong xuong 1.12 va vo hieu F5TTS_SPEED trong .env.

Sua .env o MUC BYTE, khong dung PowerShell: PowerShell doc/ghi lai lam hong dau
tieng Viet trong file (da mac mot lan voi F5TTS_REF_TEXT). Co sao luu truoc khi
dung dao.
"""
import shutil, sys, time
from pathlib import Path
sys.path.insert(0, r"C:/duan/chat-ai"); sys.stdout.reconfigure(encoding="utf-8")

TOC_MOI = 1.12
GOC = Path(r"C:/duan/chat-ai/.env")
dau = time.strftime("%Y%m%d-%H%M%S")

# --- 1. toc giong -------------------------------------------------------
from backend.services.tts_service import F5TTSService
svc = F5TTSService()
ten = svc.default_voice_name()
p = svc._tep_speed(ten)
cu = p.read_text(encoding="utf-8").strip() if p.exists() else "(chua co)"
p.write_text(f"{TOC_MOI:.3f}", encoding="utf-8")
print(f"  toc giong {ten}: {cu} -> {p.read_text(encoding='utf-8').strip()}")
print(f"    {p}")

# --- 2. .env ------------------------------------------------------------
tho = GOC.read_bytes()
sao = GOC.with_name(f".env.bak-{dau}")
shutil.copy2(GOC, sao)
dong = tho.split(b"\n")
ra, sua = [], 0
for d in dong:
    if d.strip().startswith(b"F5TTS_SPEED="):
        ra.append(b"# " + d.rstrip(b"\r")
                  + b"   # BO 2026-08-10: bi danh voice \"default\" khong co tep"
                    b" .speed nen roi ve day, lam cuoc goi doc o 0.64 thay vi"
                    b" 1.20. Mac dinh trong config.py la 1.0.")
        if d.endswith(b"\r"): ra[-1] += b"\r"
        sua += 1
    else:
        ra.append(d)
if sua:
    GOC.write_bytes(b"\n".join(ra))
print(f"\n  .env: vo hieu {sua} dong F5TTS_SPEED")
print(f"    sao luu: {sao}")
print(f"    kich thuoc {len(tho)} -> {len(GOC.read_bytes())} byte")

# --- 3. kiem chung ------------------------------------------------------
print(f"\n  cac dong F5TTS_SPEED trong .env sau khi sua:")
for i, d in enumerate(GOC.read_bytes().split(b"\n"), 1):
    if b"F5TTS_SPEED" in d:
        print(f"    {i}: {d.decode('utf-8', 'replace')[:96]}")
