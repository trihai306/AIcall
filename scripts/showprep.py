import io, sys
sys.stdout.reconfigure(encoding="utf-8")
L = io.open(r"C:\duan\chat-ai\logs\prep.txt", encoding="utf-8", errors="replace").read().splitlines()
L = [l for l in L if l.strip()]
print("\n".join(L[:3]))
print("   ... (%d dòng) ..." % len(L))
print("\n".join(L[-9:]))
import collections
tags = collections.Counter()
for l in L:
    if "[OK]" in l and "[" in l.rsplit("[",1)[0]:
        tags[l.rsplit("[",1)[-1].rstrip("]")] += 1
print("\nNguồn transcript:", dict(tags))
