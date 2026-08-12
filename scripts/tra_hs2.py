import sys, sqlite3, json
sys.path.insert(0, r"C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")
from backend.services import data_source_service as D
print("  === tra_cuu('0912345678') ===")
try:
    print("  ", str(D.tra_cuu("0912345678"))[:700])
except Exception as e:
    print("   loi:", e)
print("\n  === nguon du lieu trong CSDL ===")
c = sqlite3.connect("data/app.db").cursor()
c.execute("SELECT * FROM data_sources")
cols = [d[0] for d in c.description]
for r in c.fetchall():
    d = dict(zip(cols, r))
    for k, v in d.items():
        sv = str(v)
        if len(sv) > 200: sv = sv[:200] + "..."
        print(f"    {k}: {sv}")
    print("    ---")
