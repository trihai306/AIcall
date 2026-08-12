import json, urllib.request
d = json.loads(urllib.request.urlopen("http://127.0.0.1:8100/api/health", timeout=10).read())
for k, v in d.items():
    print(f"  {k}: {json.dumps(v, ensure_ascii=False)[:160]}")
