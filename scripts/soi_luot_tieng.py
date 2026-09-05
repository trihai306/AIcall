import sqlite3, sys, re
sys.stdout.reconfigure(encoding="utf-8")
c = sqlite3.connect("data/app.db"); c.row_factory = sqlite3.Row
print("== cot latency_metrics ==", [r["name"] for r in c.execute("PRAGMA table_info(latency_metrics)")])
# lượt khách đến từ TIẾNG: PhoWhisper trả chữ thường, không viết hoa đầu câu
rows = [r for r in c.execute(
    "SELECT session_id, turn_index, content, recorded_at FROM conversation_turns "
    "WHERE role='user' ORDER BY recorded_at DESC LIMIT 900")]
tu_tieng = [r for r in rows if r["content"] and r["content"][:1].islower()]
print(f"tong luot khach xet: {len(rows)}, giong STT (chu thuong dau cau): {len(tu_tieng)}")
phien = {}
for r in tu_tieng:
    phien.setdefault(r["session_id"], []).append(r)
for sid, ds in list(phien.items())[:14]:
    print(f"--- phien {sid[:8]} ({len(ds)} luot) {str(ds[0]['recorded_at'])[:19]}")
    for d in sorted(ds, key=lambda x: x["turn_index"]):
        print(f"    {d['turn_index']:>3} {d['content']!r}")
