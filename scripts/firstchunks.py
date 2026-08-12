import io, re, sys, collections
sys.stdout.reconfigure(encoding="utf-8")
lines = io.open(r"C:\duan\chat-ai\logs\backend.log", encoding="utf-8", errors="replace").read().splitlines()
# dong dang: TTS [voice]: 'chu...' -> Nms audio
pat = re.compile(r"TTS \[[^\]]+\]: '(.+?)\.\.\.'")
seen = [m.group(1) for l in lines if (m := pat.search(l))]
print("=== %d lan tong hop, mau 20 chuoi dau ===" % len(seen))
for s in seen[:20]:
    print("   %r" % s)
print()
c = collections.Counter(s.split()[0] if s.split() else "" for s in seen)
print("=== tu dau tien xuat hien nhieu nhat ===")
for w, n in c.most_common(8):
    print("   %-12s %d lan  (%.0f%%)" % (w, n, 100*n/max(1,len(seen))))
