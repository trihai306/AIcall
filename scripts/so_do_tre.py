"""So độ trễ từng lượt giữa các phiên gọi, để đối chiếu trước/sau khi sửa."""
import sqlite3, sys, io, datetime as dt
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

d = sqlite3.connect(r"C:\duan\chat-ai\data\app.db")
d.row_factory = sqlite3.Row
cot = [c[1] for c in d.execute("PRAGMA table_info(latency_metrics)")]

so = int(sys.argv[1]) if len(sys.argv) > 1 else 4
phien = [r[0] for r in d.execute(
    "select session_id from call_sessions order by created_at desc limit ?", (so,))]

print("cot latency_metrics:", cot, "\n")
for sid in phien:
    r0 = d.execute("""select phone, created_at, turn_count from call_sessions
                      where session_id=?""", (sid,)).fetchone()
    khi = dt.datetime.fromtimestamp(float(r0["created_at"])).strftime("%m-%d %H:%M")
    print(f"=== {sid} | {r0['phone']} | {khi} | {r0['turn_count']} luot ===")
    rows = d.execute("select * from latency_metrics where session_id=? order by rowid",
                     (sid,)).fetchall()
    if not rows:
        print("   (khong co so do)\n")
        continue
    for i, m in enumerate(rows, 1):
        g = dict(m)
        print(f"   luot {i}: " + "  ".join(
            f"{k}={g[k]}" for k in ("stt_ms", "rag_ms", "ttfa_ms", "total_ms")
            if k in g))
    tt = [dict(m)["ttfa_ms"] for m in rows if dict(m).get("ttfa_ms")]
    if tt:
        print(f"   -> TTFA: nho nhat {min(tt)}ms, lon nhat {max(tt)}ms, "
              f"trung binh {sum(tt)//len(tt)}ms")
    print()
