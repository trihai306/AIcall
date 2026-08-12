import sqlite3, sys, json
sys.path.insert(0, r"C:\duan\chat-ai")
from backend.config import settings
c = sqlite3.connect(str(settings.db_file))
print("=== Tinh huong in DB ===")
for r in c.execute("SELECT id, ten FROM tinh_huong WHERE bat=1"):
    print(r)
print()
print("=== Last 9 latency_metrics ===")
for r in c.execute("SELECT turn_number, filler_id, tinh_huong_id, ttfa_ms FROM latency_metrics ORDER BY timestamp DESC LIMIT 9"):
    print(r)
