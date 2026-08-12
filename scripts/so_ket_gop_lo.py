"""Gom moc TTS tu log de so truoc/sau."""
import re, sys, statistics as st
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
tho = Path(r"C:/duan/chat-ai/logs/backend.log").read_bytes().decode("utf-8","replace").splitlines()
LE = re.compile(r"TTS \[([^\]]+)\]: '(.*?)\.\.\.' -> (\d+)ms audio \((\d+)ms\)")
LO = re.compile(r"TTS lô \[([^\]]+)\]: (\d+) mảnh -> (\d+)ms \((\d+)ms/mảnh\)")
le, lo = [], []
for l in tho[-6000:]:
    m = LE.search(l)
    if m: le.append(int(m.group(4)))
    m = LO.search(l)
    if m: lo.append((int(m.group(2)), int(m.group(3))))
# chi lay phan SAU khi ham xong
i = max((k for k, l in enumerate(tho) if "đã hâm" in l and "hình dạng" in l), default=0)
le2, lo2 = [], []
for l in tho[i:]:
    m = LE.search(l)
    if m: le2.append(int(m.group(4)))
    m = LO.search(l)
    if m: lo2.append((int(m.group(2)), int(m.group(3))))
print(f"\n  SAU KHI HAM XONG ({len(le2)} lan sinh le, {len(lo2)} lan sinh lo)\n")
if le2:
    print(f"  sinh LE  : trung vi {st.median(le2):>5.0f}ms  to nhat {max(le2):>5.0f}ms")
if lo2:
    manh = sum(x[0] for x in lo2); tong = sum(x[1] for x in lo2)
    moi = [b/a for a, b in lo2]
    print(f"  sinh LO  : {len(lo2)} lo / {manh} manh, {tong}ms  ->"
          f" {tong/manh:.0f}ms moi manh")
    print(f"             co lo trung binh {manh/len(lo2):.1f} manh")
    print(f"\n  tong GPU cho TTS: {sum(le2) + tong}ms tren {len(le2)+manh} manh")
    print(f"  neu sinh le het  : {(len(le2)+manh) * st.median(le2):.0f}ms")
    print(f"  -> tiet kiem {(1 - (sum(le2)+tong)/((len(le2)+manh)*st.median(le2)))*100:.0f}%")
