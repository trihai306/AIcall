import time, sys, requests
sys.stdout.reconfigure(encoding="utf-8")
# do tong RAG qua benchmark endpoint
xs=[]
for _ in range(5):
    r = requests.post("http://localhost:8100/api/benchmark/rag", timeout=60).json()
    xs.append(r.get("latency_ms"))
print("  RAG tong (5 lan):", xs, "-> min", min(xs), "ms")
