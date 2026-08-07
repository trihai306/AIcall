import sys, subprocess
sys.stdout.reconfigure(encoding="utf-8")
import psutil
n = 0
for p in psutil.process_iter(["name", "cmdline"]):
    cl = " ".join(p.info.get("cmdline") or [])
    if "finetune_cli" in cl or "train.bat" in cl:
        try:
            p.kill(); n += 1
            print("  đã dừng PID", p.pid)
        except Exception as e:
            print("  không dừng được", p.pid, e)
print("tổng %d tiến trình train đã dừng" % n)
