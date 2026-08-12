import sys, time, torch
sys.stdout.reconfigure(encoding="utf-8")
print("torch:", torch.__version__)
try:
    import triton; print("triton:", triton.__version__)
except ImportError:
    print("triton: CHUA CO (torch.compile tren Windows can triton)")

m = torch.nn.Sequential(torch.nn.Linear(512,512), torch.nn.GELU(), torch.nn.Linear(512,512)).cuda().eval()
x = torch.randn(4,512, device="cuda")
try:
    t0=time.perf_counter()
    cm = torch.compile(m)
    with torch.inference_mode():
        cm(x); torch.cuda.synchronize()
    print("torch.compile: CHAY DUOC (bien dich %.1fs)" % (time.perf_counter()-t0))
except Exception as e:
    print("torch.compile: LOI ->", type(e).__name__, str(e)[:160])
