"""So DAI tung manh: ban ghi cuoc goi vs sinh lai ngoai tuyen, cung chu."""
import asyncio, io, re, sys
from pathlib import Path
sys.path.insert(0, r"C:/duan/chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, soundfile as sf
from backend.services.tts_service import F5TTSService

hang = []
for l in Path(r"C:/tmp/goi5/bang_tra.txt").read_text(encoding="utf-8").splitlines():
    m = re.match(r"\s+(\d):([\d.]+) - (\d):([\d.]+)\s+(\S+)\s+(.*?)(\s+<==.*)?$", l)
    if m and m.group(5) != "dem":
        chu = m.group(6).strip()
        if chu and chu != "[câu đệm]":
            hang.append((int(m[3])*60+float(m[4]) - (int(m[1])*60+float(m[2])), chu))

async def main():
    svc = F5TTSService(); svc.load()
    ten = svc.default_voice_name(); await svc.ensure_voice(ten)
    print(f"\n  {'ghi':>6} {'sinh lai':>9} {'ty le':>6}  chu")
    print("  " + "-"*62)
    ty = []
    for i, (dai_ghi, chu) in enumerate(hang):
        b = await svc.synthesize(chu, voice=ten, fast=(i == 0), use_cache=False)
        x, sr = sf.read(io.BytesIO(b), dtype="float32")
        d = len(x)/sr
        ty.append(dai_ghi/d)
        if i < 14 or dai_ghi/d > 1.6:
            print(f"  {dai_ghi:>5.2f}s {d:>8.2f}s {dai_ghi/d:>5.2f}x  {chu[:34]}")
    print("  " + "-"*62)
    print(f"\n  tong ghi {sum(h[0] for h in hang):.2f}s | tong sinh lai "
          f"{sum(h[0] for h in hang)/ (sum(ty)/len(ty)):.2f}s")
    print(f"  ty le trung binh {sum(ty)/len(ty):.2f}x  (min {min(ty):.2f} max {max(ty):.2f})")
    print(f"  sr tra ve: {sr} Hz")
asyncio.run(main())
