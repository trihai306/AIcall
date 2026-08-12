import io, re, sys
sys.stdout.reconfigure(encoding="utf-8")
lines = io.open(r"C:\duan\chat-ai\logs\backend.log", encoding="utf-8", errors="replace").read().splitlines()
pat = re.compile(r"TTS \[[^\]]+\]: '(.+?)\.\.\.' -> (\d+)ms audio")
fillers = {"dạ vâng ạ","dạ, em hiểu rồi ạ","vâng, để em xem ạ","dạ được ạ"}
print("=== do dai audio cua 4 cau filler ===")
seen=set()
for l in lines:
    m = pat.search(l)
    if m and m.group(1) in fillers and m.group(1) not in seen:
        seen.add(m.group(1))
        print("   %-22s -> %5d ms tieng" % ("'"+m.group(1)+"'", int(m.group(2))))
