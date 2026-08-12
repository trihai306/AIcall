import sys, inspect, f5_tts.model.cfm as c
sys.stdout.reconfigure(encoding="utf-8")
src = inspect.getsource(c.CFM.sample)
print("=== dong goi transformer trong CFM.sample ===")
for i, l in enumerate(src.splitlines()):
    s = l.strip()
    if "transformer" in s or "odeint" in s or "def fn" in s:
        print("  %3d | %s" % (i, s[:110]))
print("\n=== module con cua CFM ===")
init = inspect.getsource(c.CFM.__init__)
for l in init.splitlines():
    s = l.strip()
    if s.startswith("self.") and "=" in s:
        print("  " + s[:90])
