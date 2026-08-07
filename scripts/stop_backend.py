"""Dừng hẳn tiến trình backend đang giữ cổng 8100.

Stop-Process của PowerShell đôi khi không kịp: start_services.ps1 chạy ngay sau
đó vẫn thấy tiến trình cũ trong danh sách và bỏ qua bước khởi động, nên chạy bản
code cũ mà tưởng đã cập nhật.
"""
import sys, time
sys.stdout.reconfigure(encoding="utf-8")
import psutil

da_dung = []
for p in psutil.process_iter(["name", "cmdline"]):
    cl = " ".join(p.info.get("cmdline") or [])
    if "uvicorn" in cl and "backend.main" in cl:
        try:
            for ch in p.children(recursive=True):
                ch.kill()
            p.kill()
            da_dung.append(p.pid)
        except Exception as e:
            print(f"  không dừng được {p.pid}: {e}")

for _ in range(20):                     # chờ cổng nhả hẳn
    if not any(c.status == "LISTEN" and c.laddr.port == 8100
               for c in psutil.net_connections(kind="inet")):
        break
    time.sleep(0.5)

print(f"  đã dừng {len(da_dung)} tiến trình backend: {da_dung}" if da_dung
      else "  không có backend nào đang chạy")
