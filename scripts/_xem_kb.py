import sqlite3, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
d = sqlite3.connect(r"C:\duan\chat-ai\data\app.db"); d.row_factory = sqlite3.Row
print("cot scenarios:", [c[1] for c in d.execute("PRAGMA table_info(scenarios)")])
for r in d.execute("select * from scenarios limit 4"):
    g = dict(r)
    print("\n---", g.get("name"), "| direction:", g.get("direction"))
    print("  opening_line:", repr(g.get("opening_line"))[:200])
