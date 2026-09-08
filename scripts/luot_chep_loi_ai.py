"""Dem luot KHACH trong CSDL ma phan lon tu trung voi luot AI ngay truoc -> vong bi
STT chep thanh loi khach. Do tren toan bo lich su de biet tac hai thuc te."""
import sqlite3, re, sys
sys.stdout.reconfigure(encoding="utf-8")
c = sqlite3.connect("data/app.db")
def tu(s): return re.sub(r"[^\w\sÀ-ỹ]", " ", (s or "").lower()).split()
rows = list(c.execute("select session_id, turn_index, role, content from conversation_turns order by session_id, turn_index"))
truoc = {}; tong = 0; nghi = []
for sid, idx, role, content in rows:
    if role == "assistant": truoc[sid] = content; continue
    tong += 1
    t = tu(content); a = set(tu(truoc.get(sid, "")))
    if len(t) >= 3 and a:
        trung = sum(1 for w in t if w in a) / len(t)
        # cum 3 tu lien tiep co trong loi AI?
        cum = any(" ".join(t[i:i+3]) in " ".join(tu(truoc.get(sid, ""))) for i in range(len(t)-2))
        if trung >= 0.6 and cum: nghi.append((sid, content[:70], truoc[sid][:70], trung))
print(f"{tong} luot khach; {len(nghi)} luot ({100*len(nghi)/max(tong,1):.1f}%) trung >=60% tu VA co cum 3 tu lien tiep cua loi AI ngay truoc:")
for sid, k, a, tr in nghi[:15]:
    print(f"  [{sid}] {tr:.0%}  KHACH: {k!r}\n           AI truoc: {a!r}")
