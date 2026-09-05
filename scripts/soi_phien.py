import sqlite3, sys
sys.stdout.reconfigure(encoding="utf-8")
c = sqlite3.connect("data/app.db"); c.row_factory = sqlite3.Row
for sid in sys.argv[1:]:
    print(f"########## phien {sid}")
    for r in c.execute("SELECT turn_index, role, content FROM conversation_turns "
                       "WHERE session_id LIKE ? ORDER BY turn_index", (sid + "%",)):
        who = "KHACH" if r["role"] == "user" else "  AI "
        print(f"  {r['turn_index']:>3} {who}: {r['content']}")
    for r in c.execute("SELECT * FROM call_sessions WHERE id LIKE ?", (sid + "%",)):
        d = dict(r)
        print("  META:", {k: d[k] for k in list(d)[:14]})
    print("  latency:", [dict(x) for x in c.execute(
        "SELECT turn_number, stt_ms, ttfa_ms, total_ms FROM latency_metrics WHERE session_id LIKE ? ORDER BY turn_number", (sid + "%",))])
