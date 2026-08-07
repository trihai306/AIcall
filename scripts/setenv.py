import io, re, sys
sys.stdout.reconfigure(encoding="utf-8")
p = r"C:\duan\chat-ai\.env"
s = io.open(p, encoding="utf-8").read()
key, val = sys.argv[1], sys.argv[2]
if re.search(r"(?m)^%s=" % key, s):
    s = re.sub(r"(?m)^%s=.*$" % key, "%s=%s" % (key, val), s)
else:
    s = s.rstrip("\n") + "\n%s=%s\n" % (key, val)
io.open(p, "w", encoding="utf-8").write(s)
print([l for l in s.splitlines() if l.startswith(key)])
