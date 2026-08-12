import time, sys, threading, subprocess, requests
sys.stdout.reconfigure(encoding="utf-8")
TTS = "http://localhost:8100/api/voices/test-tts"
TXT = "Dạ anh chị cần chuẩn bị chứng minh nhân dân còn hiệu lực"

samples = []
stop = threading.Event()
def sampler():
    while not stop.is_set():
        try:
            g = subprocess.run(["nvidia-smi","--query-gpu=utilization.gpu,clocks.sm,power.draw",
                                "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=3).stdout.strip()
            samples.append(g)
        except Exception: pass
        time.sleep(0.15)

try:
    import psutil
    have_ps = True
except ImportError:
    have_ps = False

print("psutil:", "co" if have_ps else "CHUA CAI")
if have_ps:
    import psutil
    proc = None
    for p in psutil.process_iter(["name","cmdline"]):
        cl = " ".join(p.info.get("cmdline") or [])
        if "uvicorn" in cl and "backend.main" in cl:
            proc = p; break
    print("tien trinh backend:", proc.pid if proc else "khong tim thay")
    print("so core:", psutil.cpu_count(logical=False), "vat ly /", psutil.cpu_count(), "logic")

    cpu_tot, cpu_proc = [], []
    def cpu_sampler():
        if proc: proc.cpu_percent(None)
        psutil.cpu_percent(None, percpu=True)
        while not stop.is_set():
            cpu_tot.append(psutil.cpu_percent(0.15, percpu=True))
            if proc:
                try: cpu_proc.append(proc.cpu_percent(None))
                except Exception: pass
    threading.Thread(target=cpu_sampler, daemon=True).start()

threading.Thread(target=sampler, daemon=True).start()
time.sleep(1.0)

requests.post(TTS, data={"text":TXT,"voice_name":"default","fast":"true"}, timeout=180)  # warm
t0=time.perf_counter()
r = requests.post(TTS, data={"text":TXT,"voice_name":"default","fast":"true"}, timeout=180).json()
el = (time.perf_counter()-t0)*1000
stop.set(); time.sleep(0.4)

print("\n=== TTS elapsed (server bao) %s ms | wall %.0f ms ===" % (r.get("elapsed_ms"), el))
gu = [int(s.split(",")[0]) for s in samples if s]
gc = [int(s.split(",")[1]) for s in samples if s]
gp = [float(s.split(",")[2]) for s in samples if s]
if gu: print("GPU  util dinh %d%% | xung dinh %d MHz | dien dinh %.0f W" % (max(gu), max(gc), max(gp)))
if have_ps and cpu_tot:
    peak_core = max(max(row) for row in cpu_tot)
    peak_avg  = max(sum(row)/len(row) for row in cpu_tot)
    print("CPU  1 core cao nhat %.0f%% | trung binh toan bo %.0f%%" % (peak_core, peak_avg))
    if cpu_proc: print("CPU  rieng tien trinh backend: dinh %.0f%% (tren %d core => %.1f core)" % (max(cpu_proc), psutil.cpu_count(), max(cpu_proc)/100))
