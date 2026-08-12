import sqlite3, json, sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")
from backend.config import settings
conn = sqlite3.connect(str(settings.db_file))
conn.row_factory = sqlite3.Row

rows = conn.execute("SELECT * FROM call_sessions ORDER BY rowid DESC LIMIT 3").fetchall()
print(f"Recent sessions: {len(rows)}")
for row in rows:
    d = dict(row)
    keys = list(d.keys())[:6]
    print(f"  keys: {keys}")
    break

# Try latency_metrics table
rows2 = conn.execute("SELECT * FROM latency_metrics ORDER BY rowid DESC LIMIT 10").fetchall()
if rows2:
    cols2 = list(dict(rows2[0]).keys())
    print(f"\nlatency_metrics cols: {cols2}")
    for r in rows2:
        d = dict(r)
        cho_ms = d.get("tinh_huong_cho_ms")
        th_id = d.get("tinh_huong_id")
        ttfa = d.get("ttfa_ms")
        turn = d.get("turn")
        if cho_ms is not None or th_id is not None:
            print(f"  lượt {turn}: cho_ms={cho_ms}, tinh_huong_id={th_id}, ttfa={ttfa}")
conn.close()
