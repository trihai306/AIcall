import sqlite3, sys, os, time
sys.stdout.reconfigure(encoding="utf-8")
c = sqlite3.connect("data/app.db")
cols = [r[1] for r in c.execute("pragma table_info(call_sessions)")]
print("cot:", cols)
rows = list(c.execute("select * from call_sessions order by rowid"))
i = {n: k for k, n in enumerate(cols)}
ph = i.get("phone"); rec = i.get("recording_path"); out = i.get("outcome"); st = i.get("created_at")
turns = [k for k in cols if "turn" in k]
print("cot luot:", turns)
tk = i[turns[0]] if turns else None
theo_so = {}
for r in rows:
    if not r[rec] or not os.path.exists(r[rec]): continue
    so = r[ph]
    theo_so.setdefault(so, []).append(r)
for so, ds in theo_so.items():
    co_luot = [r for r in ds if (tk is None or (r[tk] or 0) > 0) and r[out] != "no_answer"]
    print(f"\n== so {so}: {len(ds)} ban ghi, {len(co_luot)} cuoc co luot")
    for r in co_luot[-6:]:
        print(f"   {r[0]}  {time.strftime('%m-%d %H:%M', time.localtime(r[st]))}  luot={r[tk] if tk else '?'}  {r[out]}  {os.path.basename(r[rec])}")
