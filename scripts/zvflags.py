import re, sys, io
sys.stdout.reconfigure(encoding="utf-8")
src = io.open(r"C:\duan\chat-ai\tools\ZipVoice\zipvoice\bin\infer_zipvoice.py", encoding="utf-8").read()
for m in re.finditer(r'add_argument\(\s*"(--[a-z0-9\-]+)"(.*?)\)\s*\n', src, re.S):
    flag = m.group(1); body = m.group(2)
    d = re.search(r'default=([^,\n]+)', body)
    h = re.search(r'help="""?(.*?)(?:"""|",)', body, re.S)
    print("  %-22s default=%-28s %s" % (flag, (d.group(1).strip() if d else "-")[:26],
          (" ".join(h.group(1).split())[:70] if h else "")))
