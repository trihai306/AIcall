"""Theo doi log backend, in ra cac moc cua CUOC GOI. Xa tung dong ngay."""
import re, sys, time
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
L = Path(r"C:\duan\chat-ai\logs\backend.log")
KHOA = re.compile(
    r"dialled|cầu tiếng|đứt ổ cắm|bắt máy|nối máy|lời chào|chào|ghi âm|"
    r"kết thúc|lượt\)|đường tiêm|uplink|ERROR|Traceback|Exception", re.IGNORECASE)
while not L.exists():
    time.sleep(1)
f = L.open("r", encoding="utf-8", errors="replace")
f.seek(0, 2)
vi_tri = f.tell()
print("đang theo dõi log cuộc gọi…")
while True:
    d = f.readline()
    if not d:
        # tệp bị cắt/xoay vòng thì mở lại
        try:
            if L.stat().st_size < vi_tri:
                f.close(); f = L.open("r", encoding="utf-8", errors="replace"); vi_tri = 0
        except OSError:
            pass
        time.sleep(0.4); continue
    vi_tri = f.tell()
    d = d.rstrip()
    if KHOA.search(d):
        print(d[-160:])
